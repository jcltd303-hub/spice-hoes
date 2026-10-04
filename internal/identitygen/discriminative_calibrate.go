package identitygen

import (
	"context"
	"fmt"
	"math"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

type DiscriminativeReferenceScore struct {
	Label               string  `json:"label"`
	Anchor              bool    `json:"anchor"`
	OwnScore            float64 `json:"own_score"`
	NearestOtherScore   float64 `json:"nearest_other_score"`
	NearestOtherPersona string  `json:"nearest_other_persona"`
	Margin              float64 `json:"margin"`
	Passed              bool    `json:"passed"`
}

type DiscriminativeCalibrationPersona struct {
	PersonaID           string                         `json:"persona_id"`
	ReferencesUsed      int                            `json:"references_used"`
	Failures            []string                       `json:"failures,omitempty"`
	Scores              []DiscriminativeReferenceScore `json:"scores"`
	WorstOwnScore       float64                        `json:"worst_own_score"`
	WorstMargin         float64                        `json:"worst_margin"`
	RecommendedOwnGate  float64                        `json:"recommended_own_gate"`
	RecommendedMargin   float64                        `json:"recommended_margin"`
	Separable           bool                           `json:"separable"`
}

type DiscriminativeCalibrationResult struct {
	OK              bool                                `json:"ok"`
	ReferenceRoot   string                              `json:"reference_root"`
	BankDir         string                              `json:"bank_dir"`
	MarginThreshold float64                             `json:"margin_threshold"`
	Personas        []DiscriminativeCalibrationPersona `json:"personas"`
}

func CalibrateDiscriminativeBanks(ctx context.Context, referenceRoot, bankDir string, marginThreshold float64) (DiscriminativeCalibrationResult, error) {
	if strings.TrimSpace(referenceRoot) == "" { referenceRoot = filepath.Join("data","references") }
	if strings.TrimSpace(bankDir) == "" { bankDir = "personas" }
	if marginThreshold <= 0 { marginThreshold = DefaultIdentityMargin }

	protos, err := LoadDiscriminativePrototypes(bankDir)
	if err != nil { return DiscriminativeCalibrationResult{}, err }

	ids := make([]string, 0, len(protos))
	for id := range protos { ids = append(ids, id) }
	sort.Strings(ids)

	m := nativecore.FromEnv()
	out := DiscriminativeCalibrationResult{
		ReferenceRoot:referenceRoot, BankDir:bankDir, MarginThreshold:marginThreshold,
	}

	for _, id := range ids {
		refs, paths, err := loadReferences(referenceRoot, id)
		if err != nil { return DiscriminativeCalibrationResult{}, fmt.Errorf("load %s: %w", id, err) }
		embedded, failures := embedReferences(ctx, m, refs, paths)
		pc := DiscriminativeCalibrationPersona{
			PersonaID:id, Failures:failures, WorstOwnScore:math.Inf(1), WorstMargin:math.Inf(1),
		}
		for _, e := range embedded {
			if e.index < 0 || e.index >= len(paths) { continue }
			ps, err := ScorePrototypeMargin(e.vec, id, protos[id], protos, marginThreshold)
			if err != nil { continue }
			label := filepath.Base(paths[e.index])
			pc.Scores = append(pc.Scores, DiscriminativeReferenceScore{
				Label:label, Anchor:isAnchorLabel(label),
				OwnScore:ps.OwnScore, NearestOtherScore:ps.NearestOtherScore,
				NearestOtherPersona:ps.NearestOtherPersona, Margin:ps.Margin, Passed:ps.Passed,
			})
			if ps.OwnScore < pc.WorstOwnScore { pc.WorstOwnScore = ps.OwnScore }
			if ps.Margin < pc.WorstMargin { pc.WorstMargin = ps.Margin }
		}
		pc.ReferencesUsed = len(pc.Scores)
		if pc.ReferencesUsed == 0 {
			pc.WorstOwnScore = 0
			pc.WorstMargin = 0
			pc.Separable = false
		} else {
			pc.RecommendedOwnGate = round3(math.Max(0, pc.WorstOwnScore-0.02))
			pc.RecommendedMargin = round3(math.Max(0.01, math.Min(marginThreshold, pc.WorstMargin-0.01)))
			pc.Separable = pc.WorstMargin > 0
		}
		sort.Slice(pc.Scores, func(i,j int) bool {
			if pc.Scores[i].Anchor != pc.Scores[j].Anchor { return pc.Scores[i].Anchor }
			return pc.Scores[i].Margin < pc.Scores[j].Margin
		})
		out.Personas = append(out.Personas, pc)
	}
	out.OK = true
	return out, nil
}
