package nativecore

import (
    "bufio"
    "bytes"
    "context"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net/http"
    "os"
    "os/exec"
    "path/filepath"
    "strconv"
    "strings"
    "time"
)

type Manager struct {
    Binary string
    ModelDir string
    LibDir string
    Type string
    Host string
    Port int
    LogPath string
    IdentityVision string
    FaceDetector string
    RequireModelMatch bool
}

func FromEnv() *Manager {
    port := 18081
    if raw := strings.TrimSpace(os.Getenv("SPICE_QNN_PORT")); raw != "" {
        if n, err := strconv.Atoi(raw); err == nil && n > 0 { port = n }
    }
    host := strings.TrimSpace(os.Getenv("SPICE_QNN_HOST")); if host == "" { host = "127.0.0.1" }
    bin := strings.TrimSpace(os.Getenv("SPICE_QNN_CORE_BIN")); if bin == "" { bin = "bin/spice-qnn-core" }
    modelDir := strings.TrimSpace(os.Getenv("SPICE_QNN_MODEL_DIR"))
    libDir := strings.TrimSpace(os.Getenv("SPICE_QNN_LIB_DIR"))
    modelType := strings.TrimSpace(os.Getenv("SPICE_QNN_TYPE")); if modelType == "" { modelType = "sd15npu" }
    logPath := strings.TrimSpace(os.Getenv("SPICE_QNN_LOG")); if logPath == "" { logPath = "data/spicemedia/qnn-core.log" }
    identityVision := strings.TrimSpace(os.Getenv("SPICE_FACE_EMBED_MODEL"))
    faceDetector := strings.TrimSpace(os.Getenv("SPICE_FACE_DETECT_MODEL"))
    return &Manager{Binary:bin, ModelDir:modelDir, LibDir:libDir, Type:modelType, Host:host, Port:port, LogPath:logPath, IdentityVision:identityVision, FaceDetector:faceDetector}
}

// FromEnvForPersona routes generation to a preconverted persona-specific SDXL
// MNN pack when SPICE_LORA_MODEL_ROOT/<persona> is complete. QNN graphs have
// immutable weights, so LoRA adapters are fused into per-persona MNN packs
// ahead of time rather than pretending they can be injected into a compiled
// QNN UNet at request time.
func FromEnvForPersona(persona string) *Manager {
    m := FromEnv()
    persona = strings.TrimSpace(persona)
    root := strings.TrimSpace(os.Getenv("SPICE_LORA_MODEL_ROOT"))
    if persona == "" || root == "" { return m }

    dir := filepath.Join(root, persona)
    required := []string{
        "tokenizer.json", "clip.mnn", "clip_2.mnn",
        "unet.mnn", "vae_decoder.mnn",
        "pos_emb.bin", "pos_emb_2.bin",
        "token_emb.bin", "token_emb_2.bin",
    }
    for _, name := range required {
        info, err := os.Stat(filepath.Join(dir, name))
        if err != nil || info.IsDir() || info.Size() == 0 { return m }
    }

    m.ModelDir = dir
    m.Type = "sdxlmnn"
    m.RequireModelMatch = true
    return m
}

func (m *Manager) baseURL() string { return fmt.Sprintf("http://%s:%d", m.Host, m.Port) }

func startupTimeout() time.Duration {
    // SDXL/QNN initialization on mobile can take well over 45 seconds,
    // especially on a cold start. Keep this configurable for slower devices.
    seconds := 180
    if raw := strings.TrimSpace(os.Getenv("SPICE_QNN_STARTUP_TIMEOUT_SECONDS")); raw != "" {
        if n, err := strconv.Atoi(raw); err == nil && n > 0 {
            seconds = n
        }
    }
    return time.Duration(seconds) * time.Second
}

func (m *Manager) Health(ctx context.Context) bool {
    ok, _ := m.healthMatches(ctx)
    return ok
}

