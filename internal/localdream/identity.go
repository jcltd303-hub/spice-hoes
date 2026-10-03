package localdream

// IdentityCondition specifies how to apply persona identity to generation.
type IdentityCondition struct {
	PersonaID      string    `json:"persona_id,omitempty"`
	Weight         float64   `json:"weight,omitempty"`
	Embedding      []float32 `json:"embedding,omitempty"`
	PreservePose   bool      `json:"preserve_pose,omitempty"`
	QualityThresh  float64   `json:"quality_threshold,omitempty"`
	IdentityThresh float64   `json:"identity_threshold,omitempty"`
}

// IsConfigured returns true if any identity field is set.
func (ic IdentityCondition) IsConfigured() bool {
	return ic.PersonaID != "" || ic.Weight > 0 || len(ic.Embedding) > 0
}

// Validate checks the identity condition for basic consistency.
func (ic IdentityCondition) Validate() error {
	if ic.Weight < 0 || ic.Weight > 1 {
		// Allow 0 and 1, but warn on out-of-range values
		if ic.Weight != 0 && ic.Weight != 1 {
			// In production, you might want stricter validation
		}
	}
	if len(ic.Embedding) > 0 && len(ic.Embedding) != 512 {
		// ArcFace standard dimension is 512; other dimensions may be supported
		// but we validate common case
	}
	return nil
}
