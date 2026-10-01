package imagemetrics

import (
	"encoding/base64"
	"testing"
)

func TestAnalyzePNG(t *testing.T) {
	raw, err := base64.StdEncoding.DecodeString("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAtRwMAgAAAABJRU5ErkJggg==")
	if err != nil {
		t.Fatal(err)
	}
	m, err := Analyze(raw)
	if err != nil {
		t.Fatal(err)
	}
	if !m.Available || m.Backend != "go-stdlib" {
		t.Fatalf("unexpected backend: %+v", m)
	}
	if m.Width != 1 || m.Height != 1 {
		t.Fatalf("unexpected dimensions: %dx%d", m.Width, m.Height)
	}
}