func (m *Manager) healthMatches(ctx context.Context) (bool, error) {
    req, _ := http.NewRequestWithContext(ctx, http.MethodGet, m.baseURL()+"/health", nil)
    resp, err := http.DefaultClient.Do(req); if err != nil { return false, err }
    defer resp.Body.Close()
    if resp.StatusCode < 200 || resp.StatusCode >= 300 { return false, nil }
    if !m.RequireModelMatch { return true, nil }

    raw, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
    if err != nil { return false, err }
    var meta map[string]any
    if err := json.Unmarshal(raw, &meta); err != nil { return false, nil }
    active, _ := meta["model_dir"].(string)
    if strings.TrimSpace(active) == "" { return false, nil }
    want, err := filepath.Abs(m.ModelDir); if err != nil { return false, err }
    got, err := filepath.Abs(active); if err != nil { return false, err }
    return filepath.Clean(want) == filepath.Clean(got), nil
}

func stopExistingCore() {
    _ = exec.Command("pkill", "-f", "spice-qnn-core").Run()
    _ = exec.Command("pkill", "-f", "stable_diffusion_core").Run()
    time.Sleep(350 * time.Millisecond)
}

func (m *Manager) faceOnly() bool {
    return m.ModelDir == "" && (m.IdentityVision != "" || m.FaceDetector != "")
}

func (m *Manager) validate() error {
    if !m.faceOnly() && m.ModelDir == "" { return errors.New("SPICE_QNN_MODEL_DIR is required") }
    if m.LibDir == "" { return errors.New("SPICE_QNN_LIB_DIR is required") }
    binary, err := filepath.Abs(m.Binary); if err != nil { return err }; m.Binary = binary
    if m.ModelDir != "" {
        modelDir, err := filepath.Abs(m.ModelDir); if err != nil { return err }; m.ModelDir = modelDir
    }
    libDir, err := filepath.Abs(m.LibDir); if err != nil { return err }; m.LibDir = libDir
    if _, err := os.Stat(m.Binary); err != nil { return fmt.Errorf("QNN core binary unavailable: %w", err) }
    if m.ModelDir != "" {
        if info, err := os.Stat(m.ModelDir); err != nil || !info.IsDir() { return fmt.Errorf("QNN model directory unavailable: %s", m.ModelDir) }
    }
    if info, err := os.Stat(m.LibDir); err != nil || !info.IsDir() { return fmt.Errorf("QNN runtime directory unavailable: %s", m.LibDir) }
    return nil
}

