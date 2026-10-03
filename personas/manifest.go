// This file defines the five seed personas for identity generation.
// Each persona has a canonical ID, name, and placeholder embedding vector.
// In production, these embeddings will be generated from reference images
// using the ArcFace model in spicemedia.

package main

import (
	"encoding/json"
	"fmt"
)

// PersonaMetadata is the immutable canonical definition for a persona.
type PersonaMetadata struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	HeightCm    int    `json:"height_cm"`
	Age         int    `json:"age"`
	BioShort    string `json:"bio_short"`
	EmbeddingDim int   `json:"embedding_dim"`
}

var Personas = map[string]PersonaMetadata{
	"zara_voss": {
		ID:           "zara_voss",
		Name:         "Zara Voss",
		HeightCm:     169,
		Age:          29,
		BioShort:     "High-energy percussionist and night-market organizer; commands a room with ease.",
		EmbeddingDim: 512,
	},
	"tess_wilder": {
		ID:           "tess_wilder",
		Name:         "Tess Wilder",
		HeightCm:     171,
		Age:          27,
		BioShort:     "Climber, rec-league keeper, retro-game competitor; rebuilt confidence after team fallout.",
		EmbeddingDim: 512,
	},
	"lila_hart": {
		ID:           "lila_hart",
		Name:         "Lila Hart",
		HeightCm:     160,
		Age:          28,
		BioShort:     "Warm ceramic artist who hosts dinner parties and grows herbs; chosen independence over compromise.",
		EmbeddingDim: 512,
	},
	"ruby_wren": {
		ID:           "ruby_wren",
		Name:         "Ruby Wren",
		HeightCm:     164,
		Age:          30,
		BioShort:     "Fiery zine writer and amateur astronomer; started publishing after failed gallery collaboration.",
		EmbeddingDim: 512,
	},
	"celeste_vale": {
		ID:           "celeste_vale",
		Name:         "Celeste Vale",
		HeightCm:     166,
		Age:          32,
		BioShort:     "Exacting boutique hotel designer and jazz collector; chose independent practice over prestigious control.",
		EmbeddingDim: 512,
	},
}

func GetPersona(id string) (PersonaMetadata, error) {
	p, ok := Personas[id]
	if !ok {
		return PersonaMetadata{}, fmt.Errorf("unknown persona: %s", id)
	}
	return p, nil
}

func ListPersonas() []PersonaMetadata {
	var out []PersonaMetadata
	for _, id := range []string{"zara_voss", "tess_wilder", "lila_hart", "ruby_wren", "celeste_vale"} {
		if p, ok := Personas[id]; ok {
			out = append(out, p)
		}
	}
	return out
}

func MarshalPersonas() ([]byte, error) {
	return json.MarshalIndent(Personas, "", "  ")
}
