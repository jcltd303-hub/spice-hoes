package main

import (
    "context"
    "flag"
    "encoding/base64"
    "encoding/json"
    "fmt"
    "io"
    "os"
    "path/filepath"
    "strconv"
    "strings"
    "time"

    ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
    "github.com/jcltd303-hub/spice-hoes/internal/identitygen"
    "github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
    "github.com/jcltd303-hub/spice-hoes/internal/nativecore"
    "github.com/jcltd303-hub/spice-hoes/internal/termui"
)

var progress *termui.Spinner

func fail(err error) {
    if progress != nil { progress.Stop(false) }
    fmt.Fprintln(os.Stderr, err)
    os.Exit(1)
}

func readObject() map[string]any {
    b, err := io.ReadAll(os.Stdin)
    if err != nil { fail(err) }
    if len(b) == 0 { return map[string]any{} }
    var v map[string]any
    if err := json.Unmarshal(b, &v); err != nil { fail(err) }
    return v
}

func write(v any) {
    enc := json.NewEncoder(os.Stdout)
    enc.SetEscapeHTML(false)
    if err := enc.Encode(v); err != nil { fail(err) }
}

func decodeB64(v any) ([]byte, error) {
    s, ok := v.(string)
    if !ok || s == "" { return nil, fmt.Errorf("missing base64 image") }
    if i := indexComma(s); i >= 0 { s = s[i+1:] }
    return base64.StdEncoding.DecodeString(s)
}

func indexComma(s string) int {
    for i := 0; i < len(s); i++ {
        if s[i] == ',' { return i }
    }
    return -1
}

func progressEvent(ev identitygen.ProgressEvent) {
    if progress == nil { return }
    progress.SetProgress(ev.Percent, ev.Stage)
    progress.SetMetrics(ev.Metrics)
}

func finish(title string, metrics map[string]any) {
    if progress == nil { return }
    progress.ReplaceMetrics(metrics)
    progress.SetProgress(100, "complete")
    progress.Stop(true)
    progress.Summary(title)
    progress = nil
}

func personaBankPathFor(persona string) string {
    if strings.TrimSpace(persona) == "" { return "" }
    candidates := []string{
        filepath.Join("personas", persona+".safetensors"),
        filepath.Join("personas", "personas.safetensors"),
    }
    for _, p := range candidates {
        if _, err := os.Stat(p); err == nil {
            return p
        }
    }
    return ""
}

func personaCartFromPayload(payload map[string]any) (string, []float32, float64, error) {
    personaID, _ := payload["persona"].(string)
    if personaID == "" { personaID, _ = payload["persona_id"].(string) }
    if personaID == "" { return "", nil, 0, nil }

    bankPath := ""
    if v, ok := payload["persona_bank"].(string); ok && strings.TrimSpace(v) != "" {
        bankPath = v
    } else {
        bankPath = personaBankPathFor(personaID)
    }
    if bankPath == "" {
        return personaID, nil, 0, fmt.Errorf("persona bank for %s not found", personaID)
    }

    bank, err := ident.LoadFile(bankPath)
    if err != nil {
        return personaID, nil, 0, err
    }
    vec, ok := bank.Tensors[personaID]
    if !ok {
        for _, name := range bank.Names {
            if name == personaID {
                vec = bank.Tensors[name]
                ok = true
                break
            }
        }
    }
    if !ok || len(vec) == 0 {
        return personaID, nil, 0, fmt.Errorf("persona %s not present in %s", personaID, bankPath)
    }

    weight := 0.82
    if v, ok := payload["identity_weight"].(float64); ok { weight = v }
    if v, ok := payload["identity_weight"].(float32); ok { weight = float64(v) }
    if s, ok := payload["identity_weight"].(string); ok {
        if w, err := strconvParseFloat(s); err == nil { weight = w }
    }

    return personaID, vec, weight, nil
}

func strconvParseFloat(s string) (float64, error) { return strconv.ParseFloat(s, 64) }

func attachPersonaIdentity(payload map[string]any) error {
    personaID, vec, weight, err := personaCartFromPayload(payload)
    if err != nil {
        return err
    }
    if personaID == "" { return nil }
    if len(vec) == 0 { return nil }

    payload["identity"] = map[string]any{
        "persona_id": personaID,
        "weight":     weight,
        "embedding":  vec,
        "model":      "arcface-r50",
    }
    return nil
}

