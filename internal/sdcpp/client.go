package sdcpp

import (
    "context"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "strconv"
    "strings"
    "time"
)

type Request struct {
    Persona       string
    Prompt        string
    Negative      string
    Seed          int64
    Width         int
    Height        int
    Steps         int
    Guidance      float64
    LoRAWeight    float64
}

type Result struct {
    Image []byte
    Meta  map[string]any
}

func binPath() string {
    if v := strings.TrimSpace(os.Getenv("SPICE_SDCPP_BIN")); v != "" { return v }
    return filepath.Join("runtime", "bin", "sd-cli")
}

func modelPath() string { return strings.TrimSpace(os.Getenv("SPICE_SDCPP_MODEL")) }

func loraDir() string {
    if v := strings.TrimSpace(os.Getenv("SPICE_LORA_DIR")); v != "" { return v }
    return filepath.Join("artifacts", "loras")
}

func Available(persona string) bool {
    bin := binPath()
    model := modelPath()
    if persona == "" || model == "" { return false }
    if info, err := os.Stat(bin); err != nil || info.IsDir() { return false }
    if info, err := os.Stat(model); err != nil || info.IsDir() { return false }
    lora := filepath.Join(loraDir(), persona+".safetensors")
    if info, err := os.Stat(lora); err != nil || info.IsDir() || info.Size() == 0 { return false }
    return true
}

func Generate(ctx context.Context, req Request) (Result, error) {
    if !Available(req.Persona) {
        return Result{}, fmt.Errorf("stable-diffusion.cpp persona backend unavailable for %s", req.Persona)
    }

    if req.Width <= 0 { req.Width = 768 }
    if req.Height <= 0 { req.Height = 768 }
    if req.Steps <= 0 { req.Steps = 20 }
    if req.Guidance <= 0 { req.Guidance = 5.5 }
    if req.LoRAWeight <= 0 { req.LoRAWeight = 0.8 }

    tmp, err := os.CreateTemp("", "spice-sdcpp-*.png")
    if err != nil { return Result{}, err }
    outPath := tmp.Name()
    _ = tmp.Close()
    _ = os.Remove(outPath)
    defer os.Remove(outPath)

    prompt := strings.TrimSpace(req.Prompt)
    prompt = fmt.Sprintf("<lora:%s:%.3f> %s", req.Persona, req.LoRAWeight, prompt)

    args := []string{
        "-m", modelPath(),
        "-p", prompt,
        "-n", req.Negative,
        "--lora-model-dir", loraDir(),
        "--lora-apply-mode", "at_runtime",
        "--steps", strconv.Itoa(req.Steps),
        "--cfg-scale", strconv.FormatFloat(req.Guidance, 'f', -1, 64),
        "-W", strconv.Itoa(req.Width),
        "-H", strconv.Itoa(req.Height),
        "--seed", strconv.FormatInt(req.Seed, 10),
        "-o", outPath,
    }

    if backend := strings.TrimSpace(os.Getenv("SPICE_SDCPP_BACKEND")); backend != "" {
        args = append(args, "--backend", backend)
    }
    if paramsBackend := strings.TrimSpace(os.Getenv("SPICE_SDCPP_PARAMS_BACKEND")); paramsBackend != "" {
        args = append(args, "--params-backend", paramsBackend)
    }
    if threads := strings.TrimSpace(os.Getenv("SPICE_SDCPP_THREADS")); threads != "" {
        args = append(args, "-t", threads)
    }
    if strings.EqualFold(strings.TrimSpace(os.Getenv("SPICE_SDCPP_FLASH_ATTN")), "1") ||
       strings.EqualFold(strings.TrimSpace(os.Getenv("SPICE_SDCPP_FLASH_ATTN")), "true") {
        args = append(args, "--fa")
    }

    started := time.Now()
    cmd := exec.CommandContext(ctx, binPath(), args...)
    output, err := cmd.CombinedOutput()
    if err != nil {
        return Result{}, fmt.Errorf("stable-diffusion.cpp failed: %w: %s", err, strings.TrimSpace(string(output)))
    }

    image, err := os.ReadFile(outPath)
    if err != nil { return Result{}, fmt.Errorf("read stable-diffusion.cpp output: %w", err) }

    return Result{
        Image: image,
        Meta: map[string]any{
            "generator": "stable-diffusion.cpp",
            "backend": "sdcpp",
            "persona": req.Persona,
            "lora_weight": req.LoRAWeight,
            "model": modelPath(),
            "lora": filepath.Join(loraDir(), req.Persona+".safetensors"),
            "generation_time_ms": time.Since(started).Milliseconds(),
        },
    }, nil
}
