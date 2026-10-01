package identity

import (
    "bytes"
    "image"
    "image/color"
    "image/png"
    "testing"
)

func pngBytes(c color.RGBA) []byte {
    img:=image.NewRGBA(image.Rect(0,0,160,120))
    for y:=0;y<120;y++ { for x:=0;x<160;x++ { img.SetRGBA(x,y,c) } }
    var b bytes.Buffer
    _ = png.Encode(&b,img)
    return b.Bytes()
}

func TestArcFaceInputShape(t *testing.T) {
    v,err:=ArcFaceInput(pngBytes(color.RGBA{200,100,50,255}))
    if err!=nil { t.Fatal(err) }
    if len(v)!=3*112*112 { t.Fatalf("unexpected input size %d",len(v)) }
    for _,x:=range v { if x < -1.001 || x > 1.001 { t.Fatalf("not normalized: %f",x) } }
}

func TestCosine(t *testing.T) {
    same,err:=Cosine([]float64{1,2,3},[]float64{1,2,3}); if err!=nil { t.Fatal(err) }
    if same < 0.999999 { t.Fatalf("same cosine %f",same) }
    opposite,err:=Cosine([]float64{1,0},[]float64{-1,0}); if err!=nil { t.Fatal(err) }
    if opposite > -0.999999 { t.Fatalf("opposite cosine %f",opposite) }
}