func (m *Manager) Ensure(ctx context.Context) error {
    check, cancel := context.WithTimeout(ctx, 700*time.Millisecond)
    healthy, _ := m.healthMatches(check)
    cancel()
    if healthy { return nil }

    // A persona-specific pre-fused MNN pack may need a different model than
    // the currently-running core. Only persona-routed managers force a swap.
    if m.RequireModelMatch {
        probe, probeCancel := context.WithTimeout(ctx, 700*time.Millisecond)
        anyHealthy := FromEnv().Health(probe)
        probeCancel()
        if anyHealthy { stopExistingCore() }
    }

    if err := m.validate(); err != nil { return err }
    if err := os.MkdirAll(filepath.Dir(m.LogPath), 0755); err != nil { return err }
    logFile, err := os.OpenFile(m.LogPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644); if err != nil { return err }
    args := []string{}
    if m.faceOnly() {
        // Native core's upscaler mode initializes QNN without loading a
        // diffusion pipeline, which is exactly what face detect/embed need.
        args = []string{"--upscaler_mode","--lib_dir",m.LibDir,"--port",strconv.Itoa(m.Port)}
    } else {
        args = []string{"--type",m.Type,"--model_dir",m.ModelDir,"--lib_dir",m.LibDir,"--port",strconv.Itoa(m.Port)}
        if m.Type == "sdxl" || m.Type == "sdxlmnn" {
            args = append(args, "--no_img2img", "--lowram")
        }
    }
    if m.IdentityVision != "" {
        identityPath, err := filepath.Abs(m.IdentityVision); if err != nil { return err }
        if _, err := os.Stat(identityPath); err != nil { return fmt.Errorf("face embedding model unavailable: %w", err) }
        m.IdentityVision = identityPath
        args = append(args, "--identity_vision", m.IdentityVision)
    }
    if m.FaceDetector != "" {
        detectorPath, err := filepath.Abs(m.FaceDetector); if err != nil { return err }
        if _, err := os.Stat(detectorPath); err != nil { return fmt.Errorf("face detector model unavailable: %w", err) }
        m.FaceDetector = detectorPath
        args = append(args, "--face_detector", m.FaceDetector)
    }
    cmd := exec.Command(m.Binary, args...)
    cmd.Stdout = logFile; cmd.Stderr = logFile; cmd.Dir = filepath.Dir(m.Binary)
    ld := strings.Join([]string{m.LibDir,"/system/lib64","/vendor/lib64","/vendor/lib64/egl"},":")
    dsp := strings.Join([]string{m.LibDir,"/vendor/lib/rfsa/adsp","/vendor/dsp/cdsp","/dsp"},";")
    cmd.Env = append(os.Environ(),"LD_LIBRARY_PATH="+ld,"DSP_LIBRARY_PATH="+dsp,"ADSP_LIBRARY_PATH="+dsp)
    if err := cmd.Start(); err != nil { logFile.Close(); return fmt.Errorf("start QNN core: %w", err) }
    _ = cmd.Process.Release(); _ = logFile.Close()
    deadline := time.Now().Add(startupTimeout())
    for time.Now().Before(deadline) {
        select { case <-ctx.Done(): return ctx.Err(); default: }
        probe, cancel := context.WithTimeout(ctx, 800*time.Millisecond); ok := m.Health(probe); cancel()
        if ok { return nil }; time.Sleep(350*time.Millisecond)
    }
    return fmt.Errorf("QNN core did not become healthy; see %s", m.LogPath)
}

