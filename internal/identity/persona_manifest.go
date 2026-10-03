package identity

import (
	"os"
	"sort"
	"strings"
)

// PersonaManifest is a lightweight JSON manifest for persona identity metadata.
type PersonaManifest struct {
	PersonaID string   `json:"persona_id"`
	Name      string   `json:"name"`
	Embedding []float32 `json:"embedding"`
	Model     string   `json:"model,omitempty"`
	Notes     []string `json:"notes,omitempty"`
}

// SaveManifest writes a simple persona definition to JSON for CLI tooling.
func SaveManifest(path string, manifest PersonaManifest) error {
	if err := os.MkdirAll(pathDir(path), 0o755); err != nil {
		return err
	}
	payload, err := jsonMarshal(manifest)
	if err != nil {
		return err
	}
	return os.WriteFile(path, payload, 0o644)
}

func jsonMarshal(v any) ([]byte, error) {
	return json.MarshalIndent(v, "", "  ")
}

func pathDir(p string) string {
	idx := strings.LastIndex(p, "/")
	if idx < 0 {
		return "."
	}
	return p[:idx]
}

// BuildFivePersonas produces a default manifest set for the five seed personas.
func BuildFivePersonas() []PersonaManifest {
	personas := []PersonaManifest{
		{PersonaID: "zara_voss", Name: "Zara Voss", Model: "arcface-r50"},
		{PersonaID: "tess_wilder", Name: "Tess Wilder", Model: "arcface-r50"},
		{PersonaID: "lila_hart", Name: "Lila Hart", Model: "arcface-r50"},
		{PersonaID: "ruby_wren", Name: "Ruby Wren", Model: "arcface-r50"},
		{PersonaID: "celeste_vale", Name: "Celeste Vale", Model: "arcface-r50"},
	}
	for i := range personas {
		personas[i].Embedding = make([]float32, 512)
		for j := range personas[i].Embedding {
			personas[i].Embedding[j] = float32((i+1)*(j+1)) / 512.0
		}
		personas[i].Notes = []string{"seeded placeholder identity vector"}
	}
	sort.Slice(personas, func(i, j int) bool { return personas[i].PersonaID < personas[j].PersonaID })
	return personas
}
