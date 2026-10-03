package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/identity"
)

func runBankGen(args []string) error {
	fs := flag.NewFlagSet("bank-gen", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	outDir := fs.String("out", "personas", "output directory for .safetensors files")
	model := fs.String("model", "arcface-r50", "identity model label")

	if err := fs.Parse(args); err != nil {
		return err
	}

	bank := identity.NewPersonaBank(*model)

	personas := []struct {
		ID        string
		Name      string
		Descr     string
		Embedding []float32
	}{
		{ID: "zara_voss", Name: "Zara Voss", Descr: "High-energy percussionist and night-market organizer"},
		{ID: "tess_wilder", Name: "Tess Wilder", Descr: "Climber, rec-league keeper, and retro-game competitor"},
		{ID: "lila_hart", Name: "Lila Hart", Descr: "Warm ceramic artist who hosts dinner parties"},
		{ID: "ruby_wren", Name: "Ruby Wren", Descr: "Fiery zine writer and amateur astronomer"},
		{ID: "celeste_vale", Name: "Celeste Vale", Descr: "Boutique hotel designer and jazz collector"},
	}

	for i, p := range personas {
		p.Embedding = make([]float32, 512)
		for j := range p.Embedding {
			p.Embedding[j] = float32((i+1)*(j+1)) / 512.0
		}

		pe := identity.PersonaEmbedding{
			ID:        p.ID,
			Name:      p.Name,
			Embedding: p.Embedding,
			Metadata: map[string]any{
				"description": p.Descr,
				"model":       *model,
				"generated":   time.Now().UTC().Format(time.RFC3339),
				"notes":       "placeholder seeded embedding — use spicemedia embed to generate from reference images",
			},
		}

		if err := bank.AddPersona(pe); err != nil {
			return fmt.Errorf("failed to add %s: %w", p.ID, err)
		}
	}

	if err := os.MkdirAll(*outDir, 0o755); err != nil {
		return err
	}

	outPath := fmt.Sprintf("%s/personas.safetensors", *outDir)
	if err := bank.WriteFile(outPath); err != nil {
		return fmt.Errorf("failed to write persona bank: %w", err)
	}

	result := map[string]any{
		"output":   outPath,
		"count":    len(bank.Tensors),
		"model":    *model,
		"version":  bank.Version,
		"personas": bank.Names,
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	return enc.Encode(result)
}

func runBankLoad(args []string) error {
	fs := flag.NewFlagSet("bank-load", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	path := fs.String("path", "", "path to .safetensors file")

	if err := fs.Parse(args); err != nil {
		return err
	}

	if *path == "" {
		return fmt.Errorf("--path is required")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = ctx

	bank, err := identity.LoadFile(*path)
	if err != nil {
		return fmt.Errorf("failed to load persona bank: %w", err)
	}

	result := map[string]any{
		"path":     *path,
		"model":    bank.Model,
		"version":  bank.Version,
		"count":    len(bank.Tensors),
		"personas": bank.Names,
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	return enc.Encode(result)
}
