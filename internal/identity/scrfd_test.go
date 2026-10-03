package identity

import (
    "os"
    "testing"

    "github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

func TestDecodeSCRFDSingleFace(t *testing.T) {
    // stride 8 => grid 80x80 with two anchors => 12800 predictions
    count:=80*80*2
    scores:=make([]float64,count)
    boxes:=make([]float64,count*4)
    kps:=make([]float64,count*10)

    // Pick grid cell (20, 30), anchor 0.
    idx:=(30*80+20)*2
    scores[idx]=0.95
    bo:=idx*4
    boxes[bo+0]=2
    boxes[bo+1]=3
    boxes[bo+2]=2
    boxes[bo+3]=3

    ko:=idx*10
    // Five relative points around the center.
    vals:=[]float64{
        -1.0,-1.0,
         1.0,-1.0,
         0.0, 0.0,
        -0.8, 1.2,
         0.8, 1.2,
    }
    copy(kps[ko:ko+10],vals)

    prep:=DetectorInput{
        Scale:1,
        PadX:0,
        PadY:0,
        OriginalWidth:640,
        OriginalHeight:640,
    }
    outs:=[]nativecore.TensorOutput{
        {Name:"score_8",Dims:[]int{1,count,1},Values:scores},
        {Name:"bbox_8",Dims:[]int{1,count,4},Values:boxes},
        {Name:"kps_8",Dims:[]int{1,count,10},Values:kps},
    }

    faces,err:=DecodeSCRFD(outs,prep,0.5,0.4)
    if err!=nil { t.Fatal(err) }
    if len(faces)!=1 { t.Fatalf("expected 1 face, got %d",len(faces)) }
    f:=faces[0]
    if f.Score!=0.95 { t.Fatalf("unexpected score %f",f.Score) }

    // center is (20*8, 30*8) = (160, 240)
    if f.X1!=144 || f.Y1!=216 || f.X2!=176 || f.Y2!=264 {
        t.Fatalf("unexpected box %+v",f)
    }
    if f.Landmarks[2].X!=160 || f.Landmarks[2].Y!=240 {
        t.Fatalf("unexpected nose landmark %+v",f.Landmarks[2])
    }
}

func TestDecodeSCRFDNMS(t *testing.T) {
    count:=80*80*2
    scores:=make([]float64,count)
    boxes:=make([]float64,count*4)
    kps:=make([]float64,count*10)

    for _,idx:=range []int{(20*80+20)*2,(20*80+20)*2+1} {
        scores[idx]=0.9
        bo:=idx*4
        boxes[bo+0]=2
        boxes[bo+1]=2
        boxes[bo+2]=2
        boxes[bo+3]=2
    }

    prep:=DetectorInput{Scale:1,OriginalWidth:640,OriginalHeight:640}
    outs:=[]nativecore.TensorOutput{
        {Dims:[]int{1,count,1},Values:scores},
        {Dims:[]int{1,count,4},Values:boxes},
        {Dims:[]int{1,count,10},Values:kps},
    }

    faces,err:=DecodeSCRFD(outs,prep,0.5,0.4)
    if err!=nil { t.Fatal(err) }
    if len(faces)!=1 { t.Fatalf("expected NMS to keep 1 face, got %d",len(faces)) }
}

func TestDecodeSCRFDFallback(t *testing.T) {
    old, had := os.LookupEnv("SPICE_SCRFD_FALLBACK_THRESHOLD")
    _ = os.Setenv("SPICE_SCRFD_FALLBACK_THRESHOLD", "0.10")
    defer func() {
        if had { _ = os.Setenv("SPICE_SCRFD_FALLBACK_THRESHOLD", old) } else { _ = os.Unsetenv("SPICE_SCRFD_FALLBACK_THRESHOLD") }
    }()

    count:=80*80*2
    scores:=make([]float64,count)
    boxes:=make([]float64,count*4)
    kps:=make([]float64,count*10)
    idx:=(30*80+20)*2
    scores[idx]=0.133556
    bo:=idx*4
    boxes[bo+0]=2
    boxes[bo+1]=3
    boxes[bo+2]=2
    boxes[bo+3]=3
    ko:=idx*10
    copy(kps[ko:ko+10],[]float64{-1,-1,1,-1,0,0,-0.8,1.2,0.8,1.2})

    prep:=DetectorInput{Scale:1,OriginalWidth:640,OriginalHeight:640}
    outs:=[]nativecore.TensorOutput{
        {Dims:[]int{1,count,1},Values:scores},
        {Dims:[]int{1,count,4},Values:boxes},
        {Dims:[]int{1,count,10},Values:kps},
    }

    faces,used,err:=DecodeSCRFDWithFallback(outs,prep,0.5,0.4)
    if err!=nil { t.Fatal(err) }
    if len(faces)!=1 { t.Fatalf("expected fallback face, got %d",len(faces)) }
    if used!=0.10 { t.Fatalf("expected fallback threshold 0.10, got %.2f",used) }
}

func TestDecodeSCRFDFallbackRejectsBelowFloor(t *testing.T) {
    old, had := os.LookupEnv("SPICE_SCRFD_FALLBACK_THRESHOLD")
    _ = os.Setenv("SPICE_SCRFD_FALLBACK_THRESHOLD", "0.10")
    defer func() {
        if had { _ = os.Setenv("SPICE_SCRFD_FALLBACK_THRESHOLD", old) } else { _ = os.Unsetenv("SPICE_SCRFD_FALLBACK_THRESHOLD") }
    }()

    count:=80*80*2
    scores:=make([]float64,count)
    boxes:=make([]float64,count*4)
    kps:=make([]float64,count*10)
    idx:=(30*80+20)*2
    scores[idx]=0.08

    prep:=DetectorInput{Scale:1,OriginalWidth:640,OriginalHeight:640}
    outs:=[]nativecore.TensorOutput{
        {Dims:[]int{1,count,1},Values:scores},
        {Dims:[]int{1,count,4},Values:boxes},
        {Dims:[]int{1,count,10},Values:kps},
    }

    _,used,err:=DecodeSCRFDWithFallback(outs,prep,0.5,0.4)
    if err==nil { t.Fatal("expected low-confidence detection to remain rejected") }
    if used!=0.5 { t.Fatalf("expected preferred threshold to remain reported, got %.2f",used) }
}
