package identitygen

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image"
	_ "image/jpeg"
	"image/png"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"github.com/jcltd303-hub/spice-hoes/internal/faceswap"
	"github.com/jcltd303-hub/spice-hoes/internal/localdream"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
	"gopkg.in/yaml.v3"
)

type PhysicalProfile struct {
	HeightCM              int      `yaml:"height_cm" json:"height_cm"`
	WeightKG              float64  `yaml:"weight_kg" json:"weight_kg"`
	Build                  string   `yaml:"build" json:"build"`
	Proportions            string   `yaml:"proportions" json:"proportions"`
	EyeColor               string   `yaml:"eye_color" json:"eye_color"`
	EyeShape               string   `yaml:"eye_shape" json:"eye_shape"`
	HairColor              string   `yaml:"hair_color" json:"hair_color"`
	HairTexture            string   `yaml:"hair_texture" json:"hair_texture"`
	HairReferenceStyle     string   `yaml:"hair_reference_style" json:"hair_reference_style"`
	SkinTone               string   `yaml:"skin_tone" json:"skin_tone"`
	DistinguishingFeatures []string `yaml:"distinguishing_features" json:"distinguishing_features"`
}

type IdentityReferenceProfile struct {
	BodyPrompt       string  `yaml:"body_prompt" json:"body_prompt"`
	WardrobeMode     string  `yaml:"wardrobe_mode" json:"wardrobe_mode"`
	HairMode         string  `yaml:"hair_mode" json:"hair_mode"`
	PoseTemplate     string  `yaml:"pose_template" json:"pose_template"`
	EmbeddingToken   string  `yaml:"embedding_token,omitempty" json:"embedding_token,omitempty"`
	EmbeddingWeight  float64 `yaml:"embedding_weight,omitempty" json:"embedding_weight,omitempty"`
}

type AdultInterestProfile struct {
	Type          string `yaml:"type" json:"type"`
	Cue           string `yaml:"cue" json:"cue"`
	PublicSubtle  bool   `yaml:"public_subtle" json:"public_subtle"`
}

type ContentCueProfile struct {
	BarefootMinRate float64 `yaml:"barefoot_min_rate" json:"barefoot_min_rate"`
}

type Persona struct {
	ID                string                   `yaml:"id" json:"id"`
	Name              string                   `yaml:"name" json:"name"`
	Age               int                      `yaml:"age" json:"age"`
	Fictional         bool                     `yaml:"fictional" json:"fictional"`
	Disclosure        string                   `yaml:"disclosure" json:"disclosure"`
	Visual            string                   `yaml:"visual" json:"visual"`
	Voice             string                   `yaml:"voice" json:"voice"`
	Hobbies           []string                 `yaml:"hobbies" json:"hobbies"`
	Physical          PhysicalProfile          `yaml:"physical" json:"physical"`
	IdentityReference IdentityReferenceProfile `yaml:"identity_reference" json:"identity_reference"`
	AdultInterest     AdultInterestProfile     `yaml:"adult_interest" json:"adult_interest"`
	ContentCues       ContentCueProfile        `yaml:"content_cues" json:"content_cues"`
}

type ProgressEvent struct {
	Percent float64
	Stage string
	Metrics map[string]any
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
	IdentityMeanThreshold float64 `json:"identity_mean_threshold,omitempty"`
	QualityThreshold float64  `json:"quality_threshold,omitempty"`
	Generator         string   `json:"generator,omitempty"`
	IdentityEmbeddingToken string `json:"identity_embedding_token,omitempty"`
	IdentityEmbeddingWeight float64 `json:"identity_embedding_weight,omitempty"`
	RequireIdentityEmbedding bool `json:"require_identity_embedding,omitempty"`
	BestOfN           int      `json:"best_of_n,omitempty"`
	SwapTopK          int      `json:"swap_top_k,omitempty"`
	StopOnAccept      *bool    `json:"stop_on_accept,omitempty"`
	SaveAllAttempts   *bool    `json:"save_all_attempts,omitempty"`
	Progress          func(ProgressEvent) `json:"-"`
}

type IdentityResult struct {
	Scored         bool    `json:"scored"`
	Passed         bool    `json:"passed"`
	Score          float64 `json:"score,omitempty"`
	MeanScore      float64 `json:"mean_score,omitempty"`
	Threshold      float64 `json:"threshold"`
	MeanThreshold  float64 `json:"mean_threshold,omitempty"`
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
	DocumentsPath  string               `json:"documents_path,omitempty"`
	Prompt         string               `json:"prompt"`
	NegativePrompt string               `json:"negative_prompt"`
	Identity       IdentityResult       `json:"identity"`
	Quality        imagemetrics.Metrics `json:"quality"`
	QualityPassed  bool                 `json:"quality_passed"`
	QualityThreshold float64            `json:"quality_threshold"`
	Generation     map[string]any       `json:"generation"`
	Batch          *BatchSummary        `json:"batch,omitempty"`
}

type AttemptSummary struct {
	Index         int     `json:"index"`
	Seed          int64   `json:"seed"`
	Status        string  `json:"status"`
	AssetPath     string  `json:"asset_path,omitempty"`
	MetadataPath  string  `json:"metadata_path,omitempty"`
	IdentityScore float64 `json:"identity_score,omitempty"`
	IdentityMean  float64 `json:"identity_mean,omitempty"`
	IdentityPass  bool    `json:"identity_pass"`
	QualityScore  float64 `json:"quality_score,omitempty"`
	QualityPass   bool    `json:"quality_pass"`
	SelectionScore float64 `json:"selection_score,omitempty"`
	Error         string  `json:"error,omitempty"`
}

type BatchSummary struct {
	Requested int              `json:"requested"`
	Completed int              `json:"completed"`
	Selected  int              `json:"selected"`
	Attempts  []AttemptSummary `json:"attempts,omitempty"`
}

const defaultNegative = "public figure likeness, child, teen, underage, youth-coded sexual styling, extra fingers, malformed hands, duplicate limbs, distorted face, waxy skin, plastic skin, 3d render, watermark, logo, text artifacts, soft focus, blurry face, smeared skin texture, motion blur, low facial contrast, excessive denoise"

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

