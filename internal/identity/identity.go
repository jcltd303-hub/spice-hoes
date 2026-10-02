package identity

import (
    "bytes"
    "fmt"
    "image"
    "image/color"
    _ "image/gif"
    _ "image/jpeg"
    _ "image/png"
    "math"
)

const (
    ArcFaceSize = 112
    side = 24
)

type Point struct { X, Y float64 }

var ArcFaceTemplate = [5]Point{
    {38.2946, 51.6963},
    {73.5318, 51.5014},
    {56.0252, 71.7366},
    {41.5493, 92.3655},
    {70.7299, 92.2041},
}

type SimilarityTransform struct {
    A, B, TX, TY float64
}

func EstimateSimilarity(src [5]Point, dst [5]Point) (SimilarityTransform,error) {
    var sx,sy,dx,dy float64
    for i:=0;i<5;i++ { sx+=src[i].X; sy+=src[i].Y; dx+=dst[i].X; dy+=dst[i].Y }
    sx/=5; sy/=5; dx/=5; dy/=5
    var denom,across,bcross float64
    for i:=0;i<5;i++ {
        x:=src[i].X-sx; y:=src[i].Y-sy
        u:=dst[i].X-dx; v:=dst[i].Y-dy
        denom += x*x+y*y
        across += x*u+y*v
        bcross += x*v-y*u
    }
    if denom < 1e-9 { return SimilarityTransform{},fmt.Errorf("degenerate landmarks") }
    a:=across/denom
    b:=bcross/denom
    tx:=dx-a*sx+b*sy
    ty:=dy-b*sx-a*sy
    return SimilarityTransform{A:a,B:b,TX:tx,TY:ty},nil
}

func bilinear(img image.Image, x,y float64) color.RGBA {
    b:=img.Bounds()
    if x < float64(b.Min.X) || y < float64(b.Min.Y) || x > float64(b.Max.X-1) || y > float64(b.Max.Y-1) {
        return color.RGBA{0,0,0,255}
    }
    x0:=int(math.Floor(x)); y0:=int(math.Floor(y))
    x1:=x0+1; if x1>=b.Max.X {x1=b.Max.X-1}
    y1:=y0+1; if y1>=b.Max.Y {y1=b.Max.Y-1}
    fx:=x-float64(x0); fy:=y-float64(y0)
    sample:=func(xx,yy int)(float64,float64,float64){
        r,g,bl,_:=img.At(xx,yy).RGBA()
        return float64(r>>8),float64(g>>8),float64(bl>>8)
    }
    r00,g00,b00:=sample(x0,y0); r10,g10,b10:=sample(x1,y0)
    r01,g01,b01:=sample(x0,y1); r11,g11,b11:=sample(x1,y1)
    mix:=func(v00,v10,v01,v11 float64) uint8 {
        top:=v00*(1-fx)+v10*fx
        bot:=v01*(1-fx)+v11*fx
        v:=top*(1-fy)+bot*fy
        if v<0 {v=0}; if v>255 {v=255}
        return uint8(math.Round(v))
    }
    return color.RGBA{mix(r00,r10,r01,r11),mix(g00,g10,g01,g11),mix(b00,b10,b01,b11),255}
}

func AlignFace(img image.Image, landmarks [5]Point) (image.Image,error) {
    t,err:=EstimateSimilarity(landmarks,ArcFaceTemplate); if err!=nil { return nil,err }
    det:=t.A*t.A+t.B*t.B
    if det < 1e-12 { return nil,fmt.Errorf("non-invertible similarity transform") }
    out:=image.NewRGBA(image.Rect(0,0,ArcFaceSize,ArcFaceSize))
    for y:=0;y<ArcFaceSize;y++ {
        for x:=0;x<ArcFaceSize;x++ {
            dx:=float64(x)-t.TX
            dy:=float64(y)-t.TY
            sx:=( t.A*dx + t.B*dy)/det
            sy:=(-t.B*dx + t.A*dy)/det
            out.SetRGBA(x,y,bilinear(img,sx,sy))
        }
    }
    return out,nil
}

func ArcFaceInputAlignedImage(img image.Image, landmarks [5]Point) ([]float64,error) {
    aligned,err:=AlignFace(img,landmarks); if err!=nil { return nil,err }
    plane:=ArcFaceSize*ArcFaceSize
    out:=make([]float64,3*plane)
    for y:=0;y<ArcFaceSize;y++ {
        for x:=0;x<ArcFaceSize;x++ {
            r,g,bv,_:=aligned.At(x,y).RGBA()
            idx:=y*ArcFaceSize+x
            out[idx]=(float64(r>>8)-127.5)/127.5
            out[plane+idx]=(float64(g>>8)-127.5)/127.5
            out[2*plane+idx]=(float64(bv>>8)-127.5)/127.5
        }
    }
    return out,nil
}


