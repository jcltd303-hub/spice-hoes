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
	"strings"

	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"gopkg.in/yaml.v3"
)

type PoseMasterRequest struct {
	PersonaID        string  `json:"persona_id"`
	PersonaPath      string  `json:"persona_path,omitempty"`
	TemplatePath     string  `json:"template_path,omitempty"`
	OutputRoot       string  `json:"output_root,omitempty"`
	Generator        string  `json:"generator,omitempty"`
	Seed             int64   `json:"seed,omitempty"`
	Width            int     `json:"width,omitempty"`
	Height           int     `json:"height,omitempty"`
	QualityThreshold float64 `json:"quality_threshold,omitempty"`
	MaxAttempts      int     `json:"max_attempts,omitempty"`
	Progress         func(ProgressEvent) `json:"-"`
}

type PoseSpec struct {
	ID          string `yaml:"id" json:"id"`
	Label       string `yaml:"label" json:"label"`
	Instruction string `yaml:"instruction" json:"instruction"`
}

type PoseTemplate struct {
	Version int    `yaml:"version" json:"version"`
	ID      string `yaml:"id" json:"id"`
	Render  struct {
		Background     string `yaml:"background" json:"background"`
		Lighting       string `yaml:"lighting" json:"lighting"`
		Camera         string `yaml:"camera" json:"camera"`
		Framing        string `yaml:"framing" json:"framing"`
		WardrobePolicy string `yaml:"wardrobe_policy" json:"wardrobe_policy"`
		HairPolicy     string `yaml:"hair_policy" json:"hair_policy"`
		Anatomy        string `yaml:"anatomy" json:"anatomy"`
	} `yaml:"render" json:"render"`
	Poses []PoseSpec `yaml:"poses" json:"poses"`
}

type PoseAsset struct {
	PoseID        string               `json:"pose_id"`
	Label         string               `json:"label"`
	Path          string               `json:"path"`
	MetadataPath  string               `json:"metadata_path"`
	Seed          int64                `json:"seed"`
	Attempts      int                  `json:"attempts"`
	Quality       imagemetrics.Metrics `json:"quality"`
	QualityPassed bool                 `json:"quality_passed"`
	Generation    map[string]any       `json:"generation"`
}

type PoseMasterResult struct {
	OK           bool        `json:"ok"`
	PersonaID    string      `json:"persona_id"`
	TemplateID   string      `json:"template_id"`
	OutputDir    string      `json:"output_dir"`
	ContactSheet string      `json:"contact_sheet,omitempty"`
	Assets       []PoseAsset `json:"assets"`
}

func loadPoseTemplate(path string) (PoseTemplate, error) {
	if path == "" {
		path = filepath.Join("identity", "templates", "body_posture_master_v1.yaml")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return PoseTemplate{}, fmt.Errorf("read pose template: %w", err)
	}
	var t PoseTemplate
	if err := yaml.Unmarshal(raw, &t); err != nil {
		return PoseTemplate{}, fmt.Errorf("parse pose template: %w", err)
	}
	if t.ID == "" || len(t.Poses) == 0 {
		return PoseTemplate{}, fmt.Errorf("pose template missing id/poses")
	}
	return t, nil
}

func posePrompt(p Persona, t PoseTemplate, pose PoseSpec) string {
	hair := strings.TrimSpace(p.IdentityReference.HairMode)
	if hair == "" {
		hair = strings.TrimSpace(p.Physical.HairReferenceStyle)
	}
	if hair == "" {
		hair = strings.TrimSpace(t.Render.HairPolicy)
	}
	parts := []string{
		fmt.Sprintf("Original fictional AI-generated adult character %s, age %d.", p.Name, p.Age),
		"Canonical body posture reference.",
		"Physical identity: " + physicalPrompt(p) + ".",
		"Body lock: " + strings.TrimSpace(p.IdentityReference.BodyPrompt) + ".",
		"Pose: " + strings.TrimSpace(pose.Instruction) + ".",
		"Background: " + strings.TrimSpace(t.Render.Background) + ".",
		"Lighting: " + strings.TrimSpace(t.Render.Lighting) + ".",
		"Camera: " + strings.TrimSpace(t.Render.Camera) + ".",
		"Framing: " + strings.TrimSpace(t.Render.Framing) + ".",
		"Identity-reference hair: " + hair + ".",
		"Minimal neutral fitted studio reference clothing only; wardrobe is not part of identity.",
		"Preserve height impression, body proportions, limb differences, birthmarks and other distinguishing physical features exactly.",
		"Realistic anatomy, clean professional reference photography, no text, no watermark.",
		"Do not resemble any real person or public figure.",
	}
	return strings.Join(parts, " ")
}

