package identity

import (
    "bytes"
    "fmt"
    "image"
    _ "image/jpeg"
    _ "image/png"
    "math"

    "github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

const SCRFDSize = 640

type DetectorInput struct {
    Tensor []float64
    Scale float64
    PadX float64
    PadY float64
    OriginalWidth int
    OriginalHeight int
}

type FaceDetection struct {
    Score float64
    X1 float64
    Y1 float64
    X2 float64
    Y2 float64
    Landmarks [5]Point
}

func SCRFDInput(data []byte) (DetectorInput,error) {
    img,_,err:=image.Decode(bytes.NewReader(data)); if err!=nil { return DetectorInput{},fmt.Errorf("decode image: %w",err) }
    b:=img.Bounds()
    w,h:=b.Dx(),b.Dy()
    if w<=0 || h<=0 { return DetectorInput{},fmt.Errorf("empty image") }

    scale:=math.Min(float64(SCRFDSize)/float64(w),float64(SCRFDSize)/float64(h))
    newW:=int(math.Round(float64(w)*scale))
    newH:=int(math.Round(float64(h)*scale))
    padX:=0.0
    padY:=0.0

    plane:=SCRFDSize*SCRFDSize
    out:=make([]float64,3*plane)
    fill:= (0.0-127.5)/128.0
    for i:=range out { out[i]=fill }

    for y:=0;y<newH;y++ {
        sy:=float64(b.Min.Y)+(float64(y)+0.5)/scale-0.5
        for x:=0;x<newW;x++ {
            sx:=float64(b.Min.X)+(float64(x)+0.5)/scale-0.5
            px:=bilinear(img,sx,sy)
            dx:=x
            dy:=y
            if dx<0 || dy<0 || dx>=SCRFDSize || dy>=SCRFDSize { continue }
            idx:=dy*SCRFDSize+dx
            // InsightFace detector preprocessing uses RGB with mean 127.5/std 128.
            out[idx]=(float64(px.R)-127.5)/128.0
            out[plane+idx]=(float64(px.G)-127.5)/128.0
            out[2*plane+idx]=(float64(px.B)-127.5)/128.0
        }
    }
    return DetectorInput{
        Tensor:out,Scale:scale,PadX:padX,PadY:padY,
        OriginalWidth:w,OriginalHeight:h,
    },nil
}

type scrfdHeadSet struct {
    score []float64
    bbox []float64
    kps []float64
    count int
    grid int
    stride float64
}

func lastDim(dims []int) int {
    if len(dims)==0 { return 0 }
    return dims[len(dims)-1]
}

func inferChannels(out nativecore.TensorOutput) int {
    ch:=lastDim(out.Dims)
    if ch==1 || ch==4 || ch==10 { return ch }
    // Some exporters flatten channels into the penultimate dimension.
    if len(out.Dims)>=2 {
        p:=out.Dims[len(out.Dims)-2]
        if p==1 || p==4 || p==10 { return p }
    }
    return 0
}

func DecodeSCRFD(outputs []nativecore.TensorOutput, prep DetectorInput, threshold,nmsThreshold float64) ([]FaceDetection,error) {
    type grouped struct {
        score,bbox,kps []float64
        count int
    }
    groups:=map[int]*grouped{}
    for _,out:=range outputs {
        ch:=inferChannels(out)
        if ch==0 || len(out.Values)%ch!=0 { continue }
        count:=len(out.Values)/ch
        g:=groups[count]
        if g==nil { g=&grouped{count:count}; groups[count]=g }
        switch ch {
        case 1: g.score=out.Values
        case 4: g.bbox=out.Values
        case 10: g.kps=out.Values
        }
    }

    detections:=make([]FaceDetection,0)
    const anchors=2
    for count,g:=range groups {
        if len(g.score)==0 || len(g.bbox)!=count*4 || len(g.kps)!=count*10 { continue }
        if count%anchors!=0 { continue }
        cells:=count/anchors
        grid:=int(math.Round(math.Sqrt(float64(cells))))
        if grid*grid!=cells || grid<=0 { continue }
        stride:=float64(SCRFDSize)/float64(grid)
        if stride<4 || stride>64 { continue }

        for i:=0;i<count;i++ {
            score:=g.score[i]
            if score<threshold { continue }
            cell:=i/anchors
            gx:=cell%grid
            gy:=cell/grid
            cx:=float64(gx)*stride
            cy:=float64(gy)*stride
            bo:=i*4
            x1:=cx-g.bbox[bo]*stride
            y1:=cy-g.bbox[bo+1]*stride
            x2:=cx+g.bbox[bo+2]*stride
            y2:=cy+g.bbox[bo+3]*stride
            var lm [5]Point
            ko:=i*10
            for j:=0;j<5;j++ {
                lm[j]=Point{
                    X:cx+g.kps[ko+j*2]*stride,
                    Y:cy+g.kps[ko+j*2+1]*stride,
                }
            }

            unmap:=func(x,y float64)(float64,float64){
                ox:=(x-prep.PadX)/prep.Scale
                oy:=(y-prep.PadY)/prep.Scale
                if ox<0 {ox=0}; if oy<0 {oy=0}
                if ox>float64(prep.OriginalWidth-1) {ox=float64(prep.OriginalWidth-1)}
                if oy>float64(prep.OriginalHeight-1) {oy=float64(prep.OriginalHeight-1)}
                return ox,oy
            }
            x1,y1=unmap(x1,y1)
            x2,y2=unmap(x2,y2)
            for j:=0;j<5;j++ { lm[j].X,lm[j].Y=unmap(lm[j].X,lm[j].Y) }
            if x2<=x1 || y2<=y1 { continue }
            detections=append(detections,FaceDetection{
                Score:score,X1:x1,Y1:y1,X2:x2,Y2:y2,Landmarks:lm,
            })
        }
    }
    if len(detections)==0 { return nil,fmt.Errorf("SCRFD found no face above threshold %.2f",threshold) }
    return nms(detections,nmsThreshold),nil
}

func iou(a,b FaceDetection) float64 {
    x1:=math.Max(a.X1,b.X1); y1:=math.Max(a.Y1,b.Y1)
    x2:=math.Min(a.X2,b.X2); y2:=math.Min(a.Y2,b.Y2)
    iw:=math.Max(0,x2-x1); ih:=math.Max(0,y2-y1)
    inter:=iw*ih
    aa:=(a.X2-a.X1)*(a.Y2-a.Y1)
    ba:=(b.X2-b.X1)*(b.Y2-b.Y1)
    denom:=aa+ba-inter
    if denom<=0 { return 0 }
    return inter/denom
}

func nms(in []FaceDetection,threshold float64) []FaceDetection {
    remaining:=append([]FaceDetection(nil),in...)
    out:=make([]FaceDetection,0,len(in))
    for len(remaining)>0 {
        best:=0
        for i:=1;i<len(remaining);i++ { if remaining[i].Score>remaining[best].Score {best=i} }
        picked:=remaining[best]
        out=append(out,picked)
        next:=make([]FaceDetection,0,len(remaining)-1)
        for i,d:=range remaining {
            if i==best {continue}
            if iou(picked,d)<=threshold {next=append(next,d)}
        }
        remaining=next
    }
    return out
}
