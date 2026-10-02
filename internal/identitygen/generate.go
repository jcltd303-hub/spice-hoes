package identitygen

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
	"gopkg.in/yaml.v3"
)

type Persona struct {
	ID         string   `yaml:"id" json:"id"`
	Name       string   `yaml:"name" json:"name"`
	Age        int      `yaml:"age" json:"age"`
	Fictional  bool     `yaml:"fictional" json:"fictional"`
	Disclosure string   `yaml:"disclosure" json:"disclosure"`
	Visual     string   `yaml:"visual" json:"visual"`
	Voice      string   `yaml:"voice" json:"voice"`
	Hobbies    []string `yaml:"hobbies" json:"hobbies"`
}

type Request struct {
	PersonaID        string  `json:"persona_id"`
	PersonaPath      string  `json:"persona_path,omitempty"`
	Theme            string  `json:"theme"`
	Scene            string  `json:"scene,omitempty"`
	Style            string  `json:"style,omitempty"`
	NegativePrompt   string  `json:"negative_prompt,omitempty"`
	Seed             int64   `json:"seed,omitempty"`
	Width            int     `json:"width,omitempty"`
	Height           int     `json:"height,omitempty"`
	Steps            int     `json:"steps,omitempty"`
	Guidance         float64 `json:"guidance,omitempty"`
	OutputDir        string  `json:"output_dir,omitempty"`
	ReferenceRoot    string  `json:"reference_root,omitempty"`
	IdentityThreshold float64 `json:"identity_threshold,omitempty"`
	QualityThreshold float64  `json:"quality_threshold,omitempty"`
}

type IdentityResult struct {
	Scored         bool    `json:"scored"`
	Passed         bool    `json:"passed"`
	Score          float64 `json:"score,omitempty"`
	MeanScore      float64 `json:"mean_score,omitempty"`
	Threshold      float64 `json:"threshold"`
	ReferenceCount int     `json:"reference_count"`
	Model          string  `json:"model"`
	Metric         string  `json:"metric"`
	Alignment      string  `json:"alignment"`
	NPU            bool    `json:"npu"`
	Reason         string  `json:"reason,omitempty"`
}

type Result struct {
	OK             bool                 `json:"ok"`
	Status         string               `json:"status"`
	PersonaID      string               `json:"persona_id"`
	AssetID        string               `json:"asset_id"`
	AssetPath      string               `json:"asset_path"`
	MetadataPath   string               `json:"metadata_path"`
	Prompt         string               `json:"prompt"`
	NegativePrompt string               `json:"negative_prompt"`
	Identity       IdentityResult       `json:"identity"`
	Quality        imagemetrics.Metrics `json:"quality"`
	QualityPassed  bool                 `json:"quality_passed"`
	QualityThreshold float64            `json:"quality_threshold"`
	Generation     map[string]any       `json:"generation"`
}

const defaultNegative = "public figure likeness, child, teen, underage, youth-coded sexual styling, extra fingers, malformed hands, duplicate limbs, distorted face, waxy skin, plastic skin, 3d render, watermark, logo, text artifacts"

func loadPersona(req Request) (Persona, error) {
	path := strings.TrimSpace(req.PersonaPath)
	if path == "" {
		if strings.TrimSpace(req.PersonaID) == "" {
			return Persona{}, fmt.Errorf("persona_id or persona_path is required")
		}
		path = filepath.Join("personas", req.PersonaID+".yaml")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return Persona{}, fmt.Errorf("read persona: %w", err)
	}
	var p Persona
	if err := yaml.Unmarshal(raw, &p); err != nil {
		return Persona{}, fmt.Errorf("parse persona: %w", err)
	}
	if p.ID == "" || p.Name == "" {
		return Persona{}, fmt.Errorf("persona is missing id/name")
	}
	if !p.Fictional || p.Age < 18 {
		return Persona{}, fmt.Errorf("identity generation requires a fictional adult persona")
	}
	return p, nil
}

