package identitygen

import (
	"context"
	"encoding/json"
	"fmt"
	"image"
	"image/draw"
	"image/png"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

type BootstrapAllRequest struct {
	PersonaID         string  `json:"persona_id,omitempty"`
	PersonaDir        string  `json:"persona_dir,omitempty"`
	ReferenceRoot     string  `json:"reference_root,omitempty"`
	OutputRoot        string  `json:"output_root,omitempty"`
	TargetReferences  int     `json:"target_references,omitempty"`
	MaxAttempts       int     `json:"max_attempts,omitempty"`
	Theme             string  `json:"theme,omitempty"`
	Style             string  `json:"style,omitempty"`
	Width             int     `json:"width,omitempty"`
	Height            int     `json:"height,omitempty"`
	Steps             int     `json:"steps,omitempty"`
	Guidance          float64 `json:"guidance,omitempty"`
	IdentityThreshold float64 `json:"identity_threshold,omitempty"`
	IdentityMeanThreshold float64 `json:"identity_mean_threshold,omitempty"`
	QualityThreshold  float64 `json:"quality_threshold,omitempty"`
	Generator         string  `json:"generator,omitempty"`
	Seed              int64   `json:"seed,omitempty"`
	Progress          func(ProgressEvent) `json:"-"`
}

type PersonaBootstrapResult struct {
	PersonaID       string   `json:"persona_id"`
	Complete        bool     `json:"complete"`
	ReferenceCount  int      `json:"reference_count"`
	TargetReferences int     `json:"target_references"`
	Attempts        int      `json:"attempts"`
	Promoted        []string `json:"promoted"`
	BestIdentity    float64  `json:"best_identity"`
	BestQuality     float64  `json:"best_quality"`
	LastStatus      string   `json:"last_status,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type BootstrapAllResult struct {
	OK              bool                     `json:"ok"`
	Complete        int                      `json:"complete"`
	Total           int                      `json:"total"`
	TargetReferences int                     `json:"target_references"`
	Personas        []PersonaBootstrapResult `json:"personas"`
}

func personaFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext == ".yaml" || ext == ".yml" {
			out = append(out, filepath.Join(dir, entry.Name()))
		}
	}
	sort.Strings(out)
	return out, nil
}

func countReferences(root, personaID string) int {
	dir := filepath.Join(root, personaID)
	count := 0
	for _, spec := range canonicalViews {
		if info, err := os.Stat(filepath.Join(dir, spec.Filename)); err == nil && !info.IsDir() {
			count++
			continue
		}
		break
	}
	return count
}

type canonicalViewSpec struct {
	Name            string
	Filename        string
	Scene           string
	RequireFaceGate bool
	IncludeInMaster bool
}

var canonicalViews = []canonicalViewSpec{
	{
		Name: "front",
		Filename: "00_front.png",
		Scene: "strict front-facing head-and-shoulders identity portrait, camera at eye level, neutral expression, both ears and both eyes visible, unobstructed face, even neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: true,
	},
	{
		Name: "three_quarter_left",
		Filename: "01_three_quarter_left.png",
		Scene: "head-and-shoulders identity portrait turned about 35 degrees to the subject's left, three-quarter view, both eyes visible, nose shape and jawline readable, same hairline and facial proportions, neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: true,
	},
	{
		Name: "three_quarter_right",
		Filename: "02_three_quarter_right.png",
		Scene: "head-and-shoulders identity portrait turned about 35 degrees to the subject's right, three-quarter view, both eyes visible, nose shape and jawline readable, same hairline and facial proportions, neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: true,
	},
	{
		Name: "left_profile",
		Filename: "03_left_profile.png",
		Scene: "clean left-side facial profile identity portrait, approximately 90 degrees, one eye visible, full nose bridge, lips, chin, ear and hairline visible, neutral expression, neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: true,
	},
	{
		Name: "right_profile",
		Filename: "04_right_profile.png",
		Scene: "clean right-side facial profile identity portrait, approximately 90 degrees, one eye visible, full nose bridge, lips, chin, ear and hairline visible, neutral expression, neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: true,
	},
	{
		Name: "rear",
		Filename: "05_rear.png",
		Scene: "strict rear head-and-shoulders identity reference from directly behind, face not visible, clearly show back of head, hairstyle, hair length, hair texture, neck and shoulder proportions, neutral light, plain background",
		RequireFaceGate: false,
		IncludeInMaster: false,
	},
	{
		Name: "face_1_neutral",
		Filename: "06_face_1_neutral.png",
		Scene: "tight straight-on facial close-up, neutral expression, eyes open, lips relaxed, hairline ears jawline and skin texture readable, even neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: false,
	},
	{
		Name: "face_2_soft_smile",
		Filename: "07_face_2_soft_smile.png",
		Scene: "tight straight-on facial close-up with a restrained natural soft smile, preserve exact facial geometry and eye shape, even neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: false,
	},
	{
		Name: "face_3_serious",
		Filename: "08_face_3_serious.png",
		Scene: "tight straight-on facial close-up with serious composed expression, preserve exact facial geometry and eye shape, even neutral light, plain background",
		RequireFaceGate: true,
		IncludeInMaster: false,
	},
}

func promoteReference(srcPath, referenceRoot, personaID string, index int, bootstrap bool, result Result) (string, error) {
	raw, err := os.ReadFile(srcPath)
	if err != nil {
		return "", err
	}

	canonicalName := fmt.Sprintf("ref-%02d.png", index)
	if index-1 >= 0 && index-1 < len(canonicalViews) {
		canonicalName = canonicalViews[index-1].Filename
	}

	// 1. Write to primary documents/sh/{personaID}/
	docDir := filepath.Join("documents", "sh", personaID)
	if err := os.MkdirAll(docDir, 0o755); err != nil {
		return "", err
	}
	docDst := filepath.Join(docDir, canonicalName)
	if err := os.WriteFile(docDst, raw, 0o644); err != nil {
		return "", err
	}

	// 2. Mirror to referenceRoot/{personaID}/
	refDir := filepath.Join(referenceRoot, personaID)
	_ = os.MkdirAll(refDir, 0o755)
	refDst := filepath.Join(refDir, canonicalName)
	_ = os.WriteFile(refDst, raw, 0o644)

	meta := map[string]any{
		"persona_id":        personaID,
		"view":              strings.TrimSuffix(canonicalName, ".png"),
		"filename":          canonicalName,
		"source_asset_id":   result.AssetID,
		"source_asset_path": result.AssetPath,
		"bootstrap":         bootstrap,
		"identity":          result.Identity,
		"quality":           result.Quality,
		"quality_passed":    result.QualityPassed,
		"prompt":            result.Prompt,
		"generation":        result.Generation,
		"location":          docDst,
	}
	b, _ := json.MarshalIndent(meta, "", "  ")
	_ = os.WriteFile(docDst+".json", b, 0o644)
	_ = os.WriteFile(refDst+".json", b, 0o644)
	return docDst, nil
}

func resizeNearest(src image.Image, width, height int) *image.RGBA {
	dst := image.NewRGBA(image.Rect(0, 0, width, height))
	sb := src.Bounds()
	if sb.Dx() == 0 || sb.Dy() == 0 {
		return dst
	}
	for y := 0; y < height; y++ {
		sy := sb.Min.Y + y*sb.Dy()/height
		if sy >= sb.Max.Y { sy = sb.Max.Y-1 }
		for x := 0; x < width; x++ {
			sx := sb.Min.X + x*sb.Dx()/width
			if sx >= sb.Max.X { sx = sb.Max.X-1 }
			dst.Set(x, y, src.At(sx, sy))
		}
	}
	return dst
}

func writeFivePaneMaster(referenceRoot, personaID string) (string, error) {
	const cellW = 360
	const cellH = 480
	const panes = 5
	canvas := image.NewRGBA(image.Rect(0, 0, cellW*panes, cellH))

	refDir := filepath.Join(referenceRoot, personaID)
	for i, spec := range canonicalViews {
		if !spec.IncludeInMaster {
			continue
		}
		f, err := os.Open(filepath.Join(refDir, spec.Filename))
		if err != nil {
			return "", fmt.Errorf("open %s for master sheet: %w", spec.Name, err)
		}
		img, _, decErr := image.Decode(f)
		_ = f.Close()
		if decErr != nil {
			return "", fmt.Errorf("decode %s for master sheet: %w", spec.Name, decErr)
		}
		resized := resizeNearest(img, cellW, cellH)
		draw.Draw(canvas, image.Rect(i*cellW, 0, (i+1)*cellW, cellH), resized, image.Point{}, draw.Src)
	}

	docDir := filepath.Join("documents", "sh", personaID)
	if err := os.MkdirAll(docDir, 0o755); err != nil {
		return "", err
	}
	docPath := filepath.Join(docDir, "master_5pane.png")
	docFile, err := os.Create(docPath)
	if err != nil {
		return "", err
	}
	if err := png.Encode(docFile, canvas); err != nil {
		_ = docFile.Close()
		return "", err
	}
	if err := docFile.Close(); err != nil {
		return "", err
	}

	refPath := filepath.Join(refDir, "master_5pane.png")
	refFile, err := os.Create(refPath)
	if err != nil {
		return "", err
	}
	if err := png.Encode(refFile, canvas); err != nil {
		_ = refFile.Close()
		return "", err
	}
	if err := refFile.Close(); err != nil {
		return "", err
	}
	return docPath, nil
}

func selectBootstrapConsensus(ctx context.Context, manager *nativecore.Manager, candidates []Result, threshold float64) (Result, bool, error) {
	if len(candidates) < 3 {
		return Result{}, false, nil
	}

	var best Result
	bestMean := -2.0
	scored := false
	for i, candidate := range candidates {
		raw, err := os.ReadFile(candidate.AssetPath)
		if err != nil {
			continue
		}
		refs := make([][]byte, 0, len(candidates)-1)
		for j, other := range candidates {
			if i == j {
				continue
			}
			ref, err := os.ReadFile(other.AssetPath)
			if err == nil {
				refs = append(refs, ref)
			}
		}
		if len(refs) < 2 {
			continue
		}
		identity := scoreIdentity(ctx, manager, raw, refs, threshold, threshold)
		if !identity.Scored {
			continue
		}
		// Bootstrap selection uses agreement with the whole candidate pool, not
		// one lucky nearest neighbour. This makes the first promoted image a
		// medoid-like identity anchor.
		identity.Score = identity.MeanScore
		identity.Metric = "mean_cosine_consensus"
		identity.Passed = identity.MeanScore >= threshold
		identity.Reason = "bootstrap_consensus"
		candidate.Identity = identity
		candidate.Status = "bootstrap_consensus"
		candidate.OK = identity.Passed && candidate.QualityPassed

		if !scored || identity.MeanScore > bestMean {
			best = candidate
			bestMean = identity.MeanScore
			scored = true
		}
	}
	if !scored {
		return Result{}, false, fmt.Errorf("bootstrap consensus could not produce ArcFace embeddings")
	}
	return best, best.Identity.Passed && best.QualityPassed, nil
}

// BootstrapAll builds a compact, verified identity pack for every fictional adult
// persona. A persona with no references first builds a small quality-passing
// candidate pool and promotes only an ArcFace-consensus anchor. Every later
// reference must pass SCRFD/5-point/ArcFace identity gating and local image-quality
// gating before it is promoted.
func BootstrapAll(ctx context.Context, req BootstrapAllRequest) (BootstrapAllResult, error) {
	if req.PersonaDir == "" {
		req.PersonaDir = "personas"
	}
	if req.ReferenceRoot == "" {
		req.ReferenceRoot = filepath.Join("data", "references")
	}
	if req.OutputRoot == "" {
		req.OutputRoot = filepath.Join("data", "identity-candidates")
	}
	if req.TargetReferences <= 0 {
		req.TargetReferences = len(canonicalViews)
	}
	if req.TargetReferences > len(canonicalViews) {
		req.TargetReferences = len(canonicalViews)
	}
	if req.MaxAttempts <= 0 {
		req.MaxAttempts = 20
	}
	if req.Theme == "" {
		req.Theme = "clean identity reference portrait"
	}
	if req.Style == "" {
		req.Style = "photorealistic neutral portrait"
	}
	if req.Width == 0 {
		req.Width = 1024
	}
	if req.Height == 0 {
		req.Height = 1024
	}
	if req.Steps == 0 {
		req.Steps = 20
	}
	if req.Guidance == 0 {
		req.Guidance = 7.0
	}
	if req.IdentityThreshold == 0 {
		req.IdentityThreshold = 0.82
	}
	if req.IdentityMeanThreshold == 0 {
		req.IdentityMeanThreshold = 0.70
	}
	if req.QualityThreshold == 0 {
		req.QualityThreshold = 0.78
	}

	files, err := personaFiles(req.PersonaDir)
	if err != nil {
		return BootstrapAllResult{}, fmt.Errorf("list personas: %w", err)
	}
	if len(files) == 0 {
		return BootstrapAllResult{}, fmt.Errorf("no persona YAML files found in %s", req.PersonaDir)
	}
	if strings.TrimSpace(req.PersonaID) != "" {
		wanted := strings.TrimSpace(req.PersonaID)
		filtered := make([]string, 0, 1)
		for _, path := range files {
			p, err := loadPersona(Request{PersonaPath:path})
			if err == nil && p.ID == wanted {
				filtered = append(filtered, path)
				break
			}
		}
		if len(filtered) == 0 {
			return BootstrapAllResult{}, fmt.Errorf("persona %q not found in %s", wanted, req.PersonaDir)
		}
		files = filtered
	}

	out := BootstrapAllResult{Total: len(files), TargetReferences: req.TargetReferences}
	if req.Progress != nil { req.Progress(ProgressEvent{Percent:1,Stage:"bootstrap initialized",Metrics:map[string]any{"personas":len(files),"target_refs":req.TargetReferences,"max_attempts":req.MaxAttempts}}) }
	for pi, path := range files {
		p, err := loadPersona(Request{PersonaPath: path})
		if err != nil {
			out.Personas = append(out.Personas, PersonaBootstrapResult{Error: err.Error()})
			continue
		}
		pr := PersonaBootstrapResult{PersonaID: p.ID, TargetReferences: req.TargetReferences}
		basePercent := 100.0 * float64(pi) / float64(len(files))
		if req.Progress != nil { req.Progress(ProgressEvent{Percent:basePercent,Stage:"persona "+p.ID,Metrics:map[string]any{"persona":fmt.Sprintf("%d/%d",pi+1,len(files))}}) }
		refCount := countReferences(req.ReferenceRoot, p.ID)
		pr.ReferenceCount = refCount
		bootstrapCandidates := make([]Result, 0, 6)
		manager := nativecore.FromEnv()

		for attempt := 0; refCount < req.TargetReferences && attempt < req.MaxAttempts; attempt++ {
			select {
			case <-ctx.Done():
				return out, ctx.Err()
			default:
			}
			pr.Attempts++
			if req.Progress != nil { req.Progress(ProgressEvent{Percent:basePercent,Stage:"attempt",Metrics:map[string]any{"persona_id":p.ID,"attempt":fmt.Sprintf("%d/%d",attempt+1,req.MaxAttempts),"references":fmt.Sprintf("%d/%d",refCount,req.TargetReferences)}}) }
			seed := req.Seed
			if seed != 0 {
				seed += int64(pi*10000 + attempt)
			}
			r, runErr := Run(ctx, Request{
				PersonaID: p.ID,
				PersonaPath: path,
				Theme: req.Theme,
				Scene: canonicalViews[refCount].Scene,
				Style: req.Style,
				Seed: seed,
				Width: req.Width,
				Height: req.Height,
				Steps: req.Steps,
				Guidance: req.Guidance,
				OutputDir: filepath.Join(req.OutputRoot, p.ID),
				ReferenceRoot: req.ReferenceRoot,
				IdentityThreshold: req.IdentityThreshold,
				IdentityMeanThreshold: req.IdentityMeanThreshold,
				QualityThreshold: req.QualityThreshold,
				Generator: req.Generator,
				Progress: func(ev ProgressEvent) {
					if req.Progress == nil { return }
					personaSpan := 100.0 / float64(len(files))
					attemptFraction := (float64(attempt) + ev.Percent/100.0) / float64(req.MaxAttempts)
					pct := basePercent + personaSpan*attemptFraction
					m := map[string]any{"persona_id":p.ID,"attempt":fmt.Sprintf("%d/%d",attempt+1,req.MaxAttempts),"references":fmt.Sprintf("%d/%d",refCount,req.TargetReferences)}
					for k,v := range ev.Metrics { m[k]=v }
					req.Progress(ProgressEvent{Percent:pct,Stage:ev.Stage,Metrics:m})
				},
			})
			if runErr != nil {
				pr.Error = runErr.Error()
				continue
			}
			pr.LastStatus = r.Status
			if r.Identity.Score > pr.BestIdentity {
				pr.BestIdentity = r.Identity.Score
			}
			if r.Quality.LocalScore > pr.BestQuality {
				pr.BestQuality = r.Quality.LocalScore
			}

			bootstrap := false
			verified := false
			viewSpec := canonicalViews[refCount]
			if refCount == 0 {
				if !r.QualityPassed {
					continue
				}
				bootstrapCandidates = append(bootstrapCandidates, r)
				if len(bootstrapCandidates) < 3 {
					if req.Progress != nil {
						req.Progress(ProgressEvent{Percent:basePercent, Stage:"collecting bootstrap consensus", Metrics:map[string]any{
							"persona_id":p.ID,
							"candidates":fmt.Sprintf("%d/3", len(bootstrapCandidates)),
							"quality_score":r.Quality.LocalScore,
						}})
					}
					continue
				}
				selected, ready, consensusErr := selectBootstrapConsensus(ctx, manager, bootstrapCandidates, req.IdentityThreshold)
				if consensusErr != nil {
					pr.Error = consensusErr.Error()
					continue
				}
				if selected.Identity.Score > pr.BestIdentity {
					pr.BestIdentity = selected.Identity.Score
				}
				if !ready {
					if req.Progress != nil {
						req.Progress(ProgressEvent{Percent:basePercent, Stage:"bootstrap consensus below threshold", Metrics:map[string]any{
							"persona_id":p.ID,
							"candidates":len(bootstrapCandidates),
							"consensus_score":selected.Identity.Score,
							"identity_threshold":req.IdentityThreshold,
						}})
					}
					continue
				}
				r = selected
				bootstrap = true
			} else if viewSpec.RequireFaceGate {
				verified = r.Identity.Scored && r.Identity.Passed && r.QualityPassed
				if !verified {
					continue
				}
			} else {
				// A strict rear view intentionally contains no detectable face, so
				// ArcFace is not a meaningful gate. Keep it last, require image
				// quality, and record that face identity scoring is not applicable.
				if !r.QualityPassed {
					continue
				}
				r.Identity = IdentityResult{
					Scored: false,
					Passed: true,
					Threshold: req.IdentityThreshold,
					ReferenceCount: refCount,
					Model: "arcface-w600k-r50-qnn",
					Metric: "not_applicable_rear_view",
					Alignment: "rear-no-face",
					NPU: true,
					Reason: "rear_reference_has_no_visible_face",
				}
				r.Status = "proposed_rear_reference"
				r.OK = true
				verified = true
			}
			dst, promoteErr := promoteReference(r.AssetPath, req.ReferenceRoot, p.ID, refCount+1, bootstrap, r)
			if promoteErr != nil {
				pr.Error = promoteErr.Error()
				continue
			}
			pr.Promoted = append(pr.Promoted, dst)
			refCount++
			pr.ReferenceCount = refCount
			if req.Progress != nil { personaSpan:=100.0/float64(len(files)); pct:=basePercent+personaSpan*float64(attempt+1)/float64(req.MaxAttempts); req.Progress(ProgressEvent{Percent:pct,Stage:"reference promoted",Metrics:map[string]any{"persona_id":p.ID,"references":fmt.Sprintf("%d/%d",refCount,req.TargetReferences),"identity_score":r.Identity.Score,"quality_score":r.Quality.LocalScore}}) }
		}

		pr.Complete = refCount >= req.TargetReferences
		if pr.Complete {
			masterPath, masterErr := writeFivePaneMaster(req.ReferenceRoot, p.ID)
			if masterErr != nil {
				pr.Error = masterErr.Error()
				pr.Complete = false
			} else {
				pr.Promoted = append(pr.Promoted, masterPath)
				out.Complete++
				if req.Progress != nil {
					req.Progress(ProgressEvent{Percent:basePercent + 100.0/float64(len(files)), Stage:"master identity sheet complete", Metrics:map[string]any{
						"persona_id":p.ID,
						"master_5pane":masterPath,
						"references":refCount,
					}})
				}
			}
		}
		out.Personas = append(out.Personas, pr)
	}
	out.OK = out.Complete == out.Total
	if req.Progress != nil { req.Progress(ProgressEvent{Percent:100,Stage:"bootstrap complete",Metrics:map[string]any{"complete":fmt.Sprintf("%d/%d",out.Complete,out.Total),"ok":out.OK}}) }

	manifestDir := filepath.Join(req.ReferenceRoot, "_manifests")
	if err := os.MkdirAll(manifestDir, 0o755); err == nil {
		if b, marshalErr := json.MarshalIndent(out, "", "  "); marshalErr == nil {
			_ = os.WriteFile(filepath.Join(manifestDir, "identity-bootstrap.json"), b, 0o644)
		}
	}
	return out, nil
}
