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

const side = 24

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
    if len(fa)!=len(fb) { return 0,fmt.Errorf("fingerprint length mismatch") }
    dot:=0.0; for i:=range fa { dot += fa[i]*fb[i] }
    score := (dot+1)/2; if score<0 {score=0}; if score>1 {score=1}; return score,nil
}