func physicalPrompt(p Persona) string {
	parts := []string{}
	if p.Physical.HeightCM > 0 { parts = append(parts, fmt.Sprintf("height %d cm", p.Physical.HeightCM)) }
	if p.Physical.WeightKG > 0 { parts = append(parts, fmt.Sprintf("weight %.0f kg", p.Physical.WeightKG)) }
	if strings.TrimSpace(p.Physical.Build) != "" { parts = append(parts, "build "+strings.TrimSpace(p.Physical.Build)) }
	if strings.TrimSpace(p.Physical.Proportions) != "" { parts = append(parts, "proportions "+strings.TrimSpace(p.Physical.Proportions)) }
	if strings.TrimSpace(p.Physical.EyeColor) != "" { parts = append(parts, strings.TrimSpace(p.Physical.EyeColor)+" eyes") }
	if strings.TrimSpace(p.Physical.EyeShape) != "" { parts = append(parts, strings.TrimSpace(p.Physical.EyeShape)+" eye shape") }
	if strings.TrimSpace(p.Physical.HairColor) != "" { parts = append(parts, strings.TrimSpace(p.Physical.HairColor)+" hair") }
	if strings.TrimSpace(p.Physical.HairTexture) != "" { parts = append(parts, strings.TrimSpace(p.Physical.HairTexture)+" hair texture") }
	if strings.TrimSpace(p.Physical.SkinTone) != "" { parts = append(parts, "skin tone "+strings.TrimSpace(p.Physical.SkinTone)) }
	if len(p.Physical.DistinguishingFeatures) > 0 { parts = append(parts, "distinguishing features "+strings.Join(p.Physical.DistinguishingFeatures, ", ")) }
	return strings.Join(parts, "; ")
}

func barefootDue(p Persona, req Request) bool {
	rate := p.ContentCues.BarefootMinRate
	if rate <= 0 { return false }
	if rate > 1 { rate = 1 }
	token := fmt.Sprintf("%s|%d|%s|%s", p.ID, req.Seed, strings.TrimSpace(req.Theme), strings.TrimSpace(req.Scene))
	sum := sha256.Sum256([]byte(token))
	n := binary.BigEndian.Uint64(sum[:8])
	fraction := float64(n) / float64(^uint64(0))
	return fraction < rate
}

func promptFor(p Persona, req Request) string {
	style := strings.TrimSpace(req.Style)
	if style == "" {
		style = "photorealistic"
	}
	parts := []string{
		fmt.Sprintf("Original fictional AI-generated adult character %s, age %d.", p.Name, p.Age),
		fmt.Sprintf("Immutable identity lock: %s.", physicalPrompt(p)),
		fmt.Sprintf("Body lock: %s.", strings.TrimSpace(p.IdentityReference.BodyPrompt)),
		fmt.Sprintf("Theme: %s.", strings.TrimSpace(req.Theme)),
		fmt.Sprintf("Style: %s.", style),
		"Photorealistic lifestyle photography, natural skin texture, visible pores, subtle asymmetry, realistic lighting, coherent anatomy. Tack-sharp eyes and eyelashes, crisp facial microtexture, precise focus on the face, strong local contrast without oversharpening.",
		"Maintain the same facial proportions, hairline, body proportions, and signature visual traits across generations.",
		"Do not resemble any real person or public figure.",
	}
	if token := strings.TrimSpace(req.IdentityEmbeddingToken); token != "" {
		weight := req.IdentityEmbeddingWeight
		if weight <= 0 { weight = 1.1 }
		parts = append([]string{fmt.Sprintf("(%s:%.2f)", token, weight)}, parts...)
	}
	if strings.TrimSpace(req.Scene) != "" {
		parts = append(parts, "Scene: "+strings.TrimSpace(req.Scene)+".")
	}
	if strings.TrimSpace(p.IdentityReference.HairMode) != "" && strings.Contains(strings.ToLower(req.Theme), "identity") {
		parts = append(parts, "Identity-reference hair: "+strings.TrimSpace(p.IdentityReference.HairMode)+".")
	}
	if strings.TrimSpace(p.AdultInterest.Cue) != "" {
		parts = append(parts, "Subtle adult-coded character motif: "+strings.TrimSpace(p.AdultInterest.Cue)+". Keep it non-explicit and secondary to the scene.")
	}
	if barefootDue(p, req) {
		parts = append(parts, "Wardrobe/pose cue: bare feet visible naturally in the composition; feet anatomically correct, clean, non-explicit, and contextually plausible.")
	}
	if len(p.Hobbies) > 0 {
		parts = append(parts, "Character context: "+strings.Join(p.Hobbies, ", ")+".")
	}
	if strings.TrimSpace(p.Voice) != "" {
		parts = append(parts, "Personality cue: "+strings.TrimSpace(p.Voice)+".")
	}
	return strings.Join(parts, " ")
}

func arcEmbeddingImage(ctx context.Context, m *nativecore.Manager, img image.Image) ([]float64, string, error) {
	const alignment = "scrfd-5pt-112"
	if m.FaceDetector == "" {
		return nil, alignment, fmt.Errorf("SCRFD face detector is not configured")
	}
	if m.IdentityVision == "" {
		return nil, alignment, fmt.Errorf("ArcFace embedding model is not configured")
	}
	prep, err := ident.SCRFDInputImage(img)
	if err != nil { return nil, alignment, fmt.Errorf("prepare SCRFD input: %w", err) }
	outputs, _, err := m.Detect(ctx, prep.Tensor)
	if err != nil { return nil, alignment, fmt.Errorf("SCRFD detection failed: %w", err) }
	faces, err := ident.DecodeSCRFD(outputs, prep, ident.SCRFDThreshold(0.5), 0.4)
	if err != nil || len(faces) == 0 {
		if err == nil { err = fmt.Errorf("no face detected") }
		return nil, alignment, fmt.Errorf("SCRFD landmarks unavailable: %w", err)
	}
	input, err := ident.ArcFaceInputAlignedImage(img, faces[0].Landmarks)
	if err != nil { return nil, alignment, fmt.Errorf("five-point alignment failed: %w", err) }
	vec, _, err := m.Embed(ctx, input)
	if err != nil { return nil, alignment, fmt.Errorf("ArcFace embedding failed: %w", err) }
	return ident.Normalize(vec), alignment, nil
}

func arcEmbedding(ctx context.Context, m *nativecore.Manager, raw []byte) ([]float64, string, error) {
	img,_,err:=image.Decode(bytes.NewReader(raw))
	if err!=nil { return nil,"scrfd-5pt-112",fmt.Errorf("decode image: %w",err) }
	return arcEmbeddingImage(ctx,m,img)
}

func loadReferences(root, personaID string) ([][]byte, []string, error) {
	dir := filepath.Join(root, personaID)
	entries, err := os.ReadDir(dir)
	if os.IsNotExist(err) {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })

	type candidate struct {
		path string
		data []byte
	}
	candidates := make([]candidate, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() { continue }
		name := strings.ToLower(entry.Name())
		ext := strings.ToLower(filepath.Ext(name))
		if ext != ".png" && ext != ".jpg" && ext != ".jpeg" { continue }
		if strings.HasPrefix(name, "master_") || strings.HasPrefix(name, "contact_") || strings.Contains(name, "_rear") {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		b, err := os.ReadFile(path)
		if err != nil { continue }
		candidates = append(candidates, candidate{path:path, data:b})
	}
	if len(candidates) == 0 { return nil, nil, nil }

	const maxRefs = 8
	selected := candidates
	if len(candidates) > maxRefs {
		selected = make([]candidate, 0, maxRefs)
		for i := 0; i < maxRefs; i++ {
			idx := int(math.Round(float64(i) * float64(len(candidates)-1) / float64(maxRefs-1)))
			selected = append(selected, candidates[idx])
		}
	}
	refs := make([][]byte, 0, len(selected))
	paths := make([]string, 0, len(selected))
	for _, item := range selected {
		refs = append(refs, item.data)
		paths = append(paths, item.path)
	}
	return refs, paths, nil
}

