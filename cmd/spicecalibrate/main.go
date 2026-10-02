// spicecalibrate measures real ArcFace score distributions from the reference
// packs on disk and recommends identity gate thresholds. It uses the same
// environment as spicemedia (SPICE_QNN_* / face model variables) and does not
// generate any images.
//
//	go run ./cmd/spicecalibrate -root data/references -out calibration.json
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/identitygen"
)

func main() {
	root := flag.String("root", "data/references", "reference root containing one directory per persona")
	personas := flag.String("personas", "", "comma-separated persona IDs (default: every directory under root)")
	margin := flag.Float64("margin", 0.02, "safety margin added above the best impostor score")
	out := flag.String("out", "", "write full JSON report to this file (default: stdout)")
	flag.Parse()

	req := identitygen.CalibrateRequest{ReferenceRoot: *root, Margin: *margin}
	for _, id := range strings.Split(*personas, ",") {
		if id = strings.TrimSpace(id); id != "" {
			req.PersonaIDs = append(req.PersonaIDs, id)
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	res, err := identitygen.Calibrate(ctx, req)
	if err != nil {
		fmt.Fprintln(os.Stderr, "calibrate:", err)
		os.Exit(1)
	}

	raw, err := json.MarshalIndent(res, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "encode report:", err)
		os.Exit(1)
	}
	if *out != "" {
		if err := os.WriteFile(*out, raw, 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "write report:", err)
			os.Exit(1)
		}
		fmt.Print(res.Summary())
		fmt.Fprintf(os.Stderr, "full report: %s\n", *out)
		return
	}
	fmt.Fprint(os.Stderr, res.Summary())
	fmt.Println(string(raw))
}
