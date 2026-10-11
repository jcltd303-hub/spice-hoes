package identity

import (
	"context"
	"fmt"
	"image"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

// FaceAlignment identifies the canonical SCRFD five-point → 112x112 ArcFace
// alignment performed by EmbedFace.
const FaceAlignment = "scrfd-5pt-112"

const (
	// detectionTimeout bounds one SCRFD Detect call; embeddingTimeout bounds
	// one ArcFace Embed call. Both previously lived inline in the two
	// call-site copies this helper replaces.
	detectionTimeout = 2 * time.Minute
	embeddingTimeout = 2 * time.Minute
)

// FaceBackend is the subset of nativecore.Manager required by the face
// pipeline. *nativecore.Manager satisfies it implicitly. The interface lives
// here — rather than taking the concrete Manager — because this package is
// already imported by nativecore's dependents; depending on the concrete
// type would create an import cycle.
type FaceBackend interface {
	Detect(ctx context.Context, input []float64) ([]nativecore.TensorOutput, map[string]any, error)
	Embed(ctx context.Context, input []float64) ([]float64, map[string]any, error)
	// FaceDetectorModel and IdentityModel report the configured model paths;
	// empty means that pipeline stage is unavailable.
	FaceDetectorModel() string
	IdentityModel() string
}

// EmbedFace runs the canonical face-embedding pipeline:
//
//	SCRFD input → Detect → landmark decode (with threshold fallback)
//	→ five-point alignment → ArcFace embed → L2 normalize.
//
// It returns the normalized embedding, the backend meta enriched with
// alignment details, and the FaceAlignment identifier.
func EmbedFace(ctx context.Context, backend FaceBackend, img image.Image) ([]float64, map[string]any, string, error) {
	if backend.FaceDetectorModel() == "" {
		return nil, nil, FaceAlignment, fmt.Errorf("SPICE_FACE_DETECT_MODEL is not configured")
	}
	if backend.IdentityModel() == "" {
		return nil, nil, FaceAlignment, fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")
	}

	prep, err := SCRFDInputImage(img)
	if err != nil {
		return nil, nil, FaceAlignment, fmt.Errorf("prepare SCRFD input: %w", err)
	}

	detectCtx, detectCancel := context.WithTimeout(ctx, detectionTimeout)
	outputs, detectMeta, err := backend.Detect(detectCtx, prep.Tensor)
	detectCancel()
	if err != nil {
		return nil, nil, FaceAlignment, fmt.Errorf("SCRFD detection failed: %w", err)
	}

	faces, usedThreshold, err := DecodeSCRFDWithFallback(outputs, prep, SCRFDThreshold(0.5), 0.4)
	if err != nil || len(faces) == 0 {
		if err == nil {
			err = fmt.Errorf("no face detected")
		}
		return nil, nil, FaceAlignment, fmt.Errorf("SCRFD landmarks unavailable: %w", err)
	}

	input, err := ArcFaceInputAlignedImage(img, faces[0].Landmarks)
	if err != nil {
		return nil, nil, FaceAlignment, fmt.Errorf("five-point alignment failed: %w", err)
	}

	embedCtx, embedCancel := context.WithTimeout(ctx, embeddingTimeout)
	vec, meta, err := backend.Embed(embedCtx, input)
	embedCancel()
	if err != nil {
		return nil, nil, FaceAlignment, fmt.Errorf("ArcFace embedding failed: %w", err)
	}

	if meta == nil {
		meta = map[string]any{}
	}
	meta["alignment"] = FaceAlignment
	meta["alignment_detail"] = fmt.Sprintf("%s@%.2f", FaceAlignment, usedThreshold)
	meta["detector_latency_ms"] = detectMeta["latency_ms"]
	meta["detector_threshold"] = usedThreshold
	return Normalize(vec), meta, FaceAlignment, nil
}