type referenceEmbedding struct {
	index int
	vec   []float64
}

func embedReferences(ctx context.Context, m *nativecore.Manager, refs [][]byte, paths []string) ([]referenceEmbedding, []string) {
	out := make([]referenceEmbedding, 0, len(refs))
	failures := make([]string, 0)
	for i, ref := range refs {
		vec, _, err := arcEmbedding(ctx, m, ref)
		if err != nil {
			label := fmt.Sprintf("reference[%d]", i)
			if i < len(paths) && strings.TrimSpace(paths[i]) != "" { label = paths[i] }
			failures = append(failures, fmt.Sprintf("%s: %v", label, err))
			continue
		}
		out = append(out, referenceEmbedding{index:i, vec:vec})
	}
	return out, failures
}

func referenceCentroid(refs []referenceEmbedding) ([]float64, error) {
	if len(refs) == 0 { return nil, fmt.Errorf("no reference embeddings") }
	dim := len(refs[0].vec)
	if dim == 0 { return nil, fmt.Errorf("empty reference embedding") }
	out := make([]float64, dim)
	count := 0
	for _, ref := range refs {
		if len(ref.vec) != dim { continue }
		for i, v := range ref.vec { out[i] += v }
		count++
	}
	if count == 0 { return nil, fmt.Errorf("no compatible reference embeddings") }
	for i := range out { out[i] /= float64(count) }
	return ident.Normalize(out), nil
}

func scoreIdentityImageCached(ctx context.Context, m *nativecore.Manager, generated image.Image, refs []referenceEmbedding, threshold, meanThreshold float64) IdentityResult {
	result := IdentityResult{
		Threshold: threshold,
		MeanThreshold: meanThreshold,
		ReferenceCount: len(refs),
		Model: "arcface-w600k-r50-qnn",
		Metric: "cosine",
		NPU: true,
	}
	if len(refs) == 0 {
		result.Reason = "no_reference_embedding_succeeded"
		return result
	}
	genVec, alignment, err := arcEmbeddingImage(ctx, m, generated)
	result.Alignment = alignment
	if err != nil {
		result.Reason = err.Error()
		return result
	}
	scores := make([]float64, 0, len(refs))
	for _, ref := range refs {
		score, err := ident.Cosine(genVec, ref.vec)
		if err == nil { scores = append(scores, score) }
	}
	if len(scores) == 0 {
		result.Reason = "no_reference_embedding_succeeded"
		return result
	}
	maxScore := scores[0]
	sum := 0.0
	for _, score := range scores {
		if score > maxScore { maxScore = score }
		sum += score
	}
	result.Scored = true
	result.Score = maxScore
	result.MeanScore = sum / float64(len(scores))
	result.ReferenceCount = len(scores)
	result.Passed = result.Score >= threshold && result.MeanScore >= meanThreshold
	return result
}

func selectCanonicalReference(refs [][]byte, paths []string, embedded []referenceEmbedding) ([]byte, string, float64, error) {
	if len(refs) == 0 {
		return nil, "", 0, fmt.Errorf("no identity references")
	}
	if len(embedded) == 0 {
		return nil, "", 0, fmt.Errorf("no reference embedding succeeded")
	}
	if len(embedded) == 1 {
		path := ""
		if embedded[0].index < len(paths) { path = paths[embedded[0].index] }
		return refs[embedded[0].index], path, 1, nil
	}

	best := 0
	bestMean := -2.0
	for i := range embedded {
		sum := 0.0
		count := 0
		for j := range embedded {
			if i == j { continue }
			score, err := ident.Cosine(embedded[i].vec, embedded[j].vec)
			if err != nil { continue }
			sum += score
			count++
		}
		if count == 0 { continue }
		mean := sum / float64(count)
		if mean > bestMean {
			best = i
			bestMean = mean
		}
	}
	path := ""
	if embedded[best].index < len(paths) { path = paths[embedded[best].index] }
	return refs[embedded[best].index], path, bestMean, nil
}

func rankedReferenceEmbeddings(refs []referenceEmbedding) []referenceEmbedding {
	if len(refs) <= 1 { return append([]referenceEmbedding(nil), refs...) }
	type ranked struct {
		ref referenceEmbedding
		mean float64
	}
	items := make([]ranked, 0, len(refs))
	for i := range refs {
		sum := 0.0
		count := 0
		for j := range refs {
			if i == j { continue }
			s, err := ident.Cosine(refs[i].vec, refs[j].vec)
			if err != nil { continue }
			sum += s
			count++
		}
		mean := -2.0
		if count > 0 { mean = sum / float64(count) }
		items = append(items, ranked{ref:refs[i], mean:mean})
	}
	sort.SliceStable(items, func(i,j int) bool { return items[i].mean > items[j].mean })
	out := make([]referenceEmbedding, 0, len(items))
	for _, item := range items { out = append(out, item.ref) }
	return out
}

func betterIdentityQuality(a IdentityResult, aq imagemetrics.Metrics, b IdentityResult, bq imagemetrics.Metrics, qualityThreshold float64) bool {
	// Identity is a hard constraint. Quality cannot compensate for a weaker face.
	aQualityPass := aq.LocalScore >= qualityThreshold
	bQualityPass := bq.LocalScore >= qualityThreshold
	aAccepted := a.Passed && aQualityPass
	bAccepted := b.Passed && bQualityPass
	if aAccepted != bAccepted { return aAccepted }
	if a.Passed != b.Passed { return a.Passed }
	if a.Score != b.Score { return a.Score > b.Score }
	if a.MeanScore != b.MeanScore { return a.MeanScore > b.MeanScore }
	if aQualityPass != bQualityPass { return aQualityPass }
	return aq.LocalScore > bq.LocalScore
}

func scoreIdentityImage(ctx context.Context, m *nativecore.Manager, generated image.Image, refs [][]byte, threshold, meanThreshold float64) IdentityResult {
	result := IdentityResult{
		Threshold: threshold,
		MeanThreshold: meanThreshold,
		ReferenceCount: len(refs),
		Model: "arcface-w600k-r50-qnn",
		Metric: "cosine",
		NPU: true,
	}
	if len(refs) == 0 {
		result.Reason = "no_reference_pack"
		return result
	}
	genVec, alignment, err := arcEmbeddingImage(ctx, m, generated)
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
	result.Passed = maxScore >= threshold && result.MeanScore >= meanThreshold
	return result
}