func commandGenerate(args []string) {
    fs := flag.NewFlagSet("generate", flag.ContinueOnError)
    fs.SetOutput(io.Discard)
    persona := fs.String("persona", "", "persona ID to apply from persona bank")
    personaBank := fs.String("persona-bank", "", "path to a persona .safetensors bank")
    weight := fs.Float64("identity-weight", 0.82, "identity strength")
    if err := fs.Parse(args); err != nil { fail(err) }

    payload := readObject()
    if *persona != "" { payload["persona"] = *persona }
    if *personaBank != "" { payload["persona_bank"] = *personaBank }
    if *weight > 0 { payload["identity_weight"] = *weight }

    if err := attachPersonaIdentity(payload); err == nil {
        // identity attached when persona exists; failure is non-fatal if the bank is absent
    }

    manager := nativecore.FromEnv()
    if manager.ModelDir == "" { fail(fmt.Errorf("generation requires SPICE_QNN_MODEL_DIR")) }
    ctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
    defer cancel()
    progress.SetProgress(15, "QNN generation")
    out, err := manager.Generate(ctx, payload)
    if err != nil { fail(err) }
    progress.SetProgress(90, "packing response")
    img, _ := out["image"].(string)
    format, _ := out["format"].(string)
    if format == "" { format = "png" }
    mime := "image/png"
    if format == "jpeg" || format == "jpg" { mime = "image/jpeg" }
    response := map[string]any{"image_base64": img, "mime_type": mime, "model": "spicemedia:qnn", "backend": "go-managed-qnn"}
    for _, k := range []string{"seed", "width", "height", "channels", "generation_time_ms", "first_step_time_ms"} {
        if v, ok := out[k]; ok { response[k] = v }
    }
    finish("generation metrics", map[string]any{
        "backend": "go-managed-qnn",
        "model":   "spicemedia:qnn",
        "format":  format,
        "seed":    out["seed"],
        "size":    fmt.Sprintf("%vx%v", out["width"], out["height"]),
        "channels": out["channels"],
        "generation_time_ms": out["generation_time_ms"],
        "first_step_time_ms": out["first_step_time_ms"],
    })
    write(response)
}

func commandQuality() {
    payload := readObject()
    raw, err := decodeB64(payload["image_base64"])
    if err != nil { fail(err) }
    progress.SetProgress(25, "analyzing pixels")
    m, err := imagemetrics.Analyze(raw)
    if err != nil { fail(err) }
    result := map[string]any{
        "semantic_scored": false,
        "overall":         m.LocalScore,
        "local":           m,
        "model":           "go-stdlib-quality-v1",
    }
    finish("quality metrics", map[string]any{
        "quality_score": m.LocalScore,
        "size": fmt.Sprintf("%dx%d", m.Width, m.Height),
        "sharpness": m.Sharpness,
        "contrast": m.Contrast,
        "brightness": m.Brightness,
        "exposure": m.ExposureScore,
        "resolution": m.ResolutionScore,
        "backend": m.Backend,
    })
    write(result)
}

func arcFaceEmbedding(manager *nativecore.Manager, raw []byte) ([]float64, map[string]any, string, error) {
    const alignment = "scrfd-5pt-112"
    if manager.FaceDetector == "" {
        return nil, nil, alignment, fmt.Errorf("SPICE_FACE_DETECT_MODEL is not configured")
    }
    if manager.IdentityVision == "" {
        return nil, nil, alignment, fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")
    }

    prep, err := ident.SCRFDInput(raw)
    if err != nil { return nil, nil, alignment, fmt.Errorf("prepare SCRFD input: %w", err) }

    detectCtx, detectCancel := context.WithTimeout(context.Background(), 2*time.Minute)
    outputs, detectMeta, err := manager.Detect(detectCtx, prep.Tensor)
    detectCancel()
    if err != nil { return nil, nil, alignment, fmt.Errorf("SCRFD detection failed: %w", err) }

    faces, err := ident.DecodeSCRFD(outputs, prep, ident.SCRFDThreshold(0.5), 0.4)
    if err != nil || len(faces) == 0 {
        if err == nil { err = fmt.Errorf("no face detected") }
        return nil, nil, alignment, fmt.Errorf("SCRFD landmarks unavailable: %w", err)
    }

    input, err := ident.ArcFaceInputAligned(raw, faces[0].Landmarks)
    if err != nil { return nil, nil, alignment, fmt.Errorf("five-point alignment failed: %w", err) }

    embedCtx, embedCancel := context.WithTimeout(context.Background(), 2*time.Minute)
    vec, meta, err := manager.Embed(embedCtx, input)
    embedCancel()
    if err != nil { return nil, nil, alignment, fmt.Errorf("ArcFace embedding failed: %w", err) }

    meta["alignment"] = alignment
    meta["detector_latency_ms"] = detectMeta["latency_ms"]
    return ident.Normalize(vec), meta, alignment, nil
}

