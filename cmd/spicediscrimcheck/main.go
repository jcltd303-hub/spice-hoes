package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/identitygen"
)

func main() {
	root := flag.String("root", "data/references", "reference root")
	bankDir := flag.String("bank-dir", "personas", "persona bank directory")
	margin := flag.Float64("margin", identitygen.DefaultIdentityMargin, "minimum discriminative margin")
	out := flag.String("out", "discriminative-calibration.json", "output report")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()

	result, err := identitygen.CalibrateDiscriminativeBanks(ctx, *root, *bankDir, *margin)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	raw, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(*out, raw, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	for _, p := range result.Personas {
		fmt.Printf("%s: refs=%d worst_own=%.3f worst_margin=%.3f separable=%t own_gate=%.3f margin_gate=%.3f\n",
			p.PersonaID, p.ReferencesUsed, p.WorstOwnScore, p.WorstMargin, p.Separable,
			p.RecommendedOwnGate, p.RecommendedMargin)
		for _, s := range p.Scores {
			fmt.Printf("  %s anchor=%t own=%.3f other=%s:%.3f margin=%.3f pass=%t\n",
				s.Label, s.Anchor, s.OwnScore, s.NearestOtherPersona, s.NearestOtherScore, s.Margin, s.Passed)
		}
	}
	fmt.Printf("report: %s\n", *out)
}