func scoreIdentity(ctx context.Context, m *nativecore.Manager, generated []byte, refs [][]byte, threshold, meanThreshold float64) IdentityResult {
	img,_,err:=image.Decode(bytes.NewReader(generated))
	if err!=nil {
		return IdentityResult{Threshold:threshold,MeanThreshold:meanThreshold,ReferenceCount:len(refs),Model:"arcface-w600k-r50-qnn",Metric:"cosine",NPU:true,Reason:"decode image: "+err.Error()}
	}
	return scoreIdentityImage(ctx,m,img,refs,threshold,meanThreshold)
}

type generatedFrame struct {
	Image image.Image
	Encoded []byte
}

func encodeFramePNG(frame generatedFrame) ([]byte,error) {
	pngMagic:=[]byte{0x89,'P','N','G',0x0d,0x0a,0x1a,0x0a}
	if len(frame.Encoded)>=len(pngMagic) && bytes.Equal(frame.Encoded[:len(pngMagic)],pngMagic) {
		if _,format,err:=image.DecodeConfig(bytes.NewReader(frame.Encoded)); err==nil && format=="png" {
			return frame.Encoded,nil
		}
	}
	if frame.Image==nil {
		return nil,fmt.Errorf("cannot encode PNG: generated frame has no image")
	}
	var buf bytes.Buffer
	if err:=png.Encode(&buf,frame.Image);err!=nil{return nil,err}
	out:=buf.Bytes()
	if len(out)<len(pngMagic) || !bytes.Equal(out[:len(pngMagic)],pngMagic) {
		return nil,fmt.Errorf("PNG encoder returned invalid signature")
	}
	return out,nil
}

func documentsMirrorRoot() string {
	if root := strings.TrimSpace(os.Getenv("SPICE_DOCUMENTS_ROOT")); root != "" {
		return filepath.Join(root, "sh")
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return ""
	}
	documents := filepath.Join(home, "storage", "documents")
	if info, err := os.Stat(documents); err == nil && info.IsDir() {
		return filepath.Join(documents, "sh")
	}
	return ""
}

func randomID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err == nil {
		return hex.EncodeToString(b[:])
	}
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

func emitProgress(req Request, percent float64, stage string, metrics map[string]any) {
	if req.Progress != nil { req.Progress(ProgressEvent{Percent: percent, Stage: stage, Metrics: metrics}) }
}

func generationBackend(req Request) string {
	backend := strings.ToLower(strings.TrimSpace(req.Generator))
	if backend == "" {
		backend = strings.ToLower(strings.TrimSpace(os.Getenv("SPICE_IDENTITY_GENERATOR")))
	}
	if backend == "" || backend == "auto" {
		if strings.TrimSpace(os.Getenv("LOCAL_DREAM_URL")) != "" {
			return "local-dream"
		}
		return "qnn"
	}
	switch backend {
	case "local-dream", "localdream", "ld":
		return "local-dream"
	default:
		return "qnn"
	}
}

func resolveIdentityEmbedding(ctx context.Context, req *Request, p Persona) (map[string]any, error) {
	meta := map[string]any{
		"identity_embedding_requested": false,
		"identity_embedding_loaded": false,
	}
	if req == nil { return meta, nil }

	token := strings.TrimSpace(req.IdentityEmbeddingToken)
	if token == "" { token = strings.TrimSpace(p.IdentityReference.EmbeddingToken) }
	weight := req.IdentityEmbeddingWeight
	if weight <= 0 { weight = p.IdentityReference.EmbeddingWeight }
	if weight <= 0 { weight = 1.1 }

	if token == "" || generationBackend(*req) != "local-dream" {
		return meta, nil
	}
	meta["identity_embedding_requested"] = true
	meta["identity_embedding_token"] = token
	meta["identity_embedding_weight"] = weight

	client := localdream.FromEnv()
	ok, inv, err := client.HasEmbedding(ctx, token)
	if err == nil && !ok {
		// The user may have just imported the safetensors file while the model
		// was already running. Ask Local Dream to rescan its embeddings dir once.
		if reloaded, reloadErr := client.ReloadEmbeddings(ctx); reloadErr == nil {
			inv = reloaded
			meta["identity_embedding_reloaded"] = true
			for _, name := range inv.Names {
				if strings.EqualFold(strings.TrimSpace(name), token) {
					ok = true
					break
				}
			}
		} else {
			meta["identity_embedding_reload_error"] = reloadErr.Error()
		}
	}
	if err != nil {
		meta["identity_embedding_probe_error"] = err.Error()
		if req.RequireIdentityEmbedding {
			return meta, fmt.Errorf("required Local Dream identity embedding %q could not be verified: %w", token, err)
		}
		return meta, nil
	}
	meta["identity_embedding_inventory_count"] = inv.Count
	meta["identity_embedding_loaded"] = ok
	if !ok {
		if req.RequireIdentityEmbedding {
			return meta, fmt.Errorf("required Local Dream identity embedding %q is not loaded", token)
		}
		return meta, nil
	}
	req.IdentityEmbeddingToken = token
	req.IdentityEmbeddingWeight = weight
	return meta, nil
}