func ArcFaceInputAligned(data []byte, landmarks [5]Point) ([]float64,error) {
    img,_,err:=image.Decode(bytes.NewReader(data)); if err!=nil { return nil,fmt.Errorf("decode image: %w",err) }
    return ArcFaceInputAlignedImage(img, landmarks)
}

func ArcFaceInput(data []byte) ([]float64,error) {
    img,_,err := image.Decode(bytes.NewReader(data)); if err != nil { return nil,fmt.Errorf("decode image: %w",err) }
    b := img.Bounds()
    if b.Dx()==0 || b.Dy()==0 { return nil,fmt.Errorf("empty image") }

    // Until SCRFD/5-point alignment is enabled, use a deterministic centered
    // square crop. The NPU embedding model and score explicitly report this
    // alignment mode so benchmark data cannot confuse it with landmark alignment.
    sidePx := b.Dx(); if b.Dy() < sidePx { sidePx = b.Dy() }
    x0 := b.Min.X + (b.Dx()-sidePx)/2
    y0 := b.Min.Y + (b.Dy()-sidePx)/2

    plane := ArcFaceSize*ArcFaceSize
    out := make([]float64,3*plane)
    for oy:=0; oy<ArcFaceSize; oy++ {
        sy := y0 + int((float64(oy)+0.5)*float64(sidePx)/ArcFaceSize)
        if sy >= y0+sidePx { sy = y0+sidePx-1 }
        for ox:=0; ox<ArcFaceSize; ox++ {
            sx := x0 + int((float64(ox)+0.5)*float64(sidePx)/ArcFaceSize)
            if sx >= x0+sidePx { sx = x0+sidePx-1 }
            r,g,bv,_ := img.At(sx,sy).RGBA()
            idx := oy*ArcFaceSize+ox
            out[idx] = (float64(r>>8)-127.5)/127.5
            out[plane+idx] = (float64(g>>8)-127.5)/127.5
            out[2*plane+idx] = (float64(bv>>8)-127.5)/127.5
        }
    }
    return out,nil
}

func Normalize(v []float64) []float64 {
    out:=append([]float64(nil),v...)
    norm:=0.0; for _,x:=range out { norm += x*x }; norm=math.Sqrt(norm)
    if norm > 1e-12 { for i:=range out { out[i]/=norm } }
    return out
}

func Cosine(a,b []float64) (float64,error) {
    if len(a)==0 || len(a)!=len(b) { return 0,fmt.Errorf("embedding length mismatch") }
    aa:=Normalize(a); bb:=Normalize(b); dot:=0.0
    for i:=range aa { dot += aa[i]*bb[i] }
    if dot < -1 { dot=-1 }; if dot > 1 { dot=1 }
    return dot,nil
}

func fingerprint(data []byte) ([]float64,error) {
    img,_,err := image.Decode(bytes.NewReader(data)); if err != nil { return nil,fmt.Errorf("decode image: %w",err) }
    b := img.Bounds(); if b.Dx()==0 || b.Dy()==0 { return nil,fmt.Errorf("empty image") }
    out := make([]float64,0,side*side)
    for oy:=0; oy<side; oy++ {
        y := b.Min.Y + int((float64(oy)+0.5)*float64(b.Dy())/side); if y>=b.Max.Y { y=b.Max.Y-1 }
        for ox:=0; ox<side; ox++ {
            x := b.Min.X + int((float64(ox)+0.5)*float64(b.Dx())/side); if x>=b.Max.X { x=b.Max.X-1 }
            r,g,bl,_ := img.At(x,y).RGBA()
            l := 0.299*float64(r>>8)+0.587*float64(g>>8)+0.114*float64(bl>>8)
            out = append(out,l/255.0)
        }
    }
    mean:=0.0; for _,v:= range out { mean += v }; mean /= float64(len(out))
    norm:=0.0; for i:= range out { out[i]-=mean; norm += out[i]*out[i] }; norm=math.Sqrt(norm)
    if norm>1e-9 { for i:= range out { out[i]/=norm } }
    return out,nil
}

func Similarity(a,b []byte) (float64,error) {
    fa,err:=fingerprint(a); if err!=nil { return 0,err }; fb,err:=fingerprint(b); if err!=nil { return 0,err }
    dot,err:=Cosine(fa,fb); if err!=nil { return 0,err }
    score := (dot+1)/2; if score<0 {score=0}; if score>1 {score=1}; return score,nil
}
