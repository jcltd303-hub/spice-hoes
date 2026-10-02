package localdream

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"image"
	_ "image/jpeg"
	_ "image/png"
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
	Frame      image.Image
	Encoded    []byte
	MIME       string
	Generation map[string]any
}

func intField(obj map[string]any, key string) int {
	switch v:=obj[key].(type) {
	case float64:
		return int(v)
	case int:
		return v
	case json.Number:
		n,_:=v.Int64(); return int(n)
	default:
		return 0
	}
}

func rawRGBImage(raw []byte, width, height, channels int) (image.Image, error) {
	if width<=0 || height<=0 {
		return nil, fmt.Errorf("raw image missing dimensions")
	}
	if channels==0 { channels=3 }
	if channels!=3 && channels!=4 {
		return nil, fmt.Errorf("unsupported raw image channel count %d",channels)
	}
	want:=width*height*channels
	if len(raw)!=want {
		return nil, fmt.Errorf("raw image size mismatch: got %d bytes, expected %d for %dx%dx%d",len(raw),want,width,height,channels)
	}
	img:=image.NewNRGBA(image.Rect(0,0,width,height))
	if channels==4 {
		copy(img.Pix,raw)
		return img,nil
	}
	for src,dst:=0,0;src<len(raw);src,dst=src+3,dst+4 {
		img.Pix[dst]=raw[src]
		img.Pix[dst+1]=raw[src+1]
		img.Pix[dst+2]=raw[src+2]
		img.Pix[dst+3]=255
	}
	return img,nil
}

func decodeImagePayload(raw []byte, obj map[string]any) (image.Image,[]byte,string,error) {
	if len(raw)>=8 && bytes.Equal(raw[:8],[]byte{0x89,'P','N','G',0x0d,0x0a,0x1a,0x0a}) {
		img,_,err:=image.Decode(bytes.NewReader(raw))
		return img,raw,"image/png",err
	}
	if len(raw)>=3 && raw[0]==0xff && raw[1]==0xd8 && raw[2]==0xff {
		img,_,err:=image.Decode(bytes.NewReader(raw))
		return img,raw,"image/jpeg",err
	}
	width:=intField(obj,"width")
	height:=intField(obj,"height")
	channels:=intField(obj,"channels")
	if channels==0 { channels=3 }
	if width>0 && height>0 && len(raw)==width*height*channels {
		img,err:=rawRGBImage(raw,width,height,channels)
		if err!=nil{return nil,nil,"",err}
		obj["source_format"]="raw-rgb"
		obj["format"]="raw"
		return img,nil,"application/x-raw-rgb",nil
	}
	return nil,nil,"",fmt.Errorf("unsupported local dream image payload: %d bytes (width=%d height=%d channels=%d)",len(raw),width,height,channels)
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
		frame, encoded, mime, err := decodeImagePayload(img, obj)
		if err != nil {
			return GenerateResult{}, err
		}
		obj["backend"] = "local-dream"
		return GenerateResult{Frame: frame, Encoded: encoded, MIME: mime, Generation: obj}, nil
	}
	if err := scanner.Err(); err != nil {
		return GenerateResult{}, err
	}
	return GenerateResult{}, errors.New("local dream stream ended without complete event")
}
