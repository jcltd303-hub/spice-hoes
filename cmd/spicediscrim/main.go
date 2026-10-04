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
	bankDir := flag.String("bank-dir", "personas", "output bank directory")
	weight := flag.Float64("anchor-weight", identitygen.DefaultAnchorWeight, "total weight assigned to anchor-* references")
	out := flag.String("out", "discriminative-banks.json", "write build report JSON")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()

	result, err := identitygen.BuildDiscriminativeBanks(ctx, *root, *bankDir, *weight)
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
		fmt.Printf("%s: anchors=%d support_kept=%d support_rejected=%d -> %s\n",
			p.PersonaID, len(p.AnchorLabels), len(p.SupportKept), len(p.SupportRejected), p.PrototypePath)
		for _, label := range p.SupportRejected {
			fmt.Printf("  rejected support: %s\n", label)
		}
	}
	fmt.Printf("report: %s\n", *out)
}
