package localdream

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGenerateRequestsPNGWithExplicitSamplingSettings(t *testing.T) {
	img := image.NewNRGBA(image.Rect(0, 0, 2, 1))
	img.SetNRGBA(0, 0, color.NRGBA{R: 23, G: 42, B: 61, A: 255})
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/generate" {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Error("missing authentication")
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		if payload["output_format"] != "png" {
			t.Errorf("expected PNG transport, got %v", payload["output_format"])
		}
		for key, want := range map[string]float64{"steps": 24, "cfg": 5.5, "seed": 41000, "width": 768, "height": 1024} {
			if payload[key] != want {
				t.Errorf("%s: got %v, want %v", key, payload[key], want)
			}
		}
		w.Header().Set("Content-Type", "text/event-stream")
		body, _ := json.Marshal(map[string]any{"image": base64.StdEncoding.EncodeToString(buf.Bytes())})
		fmt.Fprintf(w, "event: complete\ndata: %s\n\n", body)
	}))
	defer server.Close()
	client := &Client{BaseURL: server.URL, Token: "test-token", HTTP: server.Client()}
	out, err := client.Generate(context.Background(), GenerateRequest{Prompt: "RAW photograph", Seed: 41000, Width: 768, Height: 1024, Steps: 24, Guidance: 5.5})
	if err != nil {
		t.Fatal(err)
	}
	if out.MIME != "image/png" || !bytes.Equal(out.Encoded, buf.Bytes()) {
		t.Fatal("PNG payload was not preserved")
	}
	if out.Frame.Bounds() != img.Bounds() {
		t.Fatalf("wrong dimensions: %v", out.Frame.Bounds())
	}
}

func TestGenerateStillDecodesRawRGBAFromOlderRuntime(t *testing.T) {
	raw := []byte{23, 42, 61, 255, 70, 80, 90, 255}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := json.Marshal(map[string]any{"image": base64.StdEncoding.EncodeToString(raw), "width": 2, "height": 1, "channels": 4})
		fmt.Fprintf(w, "event: complete\ndata: %s\n\n", body)
	}))
	defer server.Close()
	out, err := (&Client{BaseURL: server.URL, HTTP: server.Client()}).Generate(context.Background(), GenerateRequest{Prompt: "RAW photograph"})
	if err != nil {
		t.Fatal(err)
	}
	if out.Frame.Bounds() != image.Rect(0, 0, 2, 1) {
		t.Fatalf("wrong dimensions: %v", out.Frame.Bounds())
	}
	if got := color.NRGBAModel.Convert(out.Frame.At(0, 0)); got != (color.NRGBA{23, 42, 61, 255}) {
		t.Fatalf("bad decoded pixel: %v", got)
	}
	if out.Encoded != nil {
		t.Fatal("raw bytes must never be represented as an encoded PNG")
	}
}