func promptFor(p Persona, req Request) string {
	style := strings.TrimSpace(req.Style)
	if style == "" {
		style = "photorealistic"
	}
	parts := []string{
		fmt.Sprintf("Original fictional AI-generated adult character %s, age %d.", p.Name, p.Age),
		fmt.Sprintf("Identity anchor: %s.", strings.TrimSpace(p.Visual)),
		fmt.Sprintf("Theme: %s.", strings.TrimSpace(req.Theme)),
		fmt.Sprintf("Style: %s.", style),
		"Photorealistic lifestyle photography, natural skin texture, visible pores, subtle asymmetry, realistic lighting, coherent anatomy.",
		"Maintain the same facial proportions, hairline, body proportions, and signature visual traits across generations.",
		"Do not resemble any real person or public figure.",
	}
	if strings.TrimSpace(req.Scene) != "" {
		parts = append(parts, "Scene: "+strings.TrimSpace(req.Scene)+".")
	}
	if len(p.Hobbies) > 0 {
		parts = append(parts, "Character context: "+strings.Join(p.Hobbies, ", ")+".")
	}
	if strings.TrimSpace(p.Voice) != "" {
		parts = append(parts, "Personality cue: "+strings.TrimSpace(p.Voice)+".")
	}
	return strings.Join(parts, " ")
}

func arcEmbedding(ctx context.Context, m *nativecore.Manager, raw []byte) ([]float64, string, error) {
	alignment := "center-crop-112"
	var input []float64
	if m.FaceDetector != "" {
		prep, err := ident.SCRFDInput(raw)
		if err == nil {
			outputs, _, detErr := m.Detect(ctx, prep.Tensor)
			if detErr == nil {
				faces, decErr := ident.DecodeSCRFD(outputs, prep, 0.5, 0.4)
				if decErr == nil && len(faces) > 0 {
					input, err = ident.ArcFaceInputAligned(raw, faces[0].Landmarks)
					if err == nil {
						alignment = "scrfd-5pt-112"
					}
				}
			}
		}
	}
	if input == nil {
		var err error
		input, err = ident.ArcFaceInput(raw)
		if err != nil {
			return nil, alignment, err
		}
	}
	vec, _, err := m.Embed(ctx, input)
	if err != nil {
		return nil, alignment, err
	}
	return ident.Normalize(vec), alignment, nil
}

func loadReferences(root, personaID string) ([][]byte, error) {
	dir := filepath.Join(root, personaID)
	entries, err := os.ReadDir(dir)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	out := make([][]byte, 0, 6)
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext != ".png" && ext != ".jpg" && ext != ".jpeg" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, entry.Name()))
		if err != nil {
			continue
		}
		out = append(out, b)
		if len(out) == 6 {
			break
		}
	}
	return out, nil
}

func scoreIdentity(ctx context.Context, m *nativecore.Manager, generated []byte, refs [][]byte, threshold float64) IdentityResult {
	result := IdentityResult{
		Threshold: threshold,
		ReferenceCount: len(refs),
		Model: "arcface-w600k-r50-qnn",
		Metric: "cosine",
		NPU: true,
	}
	if len(refs) == 0 {
		result.Reason = "no_reference_pack"
		return result
	}
	genVec, alignment, err := arcEmbedding(ctx, m, generated)
	result.Alignment = alignment
	if err != nil {
		result.Reason = err.Error()
		return result
	}
	scores := make([]float64, 0, len(refs))
	for _, ref := range refs {
		refVec, _, err := arcEmbedding(ctx, m, ref)
		if err != nil {
			continue
		}
		s, err := ident.Cosine(genVec, refVec)
		if err == nil {
			scores = append(scores, s)
		}
	}
	if len(scores) == 0 {
		result.Reason = "no_reference_embedding_succeeded"
		return result
	}
	maxScore := scores[0]
	sum := 0.0
	for _, s := range scores {
		if s > maxScore {
			maxScore = s
		}
		sum += s
	}
	result.Scored = true
	result.Score = maxScore
	result.MeanScore = sum / float64(len(scores))
	result.ReferenceCount = len(scores)
	result.Passed = maxScore >= threshold
	return result
}

