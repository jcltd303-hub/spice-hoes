package identity

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPersonaBankAddAndWrite(t *testing.T) {
	tmpDir := t.TempDir()
	outPath := filepath.Join(tmpDir, "test_bank.safetensors")

	bank := NewPersonaBank("arcface-r50")
	if bank.Version != "1" {
		t.Fatalf("expected version 1, got %s", bank.Version)
	}

	embedding := make([]float32, 512)
	for i := range embedding {
		embedding[i] = float32(i) / 512.0
	}

	p := PersonaEmbedding{
		ID:        "test_persona",
		Name:      "Test Persona",
		Embedding: embedding,
		Metadata: map[string]any{
			"age": 28,
		},
	}

	if err := bank.AddPersona(p); err != nil {
		t.Fatalf("failed to add persona: %v", err)
	}

	if len(bank.Tensors) != 1 {
		t.Fatalf("expected 1 tensor, got %d", len(bank.Tensors))
	}

	if err := bank.WriteFile(outPath); err != nil {
		t.Fatalf("failed to write safetensors: %v", err)
	}

	if _, err := os.Stat(outPath); err != nil {
		t.Fatalf("safetensors file not created: %v", err)
	}

	loaded, err := LoadFile(outPath)
	if err != nil {
		t.Fatalf("failed to load safetensors: %v", err)
	}

	if loaded.Model != "arcface-r50" {
		t.Fatalf("expected model arcface-r50, got %s", loaded.Model)
	}

	if len(loaded.Tensors) != 1 {
		t.Fatalf("expected 1 tensor in loaded bank, got %d", len(loaded.Tensors))
	}

	loadedEmbedding, ok := loaded.Tensors["test_persona"]
	if !ok {
		t.Fatalf("tensor test_persona not found in loaded bank")
	}

	if len(loadedEmbedding) != 512 {
		t.Fatalf("expected embedding length 512, got %d", len(loadedEmbedding))
	}

	for i := 0; i < 512; i++ {
		expected := float32(i) / 512.0
		if loadedEmbedding[i] != expected {
			t.Errorf("embedding[%d]: expected %f, got %f", i, expected, loadedEmbedding[i])
		}
	}
}

func TestPersonaBankMultiplePersonas(t *testing.T) {
	tmpDir := t.TempDir()
	outPath := filepath.Join(tmpDir, "multi_bank.safetensors")

	bank := NewPersonaBank("arcface-r50")

	for i := 0; i < 5; i++ {
		id := string(rune('a' + i))
		embedding := make([]float32, 512)
		for j := range embedding {
			embedding[j] = float32(i*512+j) / 2560.0
		}

		p := PersonaEmbedding{
			ID:        "persona_" + id,
			Name:      "Persona " + string(rune('A'+i)),
			Embedding: embedding,
		}
		if err := bank.AddPersona(p); err != nil {
			t.Fatalf("failed to add persona %d: %v", i, err)
		}
	}

	if len(bank.Tensors) != 5 {
		t.Fatalf("expected 5 tensors, got %d", len(bank.Tensors))
	}

	if err := bank.WriteFile(outPath); err != nil {
		t.Fatalf("failed to write multi-persona safetensors: %v", err)
	}

	loaded, err := LoadFile(outPath)
	if err != nil {
		t.Fatalf("failed to load multi-persona safetensors: %v", err)
	}

	if len(loaded.Tensors) != 5 {
		t.Fatalf("expected 5 tensors in loaded bank, got %d", len(loaded.Tensors))
	}
}
