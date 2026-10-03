package identitygen

import (
	"context"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

type RepairPackResult struct {
	PersonaID        string   `json:"persona_id"`
	Original         []string `json:"original"`
	Kept             []string `json:"kept"`
	Quarantined      []string `json:"quarantined,omitempty"`
	BeforeMaxMargin  float64  `json:"before_max_margin"`
	BeforeMeanMargin float64  `json:"before_mean_margin"`
	AfterMaxMargin   float64  `json:"after_max_margin"`
	AfterMeanMargin  float64  `json:"after_mean_margin"`
	Separable        bool     `json:"separable"`
	BankPath         string   `json:"bank_path,omitempty"`
}

type RepairResult struct {
	OK            bool               `json:"ok"`
	Applied       bool               `json:"applied"`
	ReferenceRoot string             `json:"reference_root"`
	QuarantineDir string             `json:"quarantine_dir,omitempty"`
	Packs         []RepairPackResult `json:"packs"`
	Calibration   CalibrateResult    `json:"calibration"`
}

type repairSubsetScore struct {
	idxs       []int
	maxMargin  float64
	meanMargin float64
	minMargin  float64
	separable  bool
}

func subsetMetrics(pack [][]float64, impostors [][]float64, idxs []int) (float64, float64, bool) {
	if len(idxs) < 3 {
		return math.Inf(-1), math.Inf(-1), false
	}
	genuineMaxWorst := math.Inf(1)
	genuineMeanWorst := math.Inf(1)
	for _, idx := range idxs {
		v := pack[idx]
		best := math.Inf(-1)
		sum, n := 0.0, 0
		for _, j := range idxs {
			if j == idx {
				continue
			}
			s, ok := cosineSafe(v, pack[j])
			if !ok {
				continue
			}
			if s > best {
				best = s
			}
			sum += s
			n++
		}
		if n == 0 {
			return math.Inf(-1), math.Inf(-1), false
		}
		mean := sum / float64(n)
		if best < genuineMaxWorst {
			genuineMaxWorst = best
		}
		if mean < genuineMeanWorst {
			genuineMeanWorst = mean
		}
	}

	impostorMaxBest := math.Inf(-1)
	impostorMeanBest := math.Inf(-1)
	if len(impostors) == 0 {
		return genuineMaxWorst, genuineMeanWorst, true
	}
	for _, v := range impostors {
		best := math.Inf(-1)
		sum, n := 0.0, 0
		for _, j := range idxs {
			s, ok := cosineSafe(v, pack[j])
			if !ok {
				continue
			}
			if s > best {
				best = s
			}
			sum += s
			n++
		}
		if n == 0 {
			continue
		}
		mean := sum / float64(n)
		if best > impostorMaxBest {
			impostorMaxBest = best
		}
		if mean > impostorMeanBest {
			impostorMeanBest = mean
		}
	}
	return genuineMaxWorst - impostorMaxBest, genuineMeanWorst - impostorMeanBest, true
}

func cosineSafe(a, b []float64) (float64, bool) {
	if len(a) == 0 || len(a) != len(b) {
		return 0, false
	}
	sumAB, sumAA, sumBB := 0.0, 0.0, 0.0
	for i := range a {
		sumAB += a[i] * b[i]
		sumAA += a[i] * a[i]
		sumBB += b[i] * b[i]
	}
	if sumAA == 0 || sumBB == 0 {
		return 0, false
	}
	return sumAB / math.Sqrt(sumAA*sumBB), true
}

func allSubsets(n, minKeep int) [][]int {
	var out [][]int
	limit := 1 << n
	for mask := 0; mask < limit; mask++ {
		idxs := make([]int, 0, n)
		for i := 0; i < n; i++ {
			if mask&(1<<i) != 0 {
				idxs = append(idxs, i)
			}
		}
		if len(idxs) >= minKeep {
			out = append(out, idxs)
		}
	}
	return out
}

func betterRepairScore(a, b repairSubsetScore) bool {
	if a.separable != b.separable {
		return a.separable
	}
	if a.minMargin != b.minMargin {
		return a.minMargin > b.minMargin
	}
	if len(a.idxs) != len(b.idxs) {
		return len(a.idxs) > len(b.idxs)
	}
	if a.meanMargin != b.meanMargin {
		return a.meanMargin > b.meanMargin
	}
	return a.maxMargin > b.maxMargin
}

func RepairIdentityPacks(ctx context.Context, root string, apply bool) (RepairResult, error) {
	if strings.TrimSpace(root) == "" {
		root = filepath.Join("data", "references")
	}
	ids, err := discoverPersonas(root)
	if err != nil {
		return RepairResult{}, err
	}

	m := nativecore.FromEnv()
	personas := make([]calibPersona, 0, len(ids))
	for _, id := range ids {
		refs, paths, err := loadReferences(root, id)
		if err != nil {
			return RepairResult{}, fmt.Errorf("load %s: %w", id, err)
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

	stamp := time.Now().UTC().Format("20060102T150405Z")
	quarantineRoot := filepath.Join(root, "_quarantine", stamp)
	result := RepairResult{ReferenceRoot: root, Applied: apply, QuarantineDir: quarantineRoot}

	for pi, p := range personas {
		if strings.HasPrefix(p.id, "_") || len(p.vecs) < 3 {
			continue
		}

		var impostors [][]float64
		for oi, o := range personas {
			if oi == pi || strings.HasPrefix(o.id, "_") {
				continue
			}
			impostors = append(impostors, o.vecs...)
		}

		all := make([]int, len(p.vecs))
		for i := range all {
			all[i] = i
		}
		beforeMax, beforeMean, _ := subsetMetrics(p.vecs, impostors, all)

		best := repairSubsetScore{
			idxs:       all,
			maxMargin:  beforeMax,
			meanMargin: beforeMean,
			minMargin:  math.Min(beforeMax, beforeMean),
			separable:  beforeMax > 0 && beforeMean > 0,
		}
		for _, idxs := range allSubsets(len(p.vecs), 3) {
			mx, mn, ok := subsetMetrics(p.vecs, impostors, idxs)
			if !ok {
				continue
			}
			candidate := repairSubsetScore{
				idxs:       idxs,
				maxMargin:  mx,
				meanMargin: mn,
				minMargin:  math.Min(mx, mn),
				separable:  mx > 0 && mn > 0,
			}
			if betterRepairScore(candidate, best) {
				best = candidate
			}
		}

		keepSet := map[int]bool{}
		for _, i := range best.idxs {
			keepSet[i] = true
		}
		packResult := RepairPackResult{
			PersonaID:        p.id,
			Original:         append([]string(nil), p.labels...),
			BeforeMaxMargin:  beforeMax,
			BeforeMeanMargin: beforeMean,
			AfterMaxMargin:   best.maxMargin,
			AfterMeanMargin:  best.meanMargin,
			Separable:        best.separable,
			BankPath:         filepath.Join("personas", p.id+".safetensors"),
		}
		for i, label := range p.labels {
			if keepSet[i] {
				packResult.Kept = append(packResult.Kept, label)
			} else {
				packResult.Quarantined = append(packResult.Quarantined, label)
			}
		}
		sort.Strings(packResult.Kept)
		sort.Strings(packResult.Quarantined)

		if apply && len(packResult.Quarantined) > 0 {
			destDir := filepath.Join(quarantineRoot, p.id)
			if err := os.MkdirAll(destDir, 0o755); err != nil {
				return RepairResult{}, err
			}
			for _, label := range packResult.Quarantined {
				src := filepath.Join(root, p.id, label)
				dst := filepath.Join(destDir, label)
				if err := os.Rename(src, dst); err != nil {
					return RepairResult{}, fmt.Errorf("quarantine %s: %w", src, err)
				}
			}
		}

		if apply {
			if _, err := BuildPersonaBankFromReferences(ctx, p.id, root, packResult.BankPath); err != nil {
				return RepairResult{}, fmt.Errorf("rebuild %s bank: %w", p.id, err)
			}
		}
		result.Packs = append(result.Packs, packResult)
	}

	cal, err := Calibrate(ctx, CalibrateRequest{ReferenceRoot: root})
	if err != nil {
		return RepairResult{}, err
	}
	result.Calibration = cal
	result.OK = true
	return result, nil
}