func generateFrame(ctx context.Context, req Request, prompt string) (generatedFrame, map[string]any, string, error) {
	backend := generationBackend(req)
	if backend == "local-dream" {
		client := localdream.FromEnv()
		out, err := client.Generate(ctx, localdream.GenerateRequest{
			Prompt: prompt, NegativePrompt: req.NegativePrompt, Seed: req.Seed,
			Width: req.Width, Height: req.Height, Steps: req.Steps, Guidance: req.Guidance,
		})
		if err != nil { return generatedFrame{}, nil, backend, err }
		meta := out.Generation
		if meta == nil { meta = map[string]any{} }
		meta["generator"] = "local-dream"
		meta["pipeline_image_mode"] = "raw-memory"
		return generatedFrame{Image:out.Frame,Encoded:out.Encoded}, meta, backend, nil
	}

	m := nativecore.FromEnv()
	if m.ModelDir == "" {
		return generatedFrame{}, nil, backend, fmt.Errorf("QNN identity generation requires SPICE_QNN_MODEL_DIR")
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
	if req.Seed != 0 { payload["seed"] = req.Seed }
	out, err := m.Generate(ctx, payload)
	if err != nil { return generatedFrame{}, nil, backend, err }
	imageB64, _ := out["image"].(string)
	if imageB64 == "" { return generatedFrame{}, nil, backend, fmt.Errorf("QNN generation returned no image") }
	imageBytes, err := base64.StdEncoding.DecodeString(imageB64)
	if err != nil { return generatedFrame{}, nil, backend, fmt.Errorf("decode generated image: %w", err) }
	img,_,err:=image.Decode(bytes.NewReader(imageBytes))
	if err!=nil { return generatedFrame{},nil,backend,fmt.Errorf("decode generated image pixels: %w",err) }
	out["generator"] = "qnn"
	out["pipeline_image_mode"] = "decoded-memory"
	return generatedFrame{Image:img,Encoded:imageBytes}, out, backend, nil
}


func minInt(a,b int) int { if a < b { return a }; return b }

func boolOption(v *bool, fallback bool) bool {
	if v == nil { return fallback }
	return *v
}

func candidateSelectionScore(r Result) float64 {
	if !r.Identity.Scored { return -1 }
	maxNorm := r.Identity.Score
	if r.Identity.Threshold > 0 { maxNorm /= r.Identity.Threshold }
	meanNorm := r.Identity.MeanScore
	if r.Identity.MeanThreshold > 0 { meanNorm /= r.Identity.MeanThreshold }
	qualityNorm := r.Quality.LocalScore
	if r.QualityThreshold > 0 { qualityNorm /= r.QualityThreshold }
	return 0.55*maxNorm + 0.25*meanNorm + 0.20*qualityNorm
}

func betterResult(a, b Result) bool {
	aAccepted := a.Identity.Passed && a.QualityPassed
	bAccepted := b.Identity.Passed && b.QualityPassed
	if aAccepted != bAccepted { return aAccepted }
	if a.Identity.Passed != b.Identity.Passed { return a.Identity.Passed }
	if a.Identity.Score != b.Identity.Score { return a.Identity.Score > b.Identity.Score }
	if a.Identity.MeanScore != b.Identity.MeanScore { return a.Identity.MeanScore > b.Identity.MeanScore }
	if a.QualityPassed != b.QualityPassed { return a.QualityPassed }
	return a.Quality.LocalScore > b.Quality.LocalScore
}

func runSingleAttempt(
	ctx context.Context,
	req Request,
	p Persona,
	refs [][]byte,
	refEmbeddings []referenceEmbedding,
	rankedSources []referenceEmbedding,
	centroidEmbedding []float64,
	canonicalRef []byte,
	medoidScore float64,
	medoidPath string,
	swapper *faceswap.Swapper,
	attemptIndex int,
	attemptTotal int,
) (Result, error) {
	prompt := promptFor(p, req)
	m := nativecore.FromEnv()
	backend := generationBackend(req)

	emitProgress(req, 15, "best-of-n generation", map[string]any{
		"attempt":attemptIndex, "best_of_n":attemptTotal, "seed":req.Seed,
		"generator":backend, "size":fmt.Sprintf("%dx%d",req.Width,req.Height),
		"steps":req.Steps, "guidance":req.Guidance,
	})
	genStarted := time.Now()
	frame, out, backend, err := generateFrame(ctx, req, prompt)
	if err != nil { return Result{}, err }
	if out == nil { out = map[string]any{} }
	if strings.TrimSpace(req.IdentityEmbeddingToken) != "" {
		out["identity_embedding_token"] = req.IdentityEmbeddingToken
		out["identity_embedding_weight"] = req.IdentityEmbeddingWeight
		out["identity_embedding_active"] = true
	} else {
		out["identity_embedding_active"] = false
	}
	out["attempt_index"] = attemptIndex
	out["attempt_seed"] = req.Seed
	out["best_of_n"] = attemptTotal
	out["generator"] = backend
	out["generation_elapsed_ms"] = time.Since(genStarted).Milliseconds()

	emitProgress(req, 62, "generation complete", map[string]any{
		"attempt":attemptIndex, "best_of_n":attemptTotal, "seed":req.Seed,
		"generator":backend, "generation_elapsed":time.Since(genStarted).Round(time.Millisecond),
	})

	if err := os.MkdirAll(req.OutputDir, 0o755); err != nil { return Result{}, err }
	assetID := randomID()
	assetPath := filepath.Join(req.OutputDir, assetID+".png")
	imageBytes, err := encodeFramePNG(frame)
	if err != nil { return Result{}, fmt.Errorf("encode generated artifact: %w", err) }
	if err := os.WriteFile(assetPath, imageBytes, 0o644); err != nil { return Result{}, err }

	preSwapFrame := frame
	preSwapBytes := append([]byte(nil), imageBytes...)
	preSwapIdentity := IdentityResult{}
	if len(refs) > 0 {
		preSwapIdentity = scoreIdentityImageCached(ctx, m, frame.Image, refEmbeddings, req.IdentityThreshold, req.IdentityMeanThreshold)
		out["identity_pre_swap_score"] = preSwapIdentity.Score
		out["identity_pre_swap_mean"] = preSwapIdentity.MeanScore
		out["identity_pre_swap_scored"] = preSwapIdentity.Scored
	}

	if len(refs) > 0 {
		if swapper != nil && len(canonicalRef) > 0 {
			emitProgress(req, 72, "identity face transfer", map[string]any{
				"attempt":attemptIndex, "best_of_n":attemptTotal, "references":len(refs),
			})

			type swapCandidate struct {
				img image.Image
				meta faceswap.Meta
				identity IdentityResult
				quality imagemetrics.Metrics
				mode string
				sourceIndex int
			}
			swapCandidates := make([]swapCandidate, 0, len(rankedSources)+1)

			tryEmbedding := func(vec []float64, mode string, sourceIndex int) {
				if len(vec) != 512 { return }
				swappedImg, meta, swapErr := swapper.SwapImageWithEmbedding(ctx, vec, frame.Image)
				if swapErr != nil || swappedImg == nil { return }
				idResult := scoreIdentityImageCached(ctx, m, swappedImg, refEmbeddings, req.IdentityThreshold, req.IdentityMeanThreshold)
				if !idResult.Scored { return }
				q, qErr := imagemetrics.AnalyzeImage(swappedImg)
				if qErr != nil || q.LocalScore < req.QualityThreshold { return }
				// Never accept a transfer that regresses either identity metric.
				if preSwapIdentity.Scored && (idResult.Score < preSwapIdentity.Score || idResult.MeanScore < preSwapIdentity.MeanScore) { return }
				swapCandidates = append(swapCandidates, swapCandidate{
					img:swappedImg, meta:meta, identity:idResult, quality:q, mode:mode, sourceIndex:sourceIndex,
				})
			}

			// Test every usable real reference independently. A single medoid or
			// centroid can hide a much stronger source for this particular target.
			for _, ref := range rankedSources {
				tryEmbedding(ref.vec, "reference_individual", ref.index)
			}
			// Also test the centroid as a final diversity candidate.
			if len(centroidEmbedding) == 512 {
				tryEmbedding(centroidEmbedding, "reference_centroid", -1)
			}

			if len(swapCandidates) == 0 {
				out["faceswap_applied"] = false
				out["faceswap_reason"] = "all face-swap source trials failed"
			} else {
				bestSwap := swapCandidates[0]
				for _, candidate := range swapCandidates[1:] {
					if betterIdentityQuality(candidate.identity, candidate.quality, bestSwap.identity, bestSwap.quality, req.QualityThreshold) {
						bestSwap = candidate
					}
				}
				frame = generatedFrame{Image:bestSwap.img}
				imageBytes, err = encodeFramePNG(frame)
				if err != nil { return Result{}, fmt.Errorf("encode swapped image: %w", err) }
				frame.Encoded = imageBytes
				if err := os.WriteFile(assetPath, imageBytes, 0o644); err != nil {
					return Result{}, fmt.Errorf("write swapped artifact: %w", err)
				}
				out["faceswap_applied"] = true
				out["faceswap_source_mode"] = bestSwap.mode
				out["faceswap_source_index"] = bestSwap.sourceIndex
				out["faceswap_trials"] = len(swapCandidates)
				out["faceswap_model"] = bestSwap.meta.Model
				out["faceswap_alignment"] = bestSwap.meta.Alignment
				out["faceswap_target_score"] = bestSwap.meta.TargetScore
				out["faceswap_reference_medoid_score"] = medoidScore
				out["faceswap_reference_medoid_path"] = medoidPath
			}
		} else {
			out["faceswap_applied"] = false
			if _, ok := out["faceswap_reason"]; !ok {
				out["faceswap_reason"] = "face swap assets unavailable"
			}
		}
	}

	emitProgress(req, 76, "SCRFD + ArcFace identity", map[string]any{
		"attempt":attemptIndex, "best_of_n":attemptTotal,
		"references":len(refs), "identity_threshold":req.IdentityThreshold,
	})
	identity := scoreIdentityImageCached(ctx, m, frame.Image, refEmbeddings, req.IdentityThreshold, req.IdentityMeanThreshold)
	if applied, _ := out["faceswap_applied"].(bool); applied && preSwapIdentity.Scored && identity.Scored && identity.Score < preSwapIdentity.Score {
		out["faceswap_reverted"] = true
		out["faceswap_revert_reason"] = fmt.Sprintf("post-swap identity %.6f below pre-swap %.6f", identity.Score, preSwapIdentity.Score)
		out["identity_post_swap_score"] = identity.Score
		out["identity_post_swap_mean"] = identity.MeanScore
		frame = preSwapFrame
		imageBytes = preSwapBytes
		identity = preSwapIdentity
		if err := os.WriteFile(assetPath, imageBytes, 0o644); err != nil {
			return Result{}, fmt.Errorf("restore pre-swap artifact: %w", err)
		}
	} else if applied {
		out["faceswap_reverted"] = false
		out["identity_post_swap_score"] = identity.Score
		out["identity_post_swap_mean"] = identity.MeanScore
	}

	emitProgress(req, 88, "image quality analysis", map[string]any{
		"attempt":attemptIndex, "best_of_n":attemptTotal,
	})
	quality, err := imagemetrics.AnalyzeImage(frame.Image)
	if err != nil { return Result{}, err }
	qualityPassed := quality.LocalScore >= req.QualityThreshold

	status := "proposed"
	if len(refs) > 0 && !identity.Scored {
		status = "rejected_identity_runtime"
	} else if identity.Scored && !identity.Passed {
		status = "rejected_identity"
	} else if !qualityPassed {
		status = "rejected_quality"
	} else if len(refs) == 0 {
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

	if mirrorRoot := documentsMirrorRoot(); mirrorRoot != "" {
		dir := filepath.Join(mirrorRoot, p.ID)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return Result{}, fmt.Errorf("create documents mirror: %w", err)
		}
		docAssetPath := filepath.Join(dir, assetID+".png")
		if err := os.WriteFile(docAssetPath, imageBytes, 0o644); err != nil {
			return Result{}, fmt.Errorf("copy generated asset to documents: %w", err)
		}
		result.DocumentsPath = docAssetPath
	}

	meta, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(metaPath, meta, 0o644); err != nil { return Result{}, err }
	if result.DocumentsPath != "" {
		if err := os.WriteFile(result.DocumentsPath+".json", meta, 0o644); err != nil {
			return Result{}, fmt.Errorf("copy generated metadata to documents: %w", err)
		}
	}

	emitProgress(req, 94, "attempt scored", map[string]any{
		"attempt":attemptIndex, "best_of_n":attemptTotal, "seed":req.Seed,
		"status":status, "identity_score":identity.Score, "identity_mean":identity.MeanScore,
		"identity_pass":identity.Passed, "quality_score":quality.LocalScore, "quality_pass":qualityPassed,
		"asset":assetPath,
	})
	return result, nil
}

func summarizeAttempt(index int, seed int64, result Result) AttemptSummary {
	return AttemptSummary{
		Index:index,
		Seed:seed,
		Status:result.Status,
		AssetPath:result.AssetPath,
		MetadataPath:result.MetadataPath,
		IdentityScore:result.Identity.Score,
		IdentityMean:result.Identity.MeanScore,
		IdentityPass:result.Identity.Passed,
		QualityScore:result.Quality.LocalScore,
		QualityPass:result.QualityPassed,
		SelectionScore:candidateSelectionScore(result),
	}
}

func refineAttemptWithFaceSwap(
	ctx context.Context,
	req Request,
	result Result,
	refEmbeddings []referenceEmbedding,
	rankedSources []referenceEmbedding,
	centroidEmbedding []float64,
	medoidScore float64,
	medoidPath string,
	swapper *faceswap.Swapper,
) (Result, error) {
	if swapper == nil || len(refEmbeddings) == 0 {
		return result, nil
	}
	raw, err := os.ReadFile(result.AssetPath)
	if err != nil { return result, fmt.Errorf("read preselected artifact: %w", err) }
	img, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil { return result, fmt.Errorf("decode preselected artifact: %w", err) }

	type swapCandidate struct {
		img image.Image
		meta faceswap.Meta
		identity IdentityResult
		quality imagemetrics.Metrics
		mode string
		sourceIndex int
	}
	m := nativecore.FromEnv()
	candidates := make([]swapCandidate, 0, len(rankedSources)+1)

	tryEmbedding := func(vec []float64, mode string, sourceIndex int) {
		if len(vec) != 512 { return }
		swapped, meta, swapErr := swapper.SwapImageWithEmbedding(ctx, vec, img)
		if swapErr != nil || swapped == nil { return }
		idResult := scoreIdentityImageCached(ctx, m, swapped, refEmbeddings, req.IdentityThreshold, req.IdentityMeanThreshold)
		if !idResult.Scored { return }
		q, qErr := imagemetrics.AnalyzeImage(swapped)
		if qErr != nil || q.LocalScore < req.QualityThreshold { return }
		// The original candidate is the floor: a transfer may not lower max or mean identity.
		if result.Identity.Scored && (idResult.Score < result.Identity.Score || idResult.MeanScore < result.Identity.MeanScore) { return }
		candidates = append(candidates, swapCandidate{
			img:swapped, meta:meta, identity:idResult, quality:q, mode:mode, sourceIndex:sourceIndex,
		})
	}

	for _, ref := range rankedSources {
		tryEmbedding(ref.vec, "reference_individual", ref.index)
	}
	if len(centroidEmbedding) == 512 {
		tryEmbedding(centroidEmbedding, "reference_centroid", -1)
	}

	if result.Generation == nil { result.Generation = map[string]any{} }
	result.Generation["faceswap_preselected"] = true
	result.Generation["faceswap_trials"] = len(candidates)
	if len(candidates) == 0 {
		result.Generation["faceswap_applied"] = false
		result.Generation["faceswap_reason"] = "all preselected face-swap source trials failed"
		return result, nil
	}

	bestSwap := candidates[0]
	for _, candidate := range candidates[1:] {
		if betterIdentityQuality(candidate.identity, candidate.quality, bestSwap.identity, bestSwap.quality, req.QualityThreshold) {
			bestSwap = candidate
		}
	}

	// Keep the original if the transfer does not improve the combined identity/quality decision.
	if !betterIdentityQuality(bestSwap.identity, bestSwap.quality, result.Identity, result.Quality, req.QualityThreshold) {
		result.Generation["faceswap_applied"] = false
		result.Generation["faceswap_reverted"] = true
		result.Generation["faceswap_revert_reason"] = "best transfer did not improve pre-swap identity/quality"
		result.Generation["identity_post_swap_score"] = bestSwap.identity.Score
		result.Generation["identity_post_swap_mean"] = bestSwap.identity.MeanScore
		return result, nil
	}

	frame := generatedFrame{Image:bestSwap.img}
	encoded, err := encodeFramePNG(frame)
	if err != nil { return result, fmt.Errorf("encode refined artifact: %w", err) }
	if err := os.WriteFile(result.AssetPath, encoded, 0o644); err != nil {
		return result, fmt.Errorf("write refined artifact: %w", err)
	}
	if result.DocumentsPath != "" {
		if err := os.WriteFile(result.DocumentsPath, encoded, 0o644); err != nil {
			return result, fmt.Errorf("write refined documents artifact: %w", err)
		}
	}

	result.Identity = bestSwap.identity
	result.Quality = bestSwap.quality
	result.QualityPassed = bestSwap.quality.LocalScore >= req.QualityThreshold
	switch {
	case !result.Identity.Scored:
		result.Status = "rejected_identity_runtime"
	case !result.Identity.Passed:
		result.Status = "rejected_identity"
	case !result.QualityPassed:
		result.Status = "rejected_quality"
	default:
		result.Status = "proposed"
	}
	result.OK = result.Status == "proposed"

	result.Generation["faceswap_applied"] = true
	result.Generation["faceswap_reverted"] = false
	result.Generation["faceswap_source_mode"] = bestSwap.mode
	result.Generation["faceswap_source_index"] = bestSwap.sourceIndex
	result.Generation["faceswap_model"] = bestSwap.meta.Model
	result.Generation["faceswap_alignment"] = bestSwap.meta.Alignment
	result.Generation["faceswap_target_score"] = bestSwap.meta.TargetScore
	result.Generation["faceswap_reference_medoid_score"] = medoidScore
	result.Generation["faceswap_reference_medoid_path"] = medoidPath
	result.Generation["identity_post_swap_score"] = bestSwap.identity.Score
	result.Generation["identity_post_swap_mean"] = bestSwap.identity.MeanScore

	meta, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(result.MetadataPath, meta, 0o644); err != nil {
		return result, fmt.Errorf("write refined metadata: %w", err)
	}
	if result.DocumentsPath != "" {
		if err := os.WriteFile(result.DocumentsPath+".json", meta, 0o644); err != nil {
			return result, fmt.Errorf("write refined documents metadata: %w", err)
		}
	}
	return result, nil
}

func Run(ctx context.Context, req Request) (Result, error) {
	emitProgress(req, 2, "loading persona", nil)
	p, err := loadPersona(req)
	if err != nil { return Result{}, err }

	if strings.TrimSpace(req.Theme) == "" { req.Theme = "identity reference portrait" }
	if req.Width == 0 { req.Width = 1024 }
	if req.Height == 0 { req.Height = 1024 }
	if req.Steps == 0 { req.Steps = 20 }
	if req.Guidance == 0 { req.Guidance = 7.0 }
	if req.OutputDir == "" { req.OutputDir = filepath.Join("data", "identity-candidates", p.ID) }
	if req.ReferenceRoot == "" { req.ReferenceRoot = filepath.Join("data", "references") }
	if req.IdentityThreshold == 0 { req.IdentityThreshold = 0.82 }
	if req.IdentityMeanThreshold == 0 { req.IdentityMeanThreshold = 0.70 }
	if req.QualityThreshold == 0 { req.QualityThreshold = 0.78 }
	if req.NegativePrompt == "" { req.NegativePrompt = defaultNegative }
	if req.BestOfN <= 0 {
		if strings.Contains(strings.ToLower(req.Theme), "identity") { req.BestOfN = 4 } else { req.BestOfN = 1 }
	}
	if req.BestOfN > 64 { req.BestOfN = 64 }
	if req.SwapTopK <= 0 { req.SwapTopK = minInt(3, req.BestOfN) }
	if req.SwapTopK > req.BestOfN { req.SwapTopK = req.BestOfN }

	embeddingMeta, err := resolveIdentityEmbedding(ctx, &req, p)
	if err != nil { return Result{}, err }

	stopOnAccept := boolOption(req.StopOnAccept, true)
	saveAll := boolOption(req.SaveAllAttempts, true)

	emitProgress(req, 8, "loading identity references", map[string]any{
		"persona":p.ID, "best_of_n":req.BestOfN,
	})
	refs, refPaths, err := loadReferences(req.ReferenceRoot, p.ID)
	if err != nil { return Result{}, fmt.Errorf("load references: %w", err) }

	m := nativecore.FromEnv()
	refEmbeddings, refEmbeddingFailures := embedReferences(ctx, m, refs, refPaths)
	if len(refs) > 0 && len(refEmbeddings) == 0 {
		detail := "unknown reference embedding failure"
		if len(refEmbeddingFailures) > 0 { detail = strings.Join(refEmbeddingFailures, " | ") }
		return Result{}, fmt.Errorf("all identity reference embeddings failed: %s", detail)
	}
	rankedSources := rankedReferenceEmbeddings(refEmbeddings)
	centroidEmbedding, _ := referenceCentroid(refEmbeddings)
	var canonicalRef []byte
	canonicalRefPath := ""
	medoidScore := 0.0
	var swapper *faceswap.Swapper
	if len(refs) > 0 {
		cfg := faceswap.ConfigFromEnv()
		if faceswap.Available(cfg) {
			canonicalRef, canonicalRefPath, medoidScore, err = selectCanonicalReference(refs, refPaths, refEmbeddings)
			if err == nil {
				swapper, err = faceswap.New(ctx, cfg, m)
				if err != nil { swapper = nil }
			}
		}
	}
	if swapper != nil { defer swapper.Close() }

	baseSeed := req.Seed
	if baseSeed == 0 { baseSeed = time.Now().UnixNano() }

	attempts := make([]AttemptSummary, 0, req.BestOfN)
	type successfulAttempt struct {
		attemptListIndex int
		attemptIndex int
		seed int64
		req Request
		result Result
	}
	successes := make([]successfulAttempt, 0, req.BestOfN)
	completed := 0
	acceptedPreSwap := false

	// Stage 1: generate every candidate and cheaply score identity + quality.
	// Do not run InSwapper here; that is reserved for the strongest candidates.
	for i := 0; i < req.BestOfN; i++ {
		attemptReq := req
		attemptReq.Seed = baseSeed + int64(i)
		attemptIndex := i + 1

		result, attemptErr := runSingleAttempt(
			ctx, attemptReq, p, refs, refEmbeddings, rankedSources, centroidEmbedding,
			canonicalRef, medoidScore, canonicalRefPath, nil, attemptIndex, req.BestOfN,
		)
		if attemptErr != nil {
			attempts = append(attempts, AttemptSummary{
				Index:attemptIndex, Seed:attemptReq.Seed, Status:"attempt_error", Error:attemptErr.Error(),
			})
			emitProgress(req, 70, "preselection attempt failed", map[string]any{
				"attempt":attemptIndex, "best_of_n":req.BestOfN, "seed":attemptReq.Seed, "error":attemptErr.Error(),
			})
			continue
		}
		completed++
		attempts = append(attempts, summarizeAttempt(attemptIndex, attemptReq.Seed, result))
		successes = append(successes, successfulAttempt{
			attemptListIndex:len(attempts)-1,
			attemptIndex:attemptIndex,
			seed:attemptReq.Seed,
			req:attemptReq,
			result:result,
		})

		if stopOnAccept && result.Identity.Passed && result.QualityPassed {
			acceptedPreSwap = true
			break
		}
	}

	if len(successes) == 0 {
		lastErr := "all best-of-n attempts failed"
		if len(attempts) > 0 && attempts[len(attempts)-1].Error != "" {
			lastErr += ": " + attempts[len(attempts)-1].Error
		}
		return Result{}, fmt.Errorf("%s", lastErr)
	}

	// Stage 2: only the strongest pre-swap candidates pay the multi-source
	// InSwapper cost. This avoids up to three swap inferences for every seed.
	if swapper != nil && !acceptedPreSwap {
		order := make([]int, len(successes))
		for i := range order { order[i] = i }
		sort.SliceStable(order, func(i,j int) bool {
			return betterResult(successes[order[i]].result, successes[order[j]].result)
		})
		k := minInt(req.SwapTopK, len(order))
		emitProgress(req, 74, "face-swap preselection", map[string]any{
			"generated":len(successes), "swap_top_k":k, "best_of_n":req.BestOfN,
		})
		for rank := 0; rank < k; rank++ {
			idx := order[rank]
			item := &successes[idx]
			refined, refineErr := refineAttemptWithFaceSwap(
				ctx, item.req, item.result, refEmbeddings, rankedSources,
				centroidEmbedding, medoidScore, canonicalRefPath, swapper,
			)
			if refineErr != nil {
				if item.result.Generation == nil { item.result.Generation = map[string]any{} }
				item.result.Generation["faceswap_refine_error"] = refineErr.Error()
			} else {
				item.result = refined
			}
			item.result.Generation["preselection_rank"] = rank + 1
			item.result.Generation["swap_top_k"] = k
			attempts[item.attemptListIndex] = summarizeAttempt(item.attemptIndex, item.seed, item.result)
		}
	}

	var best Result
	bestSuccess := 0
	for i := range successes {
		if i == 0 || betterResult(successes[i].result, best) {
			best = successes[i].result
			bestSuccess = i
		}
	}
	bestIndex := successes[bestSuccess].attemptListIndex

	selectedAttempt := attempts[bestIndex].Index
	if best.Generation == nil { best.Generation = map[string]any{} }
	best.Generation["best_of_n"] = req.BestOfN
	best.Generation["best_of_n_completed"] = completed
	best.Generation["selected_attempt"] = selectedAttempt
	best.Generation["selected_seed"] = attempts[bestIndex].Seed
	best.Generation["stop_on_accept"] = stopOnAccept
	best.Generation["reference_embeddings_cached"] = len(refEmbeddings)
	best.Generation["reference_embedding_failures"] = refEmbeddingFailures
	best.Generation["reference_centroid_dimensions"] = len(centroidEmbedding)
	best.Generation["swap_source_candidates"] = len(rankedSources)+1
	best.Generation["swap_top_k"] = req.SwapTopK
	best.Generation["two_stage_preselection"] = true
	best.Generation["selection_score"] = candidateSelectionScore(best)
	for k,v := range embeddingMeta { best.Generation[k] = v }

	best.Batch = &BatchSummary{
		Requested:req.BestOfN,
		Completed:completed,
		Selected:selectedAttempt,
	}
	if saveAll {
		best.Batch.Attempts = attempts
	} else {
		for _, a := range attempts {
			if a.Index == selectedAttempt { continue }
			if a.AssetPath != "" { _ = os.Remove(a.AssetPath) }
			if a.MetadataPath != "" { _ = os.Remove(a.MetadataPath) }
			if a.AssetPath != "" { _ = os.Remove(a.AssetPath+".json") }
		}
	}

	meta, _ := json.MarshalIndent(best, "", "  ")
	if err := os.WriteFile(best.MetadataPath, meta, 0o644); err != nil { return Result{}, err }
	if best.DocumentsPath != "" {
		if err := os.WriteFile(best.DocumentsPath+".json", meta, 0o644); err != nil {
			return Result{}, fmt.Errorf("update selected documents metadata: %w", err)
		}
	}

	emitProgress(req, 100, "complete", map[string]any{
		"status":best.Status,
		"identity_score":best.Identity.Score,
		"quality_score":best.Quality.LocalScore,
		"asset":best.AssetPath,
		"documents":best.DocumentsPath,
		"selected_attempt":selectedAttempt,
		"selected_seed":attempts[bestIndex].Seed,
		"best_of_n":req.BestOfN,
		"completed":completed,
	})
	return best, nil
}

func reqPrompt(s string) string { return s }
