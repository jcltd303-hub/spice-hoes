package main

import (
    "encoding/json"
    "flag"
    "fmt"
    "io"
    "os"
    "strings"

    "github.com/jcltd303-hub/spice-hoes/internal/identity"
    "github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
    "github.com/jcltd303-hub/spice-hoes/internal/termui"
)

func usage() {
    fmt.Fprintf(os.Stderr, "usage: spiceimg metrics|bank [args]\n")
    fmt.Fprintf(os.Stderr, "  spiceimg metrics < image.bin\n")
    fmt.Fprintf(os.Stderr, "  spiceimg bank --out personas/zara_voss.safetensors < persona.json\n")
    os.Exit(2)
}

func readJSONFromStdin() (map[string]any, error) {
    data, err := io.ReadAll(os.Stdin)
    if err != nil {
        return nil, err
    }
    if len(data) == 0 {
        return map[string]any{}, nil
    }
    var v map[string]any
    if err := json.Unmarshal(data, &v); err != nil {
        return nil, err
    }
    return v, nil
}

func toFloat32Slice(v any) ([]float32, error) {
    switch arr := v.(type) {
    case []float32:
        return append([]float32(nil), arr...), nil
    case []float64:
        out := make([]float32, len(arr))
        for i, x := range arr {
            out[i] = float32(x)
        }
        return out, nil
    case []any:
        out := make([]float32, len(arr))
        for i, x := range arr {
            switch n := x.(type) {
            case float64:
                out[i] = float32(n)
            case float32:
                out[i] = n
            case int:
                out[i] = float32(n)
            case json.Number:
                f, err := n.Float64()
                if err != nil {
                    return nil, err
                }
                out[i] = float32(f)
            default:
                return nil, fmt.Errorf("unsupported embedding value type %T", x)
            }
        }
        return out, nil
    default:
        return nil, fmt.Errorf("embedding must be an array, got %T", v)
    }
}

func personaFromPayload(data map[string]any) (identity.PersonaEmbedding, error) {
    id, _ := data["persona_id"].(string)
    if id == "" {
        id, _ = data["persona"].(string)
    }
    if id == "" {
        id, _ = data["id"].(string)
    }
    if id == "" {
        return identity.PersonaEmbedding{}, fmt.Errorf("persona_id is required")
    }

    embedding, ok := data["embedding"]
    if !ok {
        embedding = data["vector"]
    }
    if !ok {
        return identity.PersonaEmbedding{}, fmt.Errorf("embedding is required")
    }

    vals, err := toFloat32Slice(embedding)
    if err != nil {
        return identity.PersonaEmbedding{}, err
    }
    if len(vals) == 0 {
        return identity.PersonaEmbedding{}, fmt.Errorf("embedding is empty")
    }

    name, _ := data["name"].(string)
    metadata := map[string]any{}
    for k, v := range data {
        if k == "embedding" || k == "vector" || k == "persona_id" || k == "persona" || k == "id" || k == "name" {
            continue
        }
        metadata[k] = v
    }

    return identity.PersonaEmbedding{ID: id, Name: name, Embedding: vals, Metadata: metadata}, nil
}

func runBank(args []string) error {
    fs := flag.NewFlagSet("bank", flag.ContinueOnError)
    fs.SetOutput(io.Discard)
    outPath := fs.String("out", "", "output .safetensors path")
    model := fs.String("model", "arcface-r50", "identity model label")
    if err := fs.Parse(args); err != nil {
        return err
    }

    payload, err := readJSONFromStdin()
    if err != nil {
        return err
    }

    bank := identity.NewPersonaBank(*model)

    if list, ok := payload["personas"].([]any); ok && len(list) > 0 {
        for _, item := range list {
            obj, ok := item.(map[string]any)
            if !ok {
                return fmt.Errorf("persona entries must be objects")
            }
            p, err := personaFromPayload(obj)
            if err != nil {
                return err
            }
            if err := bank.AddPersona(p); err != nil {
                return err
            }
        }
    } else {
        p, err := personaFromPayload(payload)
        if err != nil {
            return err
        }
        if err := bank.AddPersona(p); err != nil {
            return err
        }
    }

    if *outPath == "" {
        return fmt.Errorf("--out is required")
    }
    if err := bank.WriteFile(*outPath); err != nil {
        return err
    }

    result := map[string]any{
        "output": *outPath,
        "count": len(bank.Tensors),
        "model": *model,
        "version": bank.Version,
    }
    enc := json.NewEncoder(os.Stdout)
    enc.SetEscapeHTML(false)
    return enc.Encode(result)
}

func runMetrics() error {
    progress := termui.Start("spiceimg metrics")
    defer progress.Stop(true)

    data, err := io.ReadAll(os.Stdin)
    if err != nil {
        progress.Stop(false)
        return err
    }
    progress.SetProgress(10, "reading image")
    metrics, err := imagemetrics.Analyze(data)
    if err != nil {
        progress.Stop(false)
        return err
    }
    progress.SetMetrics(map[string]any{
        "size": fmt.Sprintf("%dx%d", metrics.Width, metrics.Height),
        "quality_score": metrics.LocalScore,
        "sharpness": metrics.Sharpness,
        "contrast": metrics.Contrast,
        "brightness": metrics.Brightness,
        "exposure": metrics.ExposureScore,
        "resolution": metrics.ResolutionScore,
        "backend": metrics.Backend,
    })
    progress.SetProgress(100, "complete")
    progress.Stop(true)
    progress.Summary("image metrics")

    enc := json.NewEncoder(os.Stdout)
    enc.SetEscapeHTML(false)
    return enc.Encode(metrics)
}

func main() {
    if len(os.Args) < 2 {
        usage()
    }

    switch strings.TrimSpace(os.Args[1]) {
    case "metrics":
        if err := runMetrics(); err != nil {
            fmt.Fprintln(os.Stderr, err)
            os.Exit(1)
        }
    case "bank":
        if err := runBank(os.Args[2:]); err != nil {
            fmt.Fprintln(os.Stderr, err)
            os.Exit(1)
        }
    default:
        usage()
    }
}
