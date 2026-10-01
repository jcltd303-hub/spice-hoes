package imagemetrics

import (
	"bytes"
	"image"
	"image/color"
	"image/png"
	"testing"
)

func TestAnalyzePNG(t *testing.T) {
	img := image.NewRGBA(image.Rect(0, 0, 2, 2))
	img.Set(0, 0, color.RGBA{128, 128, 128, 255})
	img.Set(1, 0, color.RGBA{255, 255, 255, 255})
	img.Set(0, 1, color.RGBA{0, 0, 0, 255})
	img.Set(1, 1, color.RGBA{64, 64, 64, 255})

	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatal(err)
	}

	m, err := Analyze(buf.Bytes())
	if err != nil {
		t.Fatal(err)
	}
	if !m.Available || m.Backend != "go-stdlib" {
		t.Fatalf("unexpected backend: %+v", m)
	}
	if m.Width != 2 || m.Height != 2 {
		t.Fatalf("unexpected dimensions: %dx%d", m.Width, m.Height)
	}
}
