package identitygen

import (
	"context"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

// CalibrateRequest asks for an empirical identity-gate calibration built from
// the reference packs already on disk. It needs no image generation.
type CalibrateRequest struct {
	ReferenceRoot string              `json:"reference_root,omitempty"` // default data/references
	PersonaIDs    []string            `json:"persona_ids,omitempty"`    // default: every subdirectory of ReferenceRoot
	Margin        float64             `json:"margin,omitempty"`         // safety margin around the impostor ceiling, default 0.02
	Progress      func(ProgressEvent) `json:"-"`
}

// DistStats summarises a set of cosine similarities.
type DistStats struct {
	N      int     `json:"n"`
	Min    float64 `json:"min"`
	P10    float64 `json:"p10"`
	Median float64 `json:"median"`
	Mean   float64 `json:"mean"`
	P90    float64 `json:"p90"`
	Max    float64 `json:"max"`
}

// GateRecommendation is a suggested threshold with the reasoning behind it.
type GateRecommendation struct {
	Value     float64 `json:"value"`
	Separable bool    `json:"separable"` // false: genuine and impostor ranges overlap
	Basis     string  `json:"basis"`
}

type PersonaCalibration struct {
	PersonaID       string      `json:"persona_id"`
	ReferencesFound int         `json:"references_found"`
	ReferencesUsed  int         `json:"references_used"`
	Skipped         []string    `json:"skipped,omitempty"`
	Labels          []string    `json:"labels,omitempty"`
	Matrix          [][]float64 `json:"pairwise_cosine,omitempty"`

	// Genuine: every pair of this persona's own references.
	GenuinePairs DistStats `json:"genuine_pairs"`
	// Leave-one-out: each reference scored against the others, using the same
	// max/mean statistics the generation gate uses. This is what a perfect
	// same-identity image would score without the reference scoring itself.
	LeaveOneOutMax  DistStats `json:"leave_one_out_max"`
	LeaveOneOutMean DistStats `json:"leave_one_out_mean"`
	// Impostor: other personas' references scored against this persona's pack.
	ImpostorMax  DistStats `json:"impostor_max"`
	ImpostorMean DistStats `json:"impostor_mean"`

	MaxGate  *GateRecommendation `json:"recommended_max_gate,omitempty"`
	MeanGate *GateRecommendation `json:"recommended_mean_gate,omitempty"`
	Warnings []string            `json:"warnings,omitempty"`
}

type CalibrateResult struct {
	OK            bool                 `json:"ok"`
	ReferenceRoot string               `json:"reference_root"`
	Model         string               `json:"model"`
	Margin        float64              `json:"margin"`
	Personas      []PersonaCalibration `json:"personas"`
	Notes         []string             `json:"notes"`
}

type calibPersona struct {
	id      string
	found   int
	labels  []string // label per embedded reference
	vecs    [][]float64
	skipped []string
}

func discoverPersonas(root string) ([]string, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, err
	}
	ids := []string{}
	for _, e := range entries {
		if e.IsDir() {
			ids = append(ids, e.Name())
		}
	}
	sort.Strings(ids)
	return ids, nil
}