func writePoseContactSheet(assets []PoseAsset, output string) error {
	if len(assets) == 0 {
		return fmt.Errorf("no pose assets")
	}
	const cols = 3
	const cellW = 320
	const cellH = 430
	rows := (len(assets) + cols - 1) / cols
	canvas := image.NewRGBA(image.Rect(0, 0, cols*cellW, rows*cellH))
	for i, asset := range assets {
		f, err := os.Open(asset.Path)
		if err != nil {
			return err
		}
		img, _, decErr := image.Decode(f)
		_ = f.Close()
		if decErr != nil {
			return decErr
		}
		resized := resizeNearest(img, cellW, cellH)
		x := (i % cols) * cellW
		y := (i / cols) * cellH
		draw.Draw(canvas, image.Rect(x, y, x+cellW, y+cellH), resized, image.Point{}, draw.Src)
	}
	f, err := os.Create(output)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, canvas)
}

func GeneratePoseMasters(ctx context.Context, req PoseMasterRequest) (PoseMasterResult, error) {
	p, err := loadPersona(Request{PersonaID:req.PersonaID, PersonaPath:req.PersonaPath})
	if err != nil {
		return PoseMasterResult{}, err
	}
	t, err := loadPoseTemplate(req.TemplatePath)
	if err != nil {
		return PoseMasterResult{}, err
	}
	if req.Width <= 0 { req.Width = 768 }
	if req.Height <= 0 { req.Height = 1024 }
	if req.QualityThreshold <= 0 { req.QualityThreshold = 0.74 }
	if req.MaxAttempts <= 0 { req.MaxAttempts = 4 }
	if req.OutputRoot == "" { req.OutputRoot = filepath.Join("data", "pose-templates") }
	outDir := filepath.Join(req.OutputRoot, t.ID, p.ID)
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return PoseMasterResult{}, err
	}

	result := PoseMasterResult{PersonaID:p.ID, TemplateID:t.ID, OutputDir:outDir}
	for i, pose := range t.Poses {
		var selected PoseAsset
		bestScore := -1.0
		for attempt := 0; attempt < req.MaxAttempts; attempt++ {
			select {
			case <-ctx.Done():
				return result, ctx.Err()
			default:
			}
			seed := req.Seed
			if seed == 0 { seed = 41000 }
			seed += int64(i*100 + attempt)
			genReq := Request{
				PersonaID:p.ID, PersonaPath:req.PersonaPath,
				Theme:"canonical identity body posture master",
				Scene:pose.Instruction,
				Style:"photorealistic neutral studio reference",
				NegativePrompt:defaultNegative,
				Seed:seed, Width:req.Width, Height:req.Height,
				Steps:20, Guidance:7, Generator:req.Generator,
			}
			prompt := posePrompt(p, t, pose)
			frame, meta, backend, genErr := generateFrame(ctx, genReq, prompt)
			if genErr != nil {
				continue
			}
			quality, qErr := imagemetrics.AnalyzeImage(frame.Image)
			if qErr != nil {
				continue
			}
			if req.Progress != nil {
				req.Progress(ProgressEvent{
					Percent:100*float64(i*req.MaxAttempts+attempt+1)/float64(len(t.Poses)*req.MaxAttempts),
					Stage:"pose candidate",
					Metrics:map[string]any{"pose":pose.ID,"attempt":attempt+1,"generator":backend,"quality":quality.LocalScore},
				})
			}
			if quality.LocalScore <= bestScore {
				continue
			}
			path := filepath.Join(outDir, fmt.Sprintf("%02d_%s.png", i, pose.ID))
			encoded, encErr := encodeFramePNG(frame)
			if encErr != nil {
				return result, encErr
			}
			if err := os.WriteFile(path, encoded, 0o644); err != nil {
				return result, err
			}
			selected = PoseAsset{
				PoseID:pose.ID, Label:pose.Label, Path:path, MetadataPath:path+".json",
				Seed:seed, Attempts:attempt+1, Quality:quality,
				QualityPassed:quality.LocalScore >= req.QualityThreshold,
				Generation:meta,
			}
			metaOut := map[string]any{
				"persona_id":p.ID, "template_id":t.ID, "pose":pose,
				"seed":seed, "prompt":prompt, "quality":quality,
				"quality_threshold":req.QualityThreshold, "generation":meta,
			}
			b, _ := json.MarshalIndent(metaOut, "", "  ")
			_ = os.WriteFile(selected.MetadataPath, b, 0o644)
			bestScore = quality.LocalScore
			if selected.QualityPassed {
				break
			}
		}
		if selected.Path == "" {
			return result, fmt.Errorf("pose %s could not be generated", pose.ID)
		}
		result.Assets = append(result.Assets, selected)
	}

	result.ContactSheet = filepath.Join(outDir, "master_9pose.png")
	if err := writePoseContactSheet(result.Assets, result.ContactSheet); err != nil {
		return result, err
	}
	result.OK = true
	manifest, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(filepath.Join(outDir, "manifest.json"), manifest, 0o644); err != nil {
		return result, err
	}
	return result, nil
}
