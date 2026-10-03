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

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

type AnchorCandidate struct {
	PersonaID   string  `json:"persona_id"`
	AssetPath   string  `json:"asset_path"`
	Seed        int64   `json:"seed"`
	OwnScore    float64 `json:"own_score"`
	OtherScore  float64 `json:"other_score"`
	Margin      float64 `json:"margin"`
	Quality     float64 `json:"quality"`
}

type AnchorFixPersona struct {
	PersonaID string            `json:"persona_id"`
	Generated int               `json:"generated"`
	Selected  []AnchorCandidate `json:"selected"`
}

type AnchorFixResult struct {
	OK       bool               `json:"ok"`
	Applied  bool               `json:"applied"`
	Attempts int                `json:"attempts_per_persona"`
	Keep     int                `json:"keep_per_persona"`
	Personas []AnchorFixPersona `json:"personas"`
}

func bankVectorForPersona(personaID string) ([]float64, error) {
	req := Request{PersonaBank: filepath.Join("personas", personaID+".safetensors"), RequirePersonaBank: true}
	vec, _, err := loadPersonaBankEmbedding(req, personaID)
	return vec, err
}

func AnchorFix(ctx context.Context, personaIDs []string, attempts, keep int, apply bool) (AnchorFixResult, error) {
	if attempts < 1 { attempts = 4 }
	if attempts > 12 { attempts = 12 }
	if keep < 3 { keep = 3 }
	if keep > attempts { keep = attempts }
	if len(personaIDs) == 0 {
		personaIDs = []string{"lila_hart","ruby_wren","tess_wilder","zara_voss"}
	}

	allIDs := []string{"celeste_vale","lila_hart","ruby_wren","tess_wilder","zara_voss"}
	banks := map[string][]float64{}
	for _, id := range allIDs {
		vec, err := bankVectorForPersona(id)
		if err != nil { return AnchorFixResult{}, fmt.Errorf("load %s bank: %w", id, err) }
		banks[id] = vec
	}

	m := nativecore.FromEnv()
	result := AnchorFixResult{Applied:apply, Attempts:attempts, Keep:keep}
	stamp := time.Now().UTC().Format("20060102T150405Z")

	for _, personaID := range personaIDs {
		own := banks[personaID]
		if len(own) == 0 { return AnchorFixResult{}, fmt.Errorf("empty bank for %s", personaID) }

		candidates := make([]AnchorCandidate, 0, attempts)
		baseSeed := time.Now().UnixNano()
		for i := 0; i < attempts; i++ {
			stop := false
			saveAll := false
			req := Request{
				PersonaID: personaID,
				Theme: "identity reference portrait, distinctive canonical face",
				Scene: "clean editorial head-and-shoulders portrait, neutral expression, face unobscured, direct camera, even realistic lighting",
				Seed: baseSeed + int64(i),
				IdentityThreshold: -1,
				IdentityMeanThreshold: -1,
				QualityThreshold: 0.76,
				PersonaBank: filepath.Join("personas", personaID+".safetensors"),
				RequirePersonaBank: true,
				BestOfN: 1,
				SwapTopK: 1,
				StopOnAccept: &stop,
				SaveAllAttempts: &saveAll,
			}
			out, err := Run(ctx, req)
			if err != nil { continue }
			raw, err := os.ReadFile(out.AssetPath)
			if err != nil { continue }
			vec, _, err := arcEmbedding(ctx, m, raw)
			if err != nil { continue }

			ownScore, err := ident.Cosine(vec, own)
			if err != nil { continue }
			otherBest := math.Inf(-1)
			for otherID, other := range banks {
				if otherID == personaID { continue }
				s, err := ident.Cosine(vec, other)
				if err == nil && s > otherBest { otherBest = s }
			}
			q := out.Quality.LocalScore
			if q == 0 {
				if mm, err := imagemetrics.Analyze(raw); err == nil { q = mm.LocalScore }
			}
			candidates = append(candidates, AnchorCandidate{
				PersonaID:personaID, AssetPath:out.AssetPath, Seed:req.Seed,
				OwnScore:ownScore, OtherScore:otherBest, Margin:ownScore-otherBest, Quality:q,
			})
		}
		if len(candidates) < keep {
			return AnchorFixResult{}, fmt.Errorf("%s produced only %d usable candidates; need %d", personaID, len(candidates), keep)
		}

		sort.SliceStable(candidates, func(i,j int) bool {
			ai := candidates[i].Margin + 0.10*candidates[i].Quality
			aj := candidates[j].Margin + 0.10*candidates[j].Quality
			if ai != aj { return ai > aj }
			return candidates[i].OwnScore > candidates[j].OwnScore
		})
		selected := append([]AnchorCandidate(nil), candidates[:keep]...)

		if apply {
			refDir := filepath.Join("data","references",personaID)
			holdDir := filepath.Join("data","references","_anchorfix",stamp,personaID)
			if err := os.MkdirAll(holdDir,0o755); err != nil { return AnchorFixResult{}, err }
			entries, _ := os.ReadDir(refDir)
			for _, e := range entries {
				if e.IsDir() { continue }
				ext := strings.ToLower(filepath.Ext(e.Name()))
				if ext != ".png" && ext != ".jpg" && ext != ".jpeg" { continue }
				if err := os.Rename(filepath.Join(refDir,e.Name()), filepath.Join(holdDir,e.Name())); err != nil {
					return AnchorFixResult{}, err
				}
			}
			for i, c := range selected {
				raw, err := os.ReadFile(c.AssetPath)
				if err != nil { return AnchorFixResult{}, err }
				dst := filepath.Join(refDir, fmt.Sprintf("anchor-%02d.png", i+1))
				if err := os.WriteFile(dst, raw, 0o644); err != nil { return AnchorFixResult{}, err }
			}
			if _, err := BuildPersonaBankFromReferences(ctx, personaID, filepath.Join("data","references"), filepath.Join("personas",personaID+".safetensors")); err != nil {
				return AnchorFixResult{}, err
			}
		}

		result.Personas = append(result.Personas, AnchorFixPersona{PersonaID:personaID, Generated:len(candidates), Selected:selected})
	}
	result.OK = true
	return result,nil
}
