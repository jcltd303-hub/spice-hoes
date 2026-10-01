package imagemetrics

import (
	"bytes"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"math"
)

type Metrics struct {
	Available       bool    `json:"available"`
	Backend         string  `json:"backend"`
	Width           int     `json:"width"`
	Height          int     `json:"height"`
	Brightness      float64 `json:"brightness"`
	Sharpness       float64 `json:"sharpness"`
	Contrast        float64 `json:"contrast"`
	ResolutionScore float64 `json:"resolution_score"`
	ExposureScore   float64 `json:"exposure_score"`
	LocalScore      float64 `json:"local_score"`
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

func round6(v float64) float64 {
	return math.Round(v*1e6) / 1e6
}

func grayAt(img image.Image, x, y int) float64 {
	r, g, b, _ := img.At(x, y).RGBA()
	r8 := float64(r >> 8)
	g8 := float64(g >> 8)
	b8 := float64(b >> 8)
	// Matches standard luminance conversion closely enough for Pillow L metrics.
	return 0.299*r8 + 0.587*g8 + 0.114*b8
}

func stddev(values []float64, mean float64) float64 {
	if len(values) == 0 {
		return 0
	}
	var sum float64
	for _, v := range values {
		d := v - mean
		sum += d * d
	}
	return math.Sqrt(sum / float64(len(values)))
}

func Analyze(data []byte) (Metrics, error) {
	img, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return Metrics{}, fmt.Errorf("decode image: %w", err)
	}
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	if w <= 0 || h <= 0 {
		return Metrics{}, fmt.Errorf("invalid image dimensions")
	}

	gray := make([]float64, w*h)
	var sum float64
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			v := grayAt(img, b.Min.X+x, b.Min.Y+y)
			gray[y*w+x] = v
			sum += v
		}
	}
	meanGray := sum / float64(len(gray))
	brightness := meanGray / 255.0
	contrast := clamp01(stddev(gray, meanGray) / 128.0)

	// Pillow ImageFilter.FIND_EDGES uses a 3x3 kernel:
	//  -1 -1 -1
	//  -1  8 -1
	//  -1 -1 -1
	edges := make([]float64, 0, w*h)
	var edgeSum float64
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			var edge float64
			if x == 0 || y == 0 || x == w-1 || y == h-1 {
				edge = gray[y*w+x]
			} else {
				center := gray[y*w+x] * 8
				neighbors := gray[(y-1)*w+x-1] + gray[(y-1)*w+x] + gray[(y-1)*w+x+1] +
					gray[y*w+x-1] + gray[y*w+x+1] +
					gray[(y+1)*w+x-1] + gray[(y+1)*w+x] + gray[(y+1)*w+x+1]
				edge = center - neighbors
				if edge < 0 {
					edge = 0
				} else if edge > 255 {
					edge = 255
				}
			}
			edges = append(edges, edge)
			edgeSum += edge
		}
	}
	edgeMean := edgeSum / float64(len(edges))
	sharpness := clamp01(stddev(edges, edgeMean) / 64.0)

	megapixels := float64(w*h) / 1_000_000.0
	resolution := clamp01(megapixels / 0.7)
	exposure := clamp01(1.0 - math.Abs(brightness-0.5)/0.5)
	local := (sharpness + exposure + contrast + resolution) / 4.0

	return Metrics{
		Available:       true,
		Backend:         "go-stdlib",
		Width:           w,
		Height:          h,
		Brightness:      round6(brightness),
		Sharpness:       round6(sharpness),
		Contrast:        round6(contrast),
		ResolutionScore: round6(resolution),
		ExposureScore:   round6(exposure),
		LocalScore:      round6(local),
	}, nil
}