// Calibrate embeds every persona's reference pack with the production
// SCRFD + ArcFace path and reports the real score distributions.
func Calibrate(ctx context.Context, req CalibrateRequest) (CalibrateResult, error) {
	if req.ReferenceRoot == "" {
		req.ReferenceRoot = filepath.Join("data", "references")
	}
	if req.Margin <= 0 {
		req.Margin = 0.02
	}
	ids := req.PersonaIDs
	if len(ids) == 0 {
		var err error
		if ids, err = discoverPersonas(req.ReferenceRoot); err != nil {
			return CalibrateResult{}, fmt.Errorf("list reference root: %w", err)
		}
	}
	if len(ids) == 0 {
		return CalibrateResult{}, fmt.Errorf("no persona reference directories under %s", req.ReferenceRoot)
	}

	m := nativecore.FromEnv()
	personas := make([]calibPersona, 0, len(ids))
	for n, id := range ids {
		emitProgress(Request{Progress: req.Progress}, 5+85*float64(n)/float64(len(ids)), "embedding references", map[string]any{"persona": id})
		refs, paths, err := loadReferences(req.ReferenceRoot, id)
		if err != nil {
			return CalibrateResult{}, fmt.Errorf("load references for %s: %w", id, err)
		}
		cp := calibPersona{id: id, found: len(refs)}
		for i, ref := range refs {
			vec, _, err := arcEmbedding(ctx, m, ref)
			if err != nil {
				cp.skipped = append(cp.skipped, fmt.Sprintf("%s: %v", filepath.Base(paths[i]), err))
				continue
			}
			cp.labels = append(cp.labels, filepath.Base(paths[i]))
			cp.vecs = append(cp.vecs, vec)
		}
		personas = append(personas, cp)
	}

	out := CalibrateResult{
		OK:            true,
		ReferenceRoot: req.ReferenceRoot,
		Model:         "arcface-w600k-r50-qnn",
		Margin:        req.Margin,
		Personas:      analyzeCalibration(personas, req.Margin),
		Notes: []string{
			"Scores use the production SCRFD 5-point alignment + ArcFace embedding path.",
			"Leave-one-out and impostor statistics never score a reference against itself, unlike the generation gate when the swap source is also in the reference set.",
			"The generation gate uses all references, so real runs have one more reference than leave-one-out; expect slightly higher max and similar mean.",
			"Recommendations are provisional until each persona has at least four usable references and at least one other persona to act as impostor.",
		},
	}
	emitProgress(Request{Progress: req.Progress}, 100, "calibration complete", nil)
	return out, nil
}

// maxMeanAgainst returns the max and mean cosine of vec against pack,
// skipping index skip (-1 for none).
func maxMeanAgainst(vec []float64, pack [][]float64, skip int) (float64, float64, bool) {
	best, sum, n := math.Inf(-1), 0.0, 0
	for i, p := range pack {
		if i == skip {
			continue
		}
		s, err := ident.Cosine(vec, p)
		if err != nil {
			continue
		}
		if s > best {
			best = s
		}
		sum += s
		n++
	}
	if n == 0 {
		return 0, 0, false
	}
	return best, sum / float64(n), true
}

func percentile(sorted []float64, q float64) float64 {
	if len(sorted) == 1 {
		return sorted[0]
	}
	pos := q * float64(len(sorted)-1)
	lo, hi := int(math.Floor(pos)), int(math.Ceil(pos))
	if lo == hi {
		return sorted[lo]
	}
	f := pos - float64(lo)
	return sorted[lo]*(1-f) + sorted[hi]*f
}

func summarize(vals []float64) DistStats {
	if len(vals) == 0 {
		return DistStats{}
	}
	s := append([]float64(nil), vals...)
	sort.Float64s(s)
	sum := 0.0
	for _, v := range s {
		sum += v
	}
	return DistStats{
		N: len(s), Min: s[0], P10: percentile(s, 0.10), Median: percentile(s, 0.5),
		Mean: sum / float64(len(s)), P90: percentile(s, 0.90), Max: s[len(s)-1],
	}
}

func round3(v float64) float64 { return math.Round(v*1000) / 1000 }

// recommendGate picks a threshold between the worst genuine score and the
// best impostor score. genuineWorst is the lowest leave-one-out score a real
// same-identity reference achieved; impostorBest is the highest score any
// other persona's reference achieved against this pack.
func recommendGate(genuineWorst, impostorBest float64, haveImpostor bool, margin float64) GateRecommendation {
	if !haveImpostor {
		return GateRecommendation{
			Value: round3(genuineWorst - margin), Separable: true,
			Basis: "provisional: worst real same-identity reference minus margin; no other persona available to measure impostor scores",
		}
	}
	floor := impostorBest + margin
	if floor <= genuineWorst {
		return GateRecommendation{
			Value: round3(floor), Separable: true,
			Basis: "lowest gate that rejects every impostor reference with margin while accepting every real reference",
		}
	}
	return GateRecommendation{
		Value: round3((floor + genuineWorst) / 2), Separable: false,
		Basis: "genuine and impostor ranges overlap; midpoint shown but this gate cannot cleanly separate these personas",
	}
}

