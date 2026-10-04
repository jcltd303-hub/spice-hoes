package identitygen

import (
	"math"
	"testing"
)

func almost(a, b float64) bool { return math.Abs(a-b) < 1e-6 }

func TestWeightedPrototypeFavorsCanonicalAnchor(t *testing.T) {
	labels := []string{"anchor-01.jpg", "support-a.jpg", "support-b.jpg"}
	vecs := [][]float64{
		{1, 0},
		{0, 1},
		{0, 1},
	}
	got, anchors, supports, err := weightedPrototype(labels, vecs, 0.70)
	if err != nil { t.Fatal(err) }
	if len(anchors) != 1 || len(supports) != 2 { t.Fatalf("unexpected groups: %v %v", anchors, supports) }
	if got[0] <= got[1] {
		t.Fatalf("anchor must dominate prototype, got %v", got)
	}
}

func TestPruneSupportsRejectsForeignCloserReference(t *testing.T) {
	pack := discriminativePack{
		id:"alpha",
		labels:[]string{"anchor-01.jpg","good.jpg","contaminated.jpg"},
		vecs:[][]float64{{1,0},{0.95,0.05},{0.05,0.95}},
	}
	protos := map[string][]float64{
		"alpha":{1,0},
		"beta":{0,1},
	}
	labels, _, kept, rejected, err := pruneSupports(pack, protos)
	if err != nil { t.Fatal(err) }
	if len(labels) != 2 { t.Fatalf("expected anchor + one support, got %v", labels) }
	if len(kept) != 1 || kept[0] != "good.jpg" { t.Fatalf("unexpected kept: %v", kept) }
	if len(rejected) != 1 || rejected[0] != "contaminated.jpg" { t.Fatalf("unexpected rejected: %v", rejected) }
}

func TestScorePrototypeMargin(t *testing.T) {
	others := map[string][]float64{"alpha":{1,0}, "beta":{0,1}}
	s, err := ScorePrototypeMargin([]float64{0.98,0.02}, "alpha", []float64{1,0}, others, 0.05)
	if err != nil { t.Fatal(err) }
	if !s.Passed { t.Fatalf("expected pass: %+v", s) }
	if s.NearestOtherPersona != "beta" { t.Fatalf("unexpected nearest other: %s", s.NearestOtherPersona) }
	if s.Margin <= 0.05 { t.Fatalf("expected healthy margin: %+v", s) }

	s, err = ScorePrototypeMargin([]float64{0.7,0.7}, "alpha", []float64{1,0}, others, 0.05)
	if err != nil { t.Fatal(err) }
	if s.Passed { t.Fatalf("ambiguous vector should fail margin gate: %+v", s) }
	if !almost(s.Margin, 0) { t.Fatalf("expected near-zero margin, got %f", s.Margin) }
}
