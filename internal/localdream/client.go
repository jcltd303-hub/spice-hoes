package localdream

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type Client struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

type GenerateRequest struct {
	Prompt         string
	NegativePrompt string
	Seed           int64
	Width          int
	Height         int
}

type GenerateResult struct {
	Image      []byte
	MIME       string
	Generation map[string]any
}

func FromEnv() *Client {
	base := strings.TrimSpace(os.Getenv("LOCAL_DREAM_URL"))
	if base == "" {
		base = "http://127.0.0.1:8081"
	}
	return &Client{
		BaseURL: strings.TrimRight(base, "/"),
		Token:   strings.TrimSpace(os.Getenv("LOCAL_DREAM_TOKEN")),
		HTTP:    &http.Client{Timeout: 12 * time.Minute},
	}
}

func (c *Client) Generate(ctx context.Context, in GenerateRequest) (GenerateResult, error) {
	if strings.TrimSpace(in.Prompt) == "" {
		return GenerateResult{}, errors.New("local dream prompt is empty")
	}
	if in.Width <= 0 {
		in.Width = 768
	}
	if in.Height <= 0 {
		in.Height = 1024
	}
	payload := map[string]any{
		"prompt":          in.Prompt,
		"negative_prompt": in.NegativePrompt,
		"width":           in.Width,
		"height":          in.Height,
	}
	if in.Seed != 0 {
		payload["seed"] = in.Seed
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return GenerateResult{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/generate", bytes.NewReader(raw))
	if err != nil {
		return GenerateResult{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	client := c.HTTP
	if client == nil {
		client = &http.Client{Timeout: 12 * time.Minute}
	}
	resp, err := client.Do(req)
	if err != nil {
		return GenerateResult{}, fmt.Errorf("local dream request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		msg, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return GenerateResult{}, fmt.Errorf("local dream HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(msg)))
	}

	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 64*1024), 96*1024*1024)
	event := ""
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "event:") {
			event = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
			continue
		}
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if event == "error" {
			var obj map[string]any
			_ = json.Unmarshal([]byte(data), &obj)
			return GenerateResult{}, fmt.Errorf("local dream generation: %v", obj["message"])
		}
		if event != "complete" {
			continue
		}
		var obj map[string]any
		if err := json.Unmarshal([]byte(data), &obj); err != nil {
			return GenerateResult{}, fmt.Errorf("decode local dream completion: %w", err)
		}
		encoded, _ := obj["image"].(string)
		if encoded == "" {
			encoded, _ = obj["image_base64"].(string)
		}
		if encoded == "" {
			return GenerateResult{}, errors.New("local dream completion contained no image")
		}
		if i := strings.IndexByte(encoded, ','); strings.HasPrefix(encoded, "data:") && i >= 0 {
			encoded = encoded[i+1:]
		}
		img, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			return GenerateResult{}, fmt.Errorf("decode local dream image: %w", err)
		}
		format := strings.ToLower(fmt.Sprint(obj["format"]))
		mime := "image/png"
		if format == "jpeg" || format == "jpg" {
			mime = "image/jpeg"
		}
		obj["backend"] = "local-dream"
		return GenerateResult{Image: img, MIME: mime, Generation: obj}, nil
	}
	if err := scanner.Err(); err != nil {
		return GenerateResult{}, err
	}
	return GenerateResult{}, errors.New("local dream stream ended without complete event")
}
