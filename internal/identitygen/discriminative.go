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

const (
	DefaultAnchorWeight    = 0.70
	DefaultIdentityMargin  = 0.05
)

type DiscriminativePersonaResult struct {
	PersonaID        string   `json:"persona_id"`
	AnchorLabels     []string `json:"anchor_labels"`
	SupportKept      []string `json:"support_kept"`
	SupportRejected  []string `json:"support_rejected,omitempty"`
	Failures         []string `json:"failures,omitempty"`
	PrototypePath    string   `json:"prototype_path"`
	Dimensions       int      `json:"dimensions"`
	AnchorWeight     float64  `json:"anchor_weight"`
}

type DiscriminativeBuildResult struct {
	OK             bool                          `json:"ok"`
	ReferenceRoot  string                        `json:"reference_root"`
	BankDir        string                        `json:"bank_dir"`
	AnchorWeight   float64                       `json:"anchor_weight"`
	Personas       []DiscriminativePersonaResult `json:"personas"`
}

type discriminativePack struct {
	id      string
	labels  []string
	vecs    [][]float64
	failures []string
}

func isAnchorLabel(label string) bool {
	name := strings.ToLower(filepath.Base(label))
	return strings.HasPrefix(name, "anchor-") || strings.HasPrefix(name, "anchor_")
}

func weightedPrototype(labels []string, vecs [][]float64, anchorWeight float64) ([]float64, []string, []string, error) {
	if len(labels) != len(vecs) || len(vecs) == 0 {
		return nil, nil, nil, fmt.Errorf("labels/embeddings mismatch or empty pack")
	}
	if anchorWeight <= 0 || anchorWeight >= 1 {
		anchorWeight = DefaultAnchorWeight
	}
	var anchors, supports []int
	for i, label := range labels {
		if isAnchorLabel(label) {
			anchors = append(anchors, i)
		} else {
			supports = append(supports, i)
		}
	}
	if len(anchors) == 0 {
		return nil, nil, nil, fmt.Errorf("no anchor-* reference found")
	}
	dim := len(vecs[anchors[0]])
	if dim == 0 {
		return nil, nil, nil, fmt.Errorf("empty anchor embedding")
	}
	out := make([]float64, dim)
	addGroup := func(indices []int, totalWeight float64) {
		if len(indices) == 0 || totalWeight <= 0 {
			return
		}
		w := totalWeight / float64(len(indices))
		for _, idx := range indices {
			if len(vecs[idx]) != dim {
				continue
			}
			for j, v := range vecs[idx] {
				out[j] += w * v
			}
		}
	}
	if len(supports) == 0 {
		addGroup(anchors, 1)
	} else {
		addGroup(anchors, anchorWeight)
		addGroup(supports, 1-anchorWeight)
	}
	proto := ident.Normalize(out)
	if len(proto) == 0 {
		return nil, nil, nil, fmt.Errorf("prototype normalization failed")
	}
	anchorLabels := make([]string, 0, len(anchors))
	supportLabels := make([]string, 0, len(supports))
	for _, i := range anchors { anchorLabels = append(anchorLabels, labels[i]) }
	for _, i := range supports { supportLabels = append(supportLabels, labels[i]) }
	return proto, anchorLabels, supportLabels, nil
}

func anchorPrototype(labels []string, vecs [][]float64) ([]float64, error) {
	var refs []referenceEmbedding
	for i, label := range labels {
		if isAnchorLabel(label) && i < len(vecs) {
			refs = append(refs, referenceEmbedding{index:i, vec:vecs[i]})
		}
	}
	if len(refs) == 0 {
		return nil, fmt.Errorf("no anchor-* reference found")
	}
	return referenceCentroid(refs)
}

func nearestForeignScore(vec []float64, ownID string, prototypes map[string][]float64) (string, float64) {
	bestID := ""
	best := math.Inf(-1)
	for id, proto := range prototypes {
		if id == ownID || len(proto) == 0 {
			continue
		}
		s, err := ident.Cosine(vec, proto)
		if err == nil && s > best {
			best = s
			bestID = id
		}
	}
	if bestID == "" {
		return "", 0
	}
	return bestID, best
}