func (m *Manager) Generate(ctx context.Context, payload map[string]any) (map[string]any, error) {
    if err := m.Ensure(ctx); err != nil { return nil, err }
    if _, ok := payload["output_format"]; !ok { payload["output_format"] = "png" }
    body, err := json.Marshal(payload); if err != nil { return nil, err }
    req, err := http.NewRequestWithContext(ctx,http.MethodPost,m.baseURL()+"/generate",bytes.NewReader(body)); if err != nil { return nil, err }
    req.Header.Set("Content-Type","application/json")
    client := &http.Client{Timeout:10*time.Minute}
    resp, err := client.Do(req); if err != nil { return nil, err }; defer resp.Body.Close()
    if resp.StatusCode < 200 || resp.StatusCode >= 300 { b,_ := io.ReadAll(io.LimitReader(resp.Body,1<<20)); return nil, fmt.Errorf("QNN core HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(b))) }
    scanner := bufio.NewScanner(resp.Body); scanner.Buffer(make([]byte,64*1024),64*1024*1024)
    eventName := ""
    for scanner.Scan() {
        line := scanner.Text()
        if strings.HasPrefix(line,"event:") { eventName = strings.TrimSpace(strings.TrimPrefix(line,"event:")); continue }
        if !strings.HasPrefix(line,"data:") { continue }
        raw := strings.TrimSpace(strings.TrimPrefix(line,"data:"))
        if eventName == "error" { var e map[string]any; _ = json.Unmarshal([]byte(raw),&e); return nil, fmt.Errorf("QNN core generation error: %v",e["message"]) }
        if eventName == "complete" { var out map[string]any; if err := json.Unmarshal([]byte(raw),&out); err != nil { return nil, err }; if out["image"] == nil { return nil, errors.New("QNN core complete event contained no image") }; return out,nil }
    }
    if err := scanner.Err(); err != nil { return nil, err }
    return nil, errors.New("QNN core stream ended without complete event")
}

func (m *Manager) Embed(ctx context.Context, input []float64) ([]float64, map[string]any, error) {
    if len(input) == 0 { return nil, nil, errors.New("embedding input is empty") }
    if err := m.Ensure(ctx); err != nil { return nil, nil, err }
    payload := map[string]any{"input": input}
    body, err := json.Marshal(payload); if err != nil { return nil, nil, err }
    req, err := http.NewRequestWithContext(ctx,http.MethodPost,m.baseURL()+"/identity/embed",bytes.NewReader(body)); if err != nil { return nil,nil,err }
    req.Header.Set("Content-Type","application/json")
    resp, err := (&http.Client{Timeout:2*time.Minute}).Do(req); if err != nil { return nil,nil,err }
    defer resp.Body.Close()
    raw, err := io.ReadAll(io.LimitReader(resp.Body,32<<20)); if err != nil { return nil,nil,err }
    if resp.StatusCode < 200 || resp.StatusCode >= 300 { return nil,nil,fmt.Errorf("identity embed HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(raw))) }
    var out map[string]any
    if err := json.Unmarshal(raw,&out); err != nil { return nil,nil,err }
    values, ok := out["embedding"].([]any); if !ok || len(values)==0 { return nil,nil,errors.New("identity embed returned no vector") }
    vec := make([]float64,0,len(values))
    for _,v := range values {
        n,ok := v.(float64); if !ok { return nil,nil,errors.New("identity embed returned non-numeric vector") }
        vec = append(vec,n)
    }
    return vec,out,nil
}


type TensorOutput struct {
    Name string
    Dims []int
    Values []float64
}

func (m *Manager) Detect(ctx context.Context, input []float64) ([]TensorOutput, map[string]any, error) {
    if len(input)==0 { return nil,nil,errors.New("detector input is empty") }
    if err:=m.Ensure(ctx); err!=nil { return nil,nil,err }
    body,err:=json.Marshal(map[string]any{"input":input}); if err!=nil { return nil,nil,err }
    req,err:=http.NewRequestWithContext(ctx,http.MethodPost,m.baseURL()+"/face/detect",bytes.NewReader(body)); if err!=nil { return nil,nil,err }
    req.Header.Set("Content-Type","application/json")
    resp,err:=(&http.Client{Timeout:2*time.Minute}).Do(req); if err!=nil { return nil,nil,err }
    defer resp.Body.Close()
    raw,err:=io.ReadAll(io.LimitReader(resp.Body,128<<20)); if err!=nil { return nil,nil,err }
    if resp.StatusCode<200 || resp.StatusCode>=300 { return nil,nil,fmt.Errorf("face detect HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(raw))) }
    var payload map[string]any
    if err:=json.Unmarshal(raw,&payload); err!=nil { return nil,nil,err }
    rawOutputs,ok:=payload["outputs"].([]any); if !ok || len(rawOutputs)==0 { return nil,nil,errors.New("face detector returned no outputs") }
    outputs:=make([]TensorOutput,0,len(rawOutputs))
    for _,item:=range rawOutputs {
        obj,ok:=item.(map[string]any); if !ok { continue }
        out:=TensorOutput{}
        if name,ok:=obj["name"].(string); ok { out.Name=name }
        if ds,ok:=obj["dims"].([]any); ok {
            for _,d:=range ds { if n,ok:=d.(float64); ok { out.Dims=append(out.Dims,int(n)) } }
        }
        if vs,ok:=obj["values"].([]any); ok {
            out.Values=make([]float64,0,len(vs))
            for _,v:=range vs { if n,ok:=v.(float64); ok { out.Values=append(out.Values,n) } }
        }
        if len(out.Values)>0 { outputs=append(outputs,out) }
    }
    if len(outputs)==0 { return nil,nil,errors.New("face detector returned empty tensor set") }
    return outputs,payload,nil
}