func analyzeCalibration(personas []calibPersona, margin float64) []PersonaCalibration {
	results := make([]PersonaCalibration, 0, len(personas))
	for pi, p := range personas {
		pc := PersonaCalibration{
			PersonaID: p.id, ReferencesFound: p.found, ReferencesUsed: len(p.vecs),
			Skipped: p.skipped, Labels: p.labels,
		}
		if p.found == 0 {
			pc.Warnings = append(pc.Warnings, "no usable reference images found (master_*, contact_* and *_rear files are ignored)")
		}
		if len(p.skipped) > 0 {
			pc.Warnings = append(pc.Warnings, fmt.Sprintf("%d reference(s) failed face detection/embedding and are excluded from the gate; see skipped", len(p.skipped)))
		}
		if len(p.vecs) < 3 {
			pc.Warnings = append(pc.Warnings, "fewer than 3 usable references: leave-one-out mean is not meaningful; add references before trusting any threshold")
			results = append(results, pc)
			continue
		}

		pc.Matrix = make([][]float64, len(p.vecs))
		pairs := []float64{}
		for i := range p.vecs {
			pc.Matrix[i] = make([]float64, len(p.vecs))
			for j := range p.vecs {
				s, err := ident.Cosine(p.vecs[i], p.vecs[j])
				if err != nil {
					continue
				}
				pc.Matrix[i][j] = round3(s)
				if j > i {
					pairs = append(pairs, s)
				}
			}
		}
		pc.GenuinePairs = summarize(pairs)

		looMax, looMean := []float64{}, []float64{}
		for i, v := range p.vecs {
			if mx, mn, ok := maxMeanAgainst(v, p.vecs, i); ok {
				looMax = append(looMax, mx)
				looMean = append(looMean, mn)
			}
		}
		pc.LeaveOneOutMax, pc.LeaveOneOutMean = summarize(looMax), summarize(looMean)

		impMax, impMean := []float64{}, []float64{}
		for oi, o := range personas {
			if oi == pi {
				continue
			}
			for _, v := range o.vecs {
				if mx, mn, ok := maxMeanAgainst(v, p.vecs, -1); ok {
					impMax = append(impMax, mx)
					impMean = append(impMean, mn)
				}
			}
		}
		pc.ImpostorMax, pc.ImpostorMean = summarize(impMax), summarize(impMean)
		haveImp := len(impMax) > 0

		mg := recommendGate(pc.LeaveOneOutMax.Min, pc.ImpostorMax.Max, haveImp, margin)
		mm := recommendGate(pc.LeaveOneOutMean.Min, pc.ImpostorMean.Max, haveImp, margin)
		pc.MaxGate, pc.MeanGate = &mg, &mm
		if !haveImp {
			pc.Warnings = append(pc.Warnings, "no other persona references to act as impostors; thresholds are one-sided")
		}
		if haveImp && (!mg.Separable || !mm.Separable) {
			pc.Warnings = append(pc.Warnings, "real and impostor scores overlap: ArcFace cannot separate this pack from other personas; fix the reference pack (more frontal, consistent references) before tuning thresholds")
		}
		if mg.Value < mm.Value {
			pc.Warnings = append(pc.Warnings, "recommended max gate is below the mean gate; the max gate is then redundant")
		}
		if len(p.vecs) < 4 {
			pc.Warnings = append(pc.Warnings, "only 3 usable references: recommendations are very noisy")
		}
		results = append(results, pc)
	}
	return results
}

// Summary renders a short human-readable block for terminals.
func (r CalibrateResult) Summary() string {
	var b strings.Builder
	for _, p := range r.Personas {
		fmt.Fprintf(&b, "%s: %d/%d refs usable\n", p.PersonaID, p.ReferencesUsed, p.ReferencesFound)
		if p.MaxGate == nil {
			continue
		}
		fmt.Fprintf(&b, "  genuine LOO max  min %.3f median %.3f | mean  min %.3f median %.3f\n",
			p.LeaveOneOutMax.Min, p.LeaveOneOutMax.Median, p.LeaveOneOutMean.Min, p.LeaveOneOutMean.Median)
		if p.ImpostorMax.N > 0 {
			fmt.Fprintf(&b, "  impostor    max  best %.3f            | mean  best %.3f\n", p.ImpostorMax.Max, p.ImpostorMean.Max)
		}
		fmt.Fprintf(&b, "  recommended identity_threshold=%.3f identity_mean_threshold=%.3f\n", p.MaxGate.Value, p.MeanGate.Value)
	}
	return b.String()
}