func pruneSupports(pack discriminativePack, anchorPrototypes map[string][]float64) ([]string, [][]float64, []string, []string, error) {
	own := anchorPrototypes[pack.id]
	if len(own) == 0 {
		return nil, nil, nil, nil, fmt.Errorf("%s has no anchor prototype", pack.id)
	}
	labels := make([]string, 0, len(pack.labels))
	vecs := make([][]float64, 0, len(pack.vecs))
	var kept, rejected []string
	for i, label := range pack.labels {
		if i >= len(pack.vecs) {
			continue
		}
		vec := pack.vecs[i]
		if isAnchorLabel(label) {
			labels = append(labels, label)
			vecs = append(vecs, vec)
			continue
		}
		ownScore, err := ident.Cosine(vec, own)
		if err != nil {
			rejected = append(rejected, label)
			continue
		}
		_, foreignScore := nearestForeignScore(vec, pack.id, anchorPrototypes)
		if ownScore > foreignScore {
			labels = append(labels, label)
			vecs = append(vecs, vec)
			kept = append(kept, label)
		} else {
			rejected = append(rejected, label)
		}
	}
	sort.Strings(kept)
	sort.Strings(rejected)
	return labels, vecs, kept, rejected, nil
}

func BuildDiscriminativeBanks(ctx context.Context, referenceRoot, bankDir string, anchorWeight float64) (DiscriminativeBuildResult, error) {
	if strings.TrimSpace(referenceRoot) == "" {
		referenceRoot = filepath.Join("data", "references")
	}
	if strings.TrimSpace(bankDir) == "" {
		bankDir = "personas"
	}
	if anchorWeight <= 0 || anchorWeight >= 1 {
		anchorWeight = DefaultAnchorWeight
	}
	ids, err := discoverPersonas(referenceRoot)
	if err != nil {
		return DiscriminativeBuildResult{}, err
	}
	filtered := ids[:0]
	for _, id := range ids {
		if !strings.HasPrefix(id, "_") {
			filtered = append(filtered, id)
		}
	}
	ids = filtered
	if len(ids) == 0 {
		return DiscriminativeBuildResult{}, fmt.Errorf("no persona reference directories under %s", referenceRoot)
	}
	m := nativecore.FromEnv()
	packs := make([]discriminativePack, 0, len(ids))
	for _, id := range ids {
		refs, paths, err := loadReferences(referenceRoot, id)
		if err != nil {
			return DiscriminativeBuildResult{}, fmt.Errorf("load %s: %w", id, err)
		}
		embedded, failures := embedReferences(ctx, m, refs, paths)
		pack := discriminativePack{id:id, failures:failures}
		for _, e := range embedded {
			if e.index < 0 || e.index >= len(paths) {
				continue
			}
			pack.labels = append(pack.labels, filepath.Base(paths[e.index]))
			pack.vecs = append(pack.vecs, e.vec)
		}
		if len(pack.vecs) == 0 {
			return DiscriminativeBuildResult{}, fmt.Errorf("%s has no usable embeddings", id)
		}
		packs = append(packs, pack)
	}

	anchorProtos := map[string][]float64{}
	for _, p := range packs {
		v, err := anchorPrototype(p.labels, p.vecs)
		if err != nil {
			// Backward compatibility for a persona such as the existing
			// verified Celeste pack: use its full-pack centroid until it gets
			// an explicit anchor-* image.
			refs := make([]referenceEmbedding, 0, len(p.vecs))
			for i, v := range p.vecs { refs = append(refs, referenceEmbedding{index:i, vec:v}) }
			v, err = referenceCentroid(refs)
			if err != nil { return DiscriminativeBuildResult{}, fmt.Errorf("%s prototype: %w", p.id, err) }
		}
		anchorProtos[p.id] = v
	}

	if err := os.MkdirAll(bankDir, 0o755); err != nil {
		return DiscriminativeBuildResult{}, err
	}
	out := DiscriminativeBuildResult{
		ReferenceRoot:referenceRoot, BankDir:bankDir, AnchorWeight:anchorWeight,
	}
	for _, p := range packs {
		labels, vecs, kept, rejected, err := pruneSupports(p, anchorProtos)
		if err != nil { return DiscriminativeBuildResult{}, err }
		proto, anchorLabels, _, err := weightedPrototype(labels, vecs, anchorWeight)
		if err != nil {
			// If this persona has no explicit anchor, retain its clean legacy
			// centroid (Celeste) rather than failing the whole rebuild.
			refs := make([]referenceEmbedding, 0, len(vecs))
			for i, v := range vecs { refs = append(refs, referenceEmbedding{index:i, vec:v}) }
			proto, err = referenceCentroid(refs)
			if err != nil { return DiscriminativeBuildResult{}, err }
			anchorLabels = nil
		}

		bank := ident.NewPersonaBank("arcface-r50")
		vec32 := make([]float32, len(proto))
		for i, v := range proto { vec32[i] = float32(v) }
		meta := map[string]any{
			"source":"anchor-weighted-discriminative-prototype",
			"anchor_weight":anchorWeight,
			"anchors":anchorLabels,
			"support_kept":kept,
			"support_rejected":rejected,
			"alignment":"scrfd-5pt-112",
		}
		if len(anchorLabels) == 0 {
			meta["source"] = "legacy-centroid-no-explicit-anchor"
		}
		if err := bank.AddPersona(ident.PersonaEmbedding{ID:p.id, Name:p.id, Embedding:vec32, Metadata:meta}); err != nil {
			return DiscriminativeBuildResult{}, err
		}
		path := filepath.Join(bankDir, p.id+".safetensors")
		if err := bank.WriteFile(path); err != nil {
			return DiscriminativeBuildResult{}, err
		}
		out.Personas = append(out.Personas, DiscriminativePersonaResult{
			PersonaID:p.id, AnchorLabels:anchorLabels, SupportKept:kept,
			SupportRejected:rejected, Failures:p.failures, PrototypePath:path,
			Dimensions:len(proto), AnchorWeight:anchorWeight,
		})
	}
	out.OK = true
	return out, nil
}

