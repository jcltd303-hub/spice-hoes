package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"github.com/jcltd303-hub/spice-hoes/internal/termui"
)

func main() {
	if len(os.Args) != 2 || os.Args[1] != "metrics" {
		fmt.Fprintln(os.Stderr, "usage: spiceimg metrics < image")
		os.Exit(2)
	}
	progress := termui.Start("spiceimg metrics")
	defer progress.Stop(true)

	progress.SetProgress(10,"reading image")
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	progress.SetProgress(30,"computing image metrics")
	metrics, err := imagemetrics.Analyze(data)
	if err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	progress.SetMetrics(map[string]any{
		"size":fmt.Sprintf("%dx%d",metrics.Width,metrics.Height),
		"quality_score":metrics.LocalScore,
		"sharpness":metrics.Sharpness,
		"contrast":metrics.Contrast,
		"brightness":metrics.Brightness,
		"exposure":metrics.ExposureScore,
		"resolution":metrics.ResolutionScore,
		"backend":metrics.Backend,
	})
	progress.SetProgress(100,"complete")
	progress.Stop(true)
	progress.Summary("image metrics")
	if err := json.NewEncoder(os.Stdout).Encode(metrics); err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
