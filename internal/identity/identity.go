package identity

import (
    "bytes"
    "fmt"
    "image"
    _ "image/gif"
    _ "image/jpeg"
    _ "image/png"
    "math"
)

const (
    ArcFaceSize = 112
    side = 24
)

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