func randomID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err == nil {
		return hex.EncodeToString(b[:])
	}
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

func Run(ctx context.Context, req Request) (Result, error) {
	p, err := loadPersona(req)
	if err != nil {
		return Result{}, err
	}
	if strings.TrimSpace(req.Theme) == "" {
		req.Theme = "identity reference portrait"
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
	if req.OutputDir == "" {
		req.OutputDir = filepath.Join("data", "identity-candidates", p.ID)
	}
	if req.ReferenceRoot == "" {
		req.ReferenceRoot = filepath.Join("data", "references")
	}
	if req.IdentityThreshold == 0 {
		req.IdentityThreshold = 0.82
	}
	if req.QualityThreshold == 0 {
		req.QualityThreshold = 0.78
	}
	if req.NegativePrompt == "" {
		req.NegativePrompt = defaultNegative
	}

	prompt := promptFor(p, req)
	m := nativecore.FromEnv()
	if m.ModelDir == "" {
		return Result{}, fmt.Errorf("identity generation requires SPICE_QNN_MODEL_DIR")
	}

	payload := map[string]any{
		"prompt": reqPrompt(prompt),
		"negative_prompt": req.NegativePrompt,
		"width": req.Width,
		"height": req.Height,
		"steps": req.Steps,
		"guidance": req.Guidance,
		"output_format": "png",
	}
	if req.Seed != 0 {
		payload["seed"] = req.Seed
	}

	out, err := m.Generate(ctx, payload)
	if err != nil {
		return Result{}, err
	}
	imageB64, _ := out["image"].(string)
	if imageB64 == "" {
		return Result{}, fmt.Errorf("QNN generation returned no image")
	}
	imageBytes, err := base64.StdEncoding.DecodeString(imageB64)
	if err != nil {
		return Result{}, fmt.Errorf("decode generated image: %w", err)
	}

	if err := os.MkdirAll(req.OutputDir, 0o755); err != nil {
		return Result{}, err
	}
	assetID := randomID()
	assetPath := filepath.Join(req.OutputDir, assetID+".png")
	if err := os.WriteFile(assetPath, imageBytes, 0o644); err != nil {
		return Result{}, err
	}

	refs, err := loadReferences(req.ReferenceRoot, p.ID)
	if err != nil {
		return Result{}, fmt.Errorf("load references: %w", err)
	}
	identity := scoreIdentity(ctx, m, imageBytes, refs, req.IdentityThreshold)
	quality, err := imagemetrics.Analyze(imageBytes)
	if err != nil {
		return Result{}, err
	}
	qualityPassed := quality.LocalScore >= req.QualityThreshold
	status := "proposed"
	if identity.Scored && !identity.Passed {
		status = "rejected_identity"
	} else if !qualityPassed {
		status = "rejected_quality"
	} else if !identity.Scored {
		status = "bootstrap_candidate"
	}

	metaPath := assetPath + ".json"
	result := Result{
		OK: status == "proposed" || status == "bootstrap_candidate",
		Status: status,
		PersonaID: p.ID,
		AssetID: assetID,
		AssetPath: assetPath,
		MetadataPath: metaPath,
		Prompt: prompt,
		NegativePrompt: req.NegativePrompt,
		Identity: identity,
		Quality: quality,
		QualityPassed: qualityPassed,
		QualityThreshold: req.QualityThreshold,
		Generation: out,
	}
	meta, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(metaPath, meta, 0o644); err != nil {
		return Result{}, err
	}
	return result, nil
}

func reqPrompt(s string) string { return s }
