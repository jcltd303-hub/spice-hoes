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
	apply := flag.Bool("apply", false, "quarantine outliers and rebuild persona banks")
	out := flag.String("out", "identity-repair.json", "write JSON report")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()

	res, err := identitygen.RepairIdentityPacks(ctx, *root, *apply)
	if err != nil {
		fmt.Fprintln(os.Stderr, "repair:", err)
		os.Exit(1)
	}

	raw, _ := json.MarshalIndent(res, "", "  ")
	if *out != "" {
		if err := os.WriteFile(*out, raw, 0o644); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}

	for _, p := range res.Packs {
		fmt.Printf("%s: keep %d/%d  margin max %.3f -> %.3f  mean %.3f -> %.3f  separable=%v\n",
			p.PersonaID, len(p.Kept), len(p.Original),
			p.BeforeMaxMargin, p.AfterMaxMargin,
			p.BeforeMeanMargin, p.AfterMeanMargin,
			p.Separable)
		if len(p.Quarantined) > 0 {
			fmt.Printf("  quarantine: %v\n", p.Quarantined)
		}
	}
	if *apply {
		fmt.Printf("applied; quarantine=%s\n", res.QuarantineDir)
	} else {
		fmt.Println("dry run only; rerun with -apply to move outliers and rebuild banks")
	}
	if *out != "" {
		fmt.Printf("report: %s\n", *out)
	}
}
