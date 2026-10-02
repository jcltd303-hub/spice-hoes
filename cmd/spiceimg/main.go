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

	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	metrics, err := imagemetrics.Analyze(data)
	if err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(metrics); err != nil {
		progress.Stop(false)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
