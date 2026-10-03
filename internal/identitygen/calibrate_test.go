package identitygen

import (
	"math"
	"testing"

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
)

// unit vector in 4D with a given angle in the x/y plane plus a small z offset.
func vec(angle, z float64) []float64 {
	return ident.Normalize([]float64{math.Cos(angle), math.Sin(angle), z, 0})
}

func TestSummarize(t *testing.T) {
	s := summarize([]float64{0.2, 0.4, 0.6, 0.8})
	if s.N != 4 || s.Min != 0.2 || s.Max != 0.8 {
		t.Fatalf("unexpected stats %+v", s)
	}
	if math.Abs(s.Median-0.5) > 1e-9 || math.Abs(s.Mean-0.5) > 1e-9 {
		t.Fatalf("median/mean wrong: %+v", s)
	}
	if got := summarize(nil); got.N != 0 {
		t.Fatalf("empty summarize should be zero, got %+v", got)
	}
}

func TestRecommendGateSeparable(t *testing.T) {
	r := recommendGate(0.62, 0.35, true, 0.02)
	if !r.Separable || math.Abs(r.Value-0.37) > 1e-9 {
		t.Fatalf("expected separable gate at 0.37, got %+v", r)
	}
}

func TestRecommendGateOverlap(t *testing.T) {
	r := recommendGate(0.40, 0.50, true, 0.02)
	if r.Separable {
		t.Fatalf("expected overlap, got %+v", r)
	}
}

func TestRecommendGateProvisionalWithoutImpostors(t *testing.T) {
	r := recommendGate(0.60, 0, false, 0.02)
	if !r.Separable || math.Abs(r.Value-0.58) > 1e-9 {
		t.Fatalf("unexpected provisional gate %+v", r)
	}
}

func TestAnalyzeCalibrationSeparatesPersonas(t *testing.T) {
	a := calibPersona{id: "a", found: 4, labels: []string{"1", "2", "3", "4"},
		vecs: [][]float64{vec(0.00, 0.1), vec(0.05, 0.1), vec(0.10, 0.1), vec(0.15, 0.1)}}
	b := calibPersona{id: "b", found: 4, labels: []string{"1", "2", "3", "4"},
		vecs: [][]float64{vec(1.5, 0.1), vec(1.55, 0.1), vec(1.6, 0.1), vec(1.65, 0.1)}}
	res := analyzeCalibration([]calibPersona{a, b}, 0.02)
	if len(res) != 2 {
		t.Fatalf("expected 2 results, got %d", len(res))
	}
	pa := res[0]
	if pa.MaxGate == nil || !pa.MaxGate.Separable || !pa.MeanGate.Separable {
		t.Fatalf("clustered personas should be separable: %+v", pa)
	}
	if pa.ImpostorMax.Max >= pa.LeaveOneOutMax.Min {
		t.Fatalf("impostor max %.3f should be below genuine min %.3f", pa.ImpostorMax.Max, pa.LeaveOneOutMax.Min)
	}
	if pa.MaxGate.Value <= pa.ImpostorMax.Max {
		t.Fatalf("gate %.3f must exceed impostor best %.3f", pa.MaxGate.Value, pa.ImpostorMax.Max)
	}
}

func TestAnalyzeCalibrationFewReferencesWarns(t *testing.T) {
	p := calibPersona{id: "solo", found: 2, vecs: [][]float64{vec(0, 0), vec(0.1, 0)}}
	res := analyzeCalibration([]calibPersona{p}, 0.02)
	if res[0].MaxGate != nil || len(res[0].Warnings) == 0 {
		t.Fatalf("expected warning and no recommendation, got %+v", res[0])
	}
}