func commandEmbed() {
    payload := readObject()
    raw, err := decodeB64(payload["image_base64"])
    if err != nil { fail(err) }
    manager := nativecore.FromEnv()
    if manager.IdentityVision == "" { fail(fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")) }
    progress.SetProgress(30, "SCRFD + ArcFace embedding")
    vec, meta, alignment, err := arcFaceEmbedding(manager, raw)
    if err != nil { fail(err) }
    response := map[string]any{
        "embedding": vec,
        "dimensions": len(vec),
        "model": "arcface-w600k-r50-qnn",
        "alignment": alignment,
        "npu": true,
        "latency_ms": meta["latency_ms"],
        "detector_latency_ms": meta["detector_latency_ms"],
        "l2_norm": meta["l2_norm"],
    }
    finish("embedding metrics", map[string]any{
        "dimensions": len(vec),
        "alignment": alignment,
        "latency_ms": meta["latency_ms"],
        "detector_latency_ms": meta["detector_latency_ms"],
        "l2_norm": meta["l2_norm"],
    })
    write(response)
}

func commandPersonaEmbed() {
    payload := readObject()
    raw, err := decodeB64(payload["image_base64"])
    if err != nil { fail(err) }
    personaID, ok := payload["persona_id"].(string)
    if !ok || strings.TrimSpace(personaID) == "" {
        fail(fmt.Errorf("persona_id is required"))
    }
    manager := nativecore.FromEnv()
    if manager.IdentityVision == "" { fail(fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")) }
    vec, meta, alignment, err := arcFaceEmbedding(manager, raw)
    if err != nil { fail(err) }
    outPath := filepath.Join("personas", personaID+".safetensors")
    if v, ok := payload["output_path"].(string); ok && strings.TrimSpace(v) != "" { outPath = v }

    name := personaID
    if v, ok := payload["name"].(string); ok && strings.TrimSpace(v) != "" {
        name = strings.TrimSpace(v)
    }

    bank := ident.NewPersonaBank("arcface-r50")
    emb32 := make([]float32, len(vec))
    for i := range vec { emb32[i] = float32(vec[i]) }
    if err := bank.AddPersona(ident.PersonaEmbedding{
        ID:        personaID,
        Name:      name,
        Embedding: emb32,
        Metadata: map[string]any{
            "alignment": alignment,
            "generated_at": time.Now().UTC().Format(time.RFC3339),
            "npu": true,
            "latency_ms": meta["latency_ms"],
        },
    }); err != nil { fail(err) }
    if err := bank.WriteFile(outPath); err != nil { fail(err) }

    write(map[string]any{
        "persona_id": personaID,
        "output": outPath,
        "dimensions": len(vec),
        "alignment": alignment,
        "model": "arcface-r50",
        "npu": true,
        "latency_ms": meta["latency_ms"],
    })
}

func commandDetect() {
    payload := readObject()
    raw, err := decodeB64(payload["image_base64"])
    if err != nil { fail(err) }
    manager := nativecore.FromEnv()
    if manager.FaceDetector == "" { fail(fmt.Errorf("SPICE_FACE_DETECT_MODEL is not configured")) }

    prep, err := ident.SCRFDInput(raw)
    if err != nil { fail(err) }
    ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
    defer cancel()
    progress.SetProgress(35, "SCRFD detection")
    outputs, meta, err := manager.Detect(ctx, prep.Tensor)
    if err != nil { fail(err) }
    faces, err := ident.DecodeSCRFD(outputs, prep, ident.SCRFDThreshold(0.5), 0.4)
    if err != nil { fail(err) }

    result := make([]map[string]any, 0, len(faces))
    for _, face := range faces {
        points := make([][]float64, 0, 5)
        for _, p := range face.Landmarks {
            points = append(points, []float64{p.X, p.Y})
        }
        result = append(result, map[string]any{
            "score": face.Score,
            "box": []float64{face.X1, face.Y1, face.X2, face.Y2},
            "landmarks": points,
        })
    }
    response := map[string]any{
        "faces": result,
        "count": len(result),
        "model": "scrfd-10g-qnn",
        "npu": true,
        "latency_ms": meta["latency_ms"],
    }
    finish("face detection metrics", map[string]any{"faces": len(result), "latency_ms": meta["latency_ms"], "model": "scrfd-10g-qnn", "npu": true})
    write(response)
}

func commandIdentity() {
    payload := readObject()
    generated, err := decodeB64(payload["image_base64"])
    if err != nil { fail(err) }
    refs, ok := payload["references"].([]any)
    if !ok || len(refs) == 0 { fail(fmt.Errorf("identity requires references")) }

    manager := nativecore.FromEnv()
    if manager.IdentityVision != "" {
        generatedEmbedding, meta, alignment, err := arcFaceEmbedding(manager, generated)
        if err == nil {
            scores := make([]float64, 0, len(refs))
            for _, item := range refs {
                obj, ok := item.(map[string]any)
                if !ok { continue }
                ref, err := decodeB64(obj["image_base64"])
                if err != nil { continue }
                refEmbedding, _, _, err := arcFaceEmbedding(manager, ref)
                if err != nil { continue }
                score, err := ident.Cosine(generatedEmbedding, refEmbedding)
                if err == nil { scores = append(scores, score) }
            }
            if len(scores) > 0 {
                maxScore, sum := scores[0], 0.0
                for _, s := range scores {
                    if s > maxScore { maxScore = s }
                    sum += s
                }
                response := map[string]any{
                    "score": maxScore,
                    "mean_score": sum / float64(len(scores)),
                    "reference_count": len(scores),
                    "model": "arcface-w600k-r50-qnn",
                    "metric": "cosine",
                    "embedding_dimensions": len(generatedEmbedding),
                    "alignment": alignment,
                    "npu": true,
                    "latency_ms": meta["latency_ms"],
                    "detector_latency_ms": meta["detector_latency_ms"],
                    "l2_norm": meta["l2_norm"],
                }
                finish("identity metrics", map[string]any{"score": maxScore, "mean_score": sum / float64(len(scores)), "references": len(scores), "alignment": alignment, "latency_ms": meta["latency_ms"], "model": "arcface-w600k-r50-qnn"})
                write(response)
                return
            }
        }
    }

    scores := make([]float64, 0, len(refs))
    for _, item := range refs {
        obj, ok := item.(map[string]any)
        if !ok { continue }
        ref, err := decodeB64(obj["image_base64"])
        if err != nil { continue }
        score, err := ident.Similarity(generated, ref)
        if err == nil { scores = append(scores, score) }
    }
    if len(scores) == 0 { fail(fmt.Errorf("no decodable identity references")) }
    maxScore, sum := scores[0], 0.0
    for _, s := range scores {
        if s > maxScore { maxScore = s }
        sum += s
    }
    response := map[string]any{
        "score": maxScore,
        "mean_score": sum / float64(len(scores)),
        "reference_count": len(scores),
        "model": "go-perceptual-identity-v1",
        "metric": "normalized_similarity",
        "alignment": "none",
        "npu": false,
        "fallback_reason": "SPICE_FACE_EMBED_MODEL unavailable or NPU embedding failed",
    }
    finish("identity metrics", map[string]any{"score": maxScore, "mean_score": sum / float64(len(scores)), "references": len(scores), "model": "go-perceptual-identity-v1", "npu": false})
    write(response)
}

func commandPersonaBankBuild(args []string) {
    fs := flag.NewFlagSet("persona-bank-build", flag.ContinueOnError)
    fs.SetOutput(io.Discard)
    persona := fs.String("persona", "", "persona ID")
    referenceRoot := fs.String("reference-root", "data/references", "reference root")
    out := fs.String("out", "", "output .safetensors path")
    if err := fs.Parse(args); err != nil { fail(err) }
    if strings.TrimSpace(*persona) == "" { fail(fmt.Errorf("--persona is required")) }

    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
    defer cancel()
    result, err := identitygen.BuildPersonaBankFromReferences(ctx, *persona, *referenceRoot, *out)
    if err != nil { fail(err) }
    write(result)
}

func commandIdentityGenerate(args []string) {
    fs := flag.NewFlagSet("identity-generate", flag.ContinueOnError)
    fs.SetOutput(io.Discard)
    persona := fs.String("persona", "", "persona ID; automatically loads personas/<id>.yaml and personas/<id>.safetensors")
    theme := fs.String("theme", "", "generation theme")
    scene := fs.String("scene", "", "optional scene description")
    personaBank := fs.String("persona-bank", "", "path to persona .safetensors bank")
    requirePersonaBank := fs.Bool("require-persona-bank", false, "fail if persona bank cannot be loaded")
    if err := fs.Parse(args); err != nil { fail(err) }

    payload := readObject()
    if *persona != "" { payload["persona_id"] = *persona }
    if *theme != "" { payload["theme"] = *theme }
    if *scene != "" { payload["scene"] = *scene }
    if *personaBank != "" { payload["persona_bank"] = *personaBank }
    if *requirePersonaBank { payload["require_persona_bank"] = true }

    raw, err := json.Marshal(payload)
    if err != nil { fail(err) }
    var req identitygen.Request
    if err := json.Unmarshal(raw, &req); err != nil { fail(err) }
    req.Progress = progressEvent
    ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
    defer cancel()
    out, err := identitygen.Run(ctx, req)
    if err != nil { fail(err) }
    finish("identity generation metrics", map[string]any{
        "persona": out.PersonaID,
        "status": out.Status,
        "asset": out.AssetPath,
        "documents": out.DocumentsPath,
        "identity_score": out.Identity.Score,
        "identity_mean": out.Identity.MeanScore,
        "identity_pass": out.Identity.Passed,
        "identity_threshold": out.Identity.Threshold,
        "identity_mean_threshold": out.Identity.MeanThreshold,
        "references": out.Identity.ReferenceCount,
        "alignment": out.Identity.Alignment,
        "persona_bank_loaded": out.Generation["persona_bank_loaded"],
        "persona_bank_path": out.Generation["persona_bank_path"],
    })
    write(out)
}


func commandIdentityLoop(args []string) {
    fs := flag.NewFlagSet("identity-loop", flag.ContinueOnError)
    fs.SetOutput(io.Discard)
    persona := fs.String("persona", "", "persona ID")
    theme := fs.String("theme", "identity reference portrait", "generation theme")
    scene := fs.String("scene", "clean frontal portrait, face unobscured, realistic lighting", "scene description")
    maxAttempts := fs.Int("max-attempts", 12, "maximum generate/inspect attempts before giving up")
    margin := fs.Float64("margin-threshold", identitygen.DefaultIdentityMargin, "minimum own-vs-foreign prototype margin")
    quality := fs.Float64("quality-threshold", 0.78, "minimum local image quality score")
    own := fs.Float64("own-threshold", 0.70, "minimum own-prototype similarity")
    personaBank := fs.String("persona-bank", "", "path to persona .safetensors bank")
    saveRejected := fs.Bool("save-rejected", true, "keep rejected attempt assets/metadata")
    if err := fs.Parse(args); err != nil { fail(err) }
    if strings.TrimSpace(*persona) == "" { fail(fmt.Errorf("--persona is required")) }
    if *maxAttempts < 1 { *maxAttempts = 1 }
    if *maxAttempts > 64 { *maxAttempts = 64 }

    stop := true
    saveAll := *saveRejected
    req := identitygen.Request{
        PersonaID: *persona,
        Theme: *theme,
        Scene: *scene,
        BestOfN: *maxAttempts,
        IdentityMeanThreshold: *own,
        IdentityMarginThreshold: *margin,
        QualityThreshold: *quality,
        RequirePersonaBank: true,
        StopOnAccept: &stop,
        SaveAllAttempts: &saveAll,
        Progress: progressEvent,
    }
    if strings.TrimSpace(*personaBank) != "" { req.PersonaBank = *personaBank }

    ctx, cancel := context.WithTimeout(context.Background(), 4*time.Hour)
    defer cancel()
    out, err := identitygen.Run(ctx, req)
    if err != nil { fail(err) }

    accepted := out.Identity.Passed && out.QualityPassed
    reason := "accepted"
    if !accepted {
        reason = out.Identity.Reason
        if reason == "" {
            switch {
            case !out.Identity.Passed && !out.QualityPassed:
                reason = "identity_and_quality_failed"
            case !out.Identity.Passed:
                reason = "identity_failed"
            case !out.QualityPassed:
                reason = "quality_failed"
            }
        }
    }

    finish("identity loop complete", map[string]any{
        "persona": out.PersonaID,
        "accepted": accepted,
        "reason": reason,
        "attempts_requested": *maxAttempts,
        "attempts_completed": func() int { if out.Batch != nil { return out.Batch.Completed }; return 1 }(),
        "selected_attempt": func() int { if out.Batch != nil { return out.Batch.Selected }; return 1 }(),
        "prototype_score": out.Identity.PrototypeScore,
        "nearest_other": out.Identity.NearestOtherPersona,
        "nearest_other_score": out.Identity.NearestOtherScore,
        "identity_margin": out.Identity.IdentityMargin,
        "margin_threshold": out.Identity.MarginThreshold,
        "quality": out.Quality.LocalScore,
        "quality_threshold": out.QualityThreshold,
        "asset": out.AssetPath,
    })
    write(out)
}

func commandIdentityAutonomous() {
    payload := readObject()
    raw, err := json.Marshal(payload)
    if err != nil { fail(err) }

    var req identitygen.AutonomousRequest
    if err := json.Unmarshal(raw, &req); err != nil { fail(err) }
    req.Progress = progressEvent

    ctx, cancel := context.WithTimeout(context.Background(), 8*time.Hour)
    defer cancel()
    out, err := identitygen.AutonomousIdentity(ctx, req)
    if err != nil { fail(err) }

    finish("autonomous identity metrics", map[string]any{
        "persona": out.PersonaID,
        "ok": out.OK,
        "run_id": out.RunID,
        "run_root": out.RunRoot,
        "documents": out.DocumentsPath,
        "reference_complete": out.ReferenceComplete,
        "portfolio_complete": out.PortfolioComplete,
        "portfolio_sheet": out.PortfolioSheet,
        "manifest": out.ManifestPath,
        "persona_bank": out.PersonaBankPath,
        "persona_bank_snapshot": out.PersonaBankSnapshot,
        "persona_bank_dimensions": out.PersonaBankDimensions,
        "swap_available": out.SwapAvailable,
        "swap_mode": out.SwapMode,
    })
    write(out)
}

func commandHealth() {
    ctx, cancel := context.WithTimeout(context.Background(), 50*time.Second)
    defer cancel()
    m := nativecore.FromEnv()
    if err := m.Ensure(ctx); err != nil {
        result := map[string]any{"ok": false, "backend": "go-managed-qnn", "error": err.Error()}
        finish("health metrics", result)
        write(result)
        return
    }
    result := map[string]any{"ok": true, "backend": "go-managed-qnn", "mode": func() string { if m.ModelDir == "" { return "face-only" }; return "generation" }() }
    finish("health metrics", result)
    write(result)
}

func main() {
    if len(os.Args) < 2 {
        fail(fmt.Errorf("usage: spicemedia generate|quality|detect|embed|persona-embed|persona-bank-build|identity|identity-generate|identity-loop|identity-autonomous|health"))
    }
    command := os.Args[1]
    progress = termui.Start(termui.Label("spicemedia", command))
    defer func(){ if progress != nil { progress.Stop(true) } }()

    switch command {
    case "generate":
        commandGenerate(os.Args[2:])
    case "quality":
        commandQuality()
    case "detect":
        commandDetect()
    case "embed":
        commandEmbed()
    case "persona-embed":
        commandPersonaEmbed()
    case "persona-bank-build":
        commandPersonaBankBuild(os.Args[2:])
    case "identity":
        commandIdentity()
    case "identity-generate":
        commandIdentityGenerate(os.Args[2:])
    case "identity-loop":
        commandIdentityLoop(os.Args[2:])
    case "identity-autonomous":
        commandIdentityAutonomous()
    case "health":
        commandHealth()
    default:
        fail(fmt.Errorf("unknown command: %s", command))
    }
}
