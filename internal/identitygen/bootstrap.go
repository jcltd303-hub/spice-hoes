package identitygen

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type BootstrapAllRequest struct {
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
	QualityThreshold  float64 `json:"quality_threshold,omitempty"`
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
	refs, err := loadReferences(root, personaID)
	if err != nil {
		return 0
	}
	return len(refs)
}

func promoteReference(srcPath, referenceRoot, personaID string, index int, bootstrap bool, result Result) (string, error) {
	raw, err := os.ReadFile(srcPath)
	if err != nil {
		return "", err
	}
	dir := filepath.Join(referenceRoot, personaID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	tag := "verified"
	if bootstrap {
		tag = "bootstrap"
	}
	dst := filepath.Join(dir, fmt.Sprintf("ref-%02d-%s.png", index, tag))
	if _, err := os.Stat(dst); err == nil {
		return dst, nil
	}
	if err := os.WriteFile(dst, raw, 0o644); err != nil {
		return "", err
	}
	meta := map[string]any{
		"persona_id": personaID,
		"source_asset_id": result.AssetID,
		"source_asset_path": result.AssetPath,
		"bootstrap": bootstrap,
		"identity": result.Identity,
		"quality": result.Quality,
		"quality_passed": result.QualityPassed,
		"prompt": result.Prompt,
		"generation": result.Generation,
	}
	b, _ := json.MarshalIndent(meta, "", "  ")
	if err := os.WriteFile(dst+".json", b, 0o644); err != nil {
		return "", err
	}
	return dst, nil
}

// BootstrapAll builds a compact, verified identity pack for every fictional adult
// persona. A persona with no references gets exactly one quality-passing bootstrap
// seed. Every later reference must pass both SCRFD/5-point/ArcFace identity gating
// and local image-quality gating before it is promoted.
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
		req.TargetReferences = 5
	}
	if req.TargetReferences > 6 {
		req.TargetReferences = 6
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
				Scene: "front-facing or gentle three-quarter portrait, unobstructed face, even natural light, no sunglasses, no heavy occlusion",
				Style: req.Style,
				Seed: seed,
				Width: req.Width,
				Height: req.Height,
				Steps: req.Steps,
				Guidance: req.Guidance,
				OutputDir: filepath.Join(req.OutputRoot, p.ID),
				ReferenceRoot: req.ReferenceRoot,
				IdentityThreshold: req.IdentityThreshold,
				QualityThreshold: req.QualityThreshold,
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

			bootstrap := refCount == 0 && !r.Identity.Scored && r.QualityPassed
			verified := r.Identity.Scored && r.Identity.Passed && r.QualityPassed
			if !bootstrap && !verified {
				continue
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
			out.Complete++
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
