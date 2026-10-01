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
    return &Manager{Binary:bin, ModelDir:modelDir, LibDir:libDir, Type:modelType, Host:host, Port:port, LogPath:logPath}
}

func (m *Manager) baseURL() string { return fmt.Sprintf("http://%s:%d", m.Host, m.Port) }

func (m *Manager) Health(ctx context.Context) bool {
    req, _ := http.NewRequestWithContext(ctx, http.MethodGet, m.baseURL()+"/health", nil)
    resp, err := http.DefaultClient.Do(req); if err != nil { return false }
    defer resp.Body.Close()
    return resp.StatusCode >= 200 && resp.StatusCode < 300
}

func (m *Manager) validate() error {
    if m.ModelDir == "" { return errors.New("SPICE_QNN_MODEL_DIR is required") }
    if m.LibDir == "" { return errors.New("SPICE_QNN_LIB_DIR is required") }
    if _, err := os.Stat(m.Binary); err != nil { return fmt.Errorf("QNN core binary unavailable: %w", err) }
    if info, err := os.Stat(m.ModelDir); err != nil || !info.IsDir() { return fmt.Errorf("QNN model directory unavailable: %s", m.ModelDir) }
    if info, err := os.Stat(m.LibDir); err != nil || !info.IsDir() { return fmt.Errorf("QNN runtime directory unavailable: %s", m.LibDir) }
    return nil
}

func (m *Manager) Ensure(ctx context.Context) error {
    check, cancel := context.WithTimeout(ctx, 700*time.Millisecond)
    if m.Health(check) { cancel(); return nil }; cancel()
    if err := m.validate(); err != nil { return err }
    if err := os.MkdirAll(filepath.Dir(m.LogPath), 0755); err != nil { return err }
    logFile, err := os.OpenFile(m.LogPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644); if err != nil { return err }
    args := []string{"--type",m.Type,"--model_dir",m.ModelDir,"--lib_dir",m.LibDir,"--port",strconv.Itoa(m.Port)}
    cmd := exec.Command(m.Binary, args...)
    cmd.Stdout = logFile; cmd.Stderr = logFile; cmd.Dir = filepath.Dir(m.Binary)
    ld := strings.Join([]string{m.LibDir,"/system/lib64","/vendor/lib64","/vendor/lib64/egl"},":")
    dsp := strings.Join([]string{m.LibDir,"/vendor/lib/rfsa/adsp","/vendor/dsp/cdsp","/dsp"},";")
    cmd.Env = append(os.Environ(),"LD_LIBRARY_PATH="+ld,"DSP_LIBRARY_PATH="+dsp,"ADSP_LIBRARY_PATH="+dsp)
    if err := cmd.Start(); err != nil { logFile.Close(); return fmt.Errorf("start QNN core: %w", err) }
    _ = cmd.Process.Release(); _ = logFile.Close()
    deadline := time.Now().Add(45*time.Second)
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