type PrototypeScore struct {
	OwnScore            float64 `json:"own_score"`
	NearestOtherScore   float64 `json:"nearest_other_score,omitempty"`
	NearestOtherPersona string  `json:"nearest_other_persona,omitempty"`
	Margin              float64 `json:"margin"`
	MarginThreshold     float64 `json:"margin_threshold"`
	Passed              bool    `json:"passed"`
}

func ScorePrototypeMargin(vec []float64, personaID string, own []float64, others map[string][]float64, marginThreshold float64) (PrototypeScore, error) {
	if marginThreshold <= 0 {
		marginThreshold = DefaultIdentityMargin
	}
	ownScore, err := ident.Cosine(vec, own)
	if err != nil {
		return PrototypeScore{}, err
	}
	otherID, otherScore := nearestForeignScore(vec, personaID, others)
	margin := ownScore
	if otherID != "" {
		margin = ownScore - otherScore
	}
	return PrototypeScore{
		OwnScore:ownScore, NearestOtherScore:otherScore, NearestOtherPersona:otherID,
		Margin:margin, MarginThreshold:marginThreshold,
		Passed:otherID == "" || margin >= marginThreshold,
	}, nil
}

func LoadDiscriminativePrototypes(bankDir string) (map[string][]float64, error) {
	if strings.TrimSpace(bankDir) == "" { bankDir = "personas" }
	entries, err := os.ReadDir(bankDir)
	if err != nil { return nil, err }
	out := map[string][]float64{}
	for _, e := range entries {
		if e.IsDir() || strings.ToLower(filepath.Ext(e.Name())) != ".safetensors" { continue }
		id := strings.TrimSuffix(e.Name(), filepath.Ext(e.Name()))
		bank, err := ident.LoadFile(filepath.Join(bankDir, e.Name()))
		if err != nil { continue }
		vec32, ok := bank.Tensors[id]
		if !ok || len(vec32) == 0 { continue }
		vec := make([]float64, len(vec32))
		for i, v := range vec32 { vec[i] = float64(v) }
		out[id] = ident.Normalize(vec)
	}
	if len(out) == 0 { return nil, fmt.Errorf("no persona prototypes in %s", bankDir) }
	return out, nil
}
