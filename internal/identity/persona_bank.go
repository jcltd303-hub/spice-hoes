package identity

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// PersonaEmbedding is a normalized face identity embedding plus metadata.
type PersonaEmbedding struct {
	ID        string
	Name      string
	Embedding []float32
	Metadata  map[string]any
}

// PersonaBank stores a set of persona identity vectors and can serialize to a
// safetensors file for downstream local Dream / image generation use.
type PersonaBank struct {
	Version string
	Model   string
	Names   []string
	Tensors map[string][]float32
}

type personaTensorHeader struct {
	DType       string   `json:"dtype"`
	Shape       []int    `json:"shape"`
	DataOffsets []uint64 `json:"data_offsets"`
}

type personaSafeTensorsHeader struct {
	Metadata map[string]any                  `json:"__metadata__"`
	Tensors  map[string]personaTensorHeader `json:"__tensors__"`
}

func NewPersonaBank(model string) *PersonaBank {
	if strings.TrimSpace(model) == "" {
		model = "arcface-r50"
	}
	return &PersonaBank{
		Version: "1",
		Model:   model,
		Tensors: map[string][]float32{},
	}
}

func normalizeTensorName(id string) string {
	return strings.TrimSpace(id)
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}

func (b *PersonaBank) AddPersona(p PersonaEmbedding) error {
	if strings.TrimSpace(p.ID) == "" {
		return fmt.Errorf("persona id is required")
	}
	if len(p.Embedding) == 0 {
		return fmt.Errorf("persona %s embedding is empty", p.ID)
	}

	id := normalizeTensorName(p.ID)
	if p.Metadata == nil {
		p.Metadata = map[string]any{}
	}
	if strings.TrimSpace(p.Name) != "" {
		p.Metadata["name"] = p.Name
	}

	b.Tensors[id] = append([]float32(nil), p.Embedding...)
	if !contains(b.Names, id) {
		b.Names = append(b.Names, id)
	}
	sort.Strings(b.Names)
	return nil
}

func (b *PersonaBank) WriteFile(path string) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("persona bank output path is empty")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create parent dir: %w", err)
	}

	names := make([]string, 0, len(b.Tensors))
	for name := range b.Tensors {
		names = append(names, name)
	}
	sort.Strings(names)

	entries := make(map[string][]float32, len(names))
	totalBytes := 0
	for _, name := range names {
		arr := append([]float32(nil), b.Tensors[name]...)
		entries[name] = arr
		totalBytes += len(arr) * 4
	}

	metadata := map[string]any{
		"model":   b.Model,
		"version": b.Version,
		"count":   len(names),
	}
	if len(b.Names) > 0 {
		metadata["names"] = append([]string(nil), b.Names...)
	}

	tensorMap := map[string]personaTensorHeader{}
	offset := uint64(0)
	for _, name := range names {
		shape := []int{len(entries[name])}
		tensorMap[name] = personaTensorHeader{
			DType:       "F32",
			Shape:       shape,
			DataOffsets: []uint64{offset, offset + uint64(len(entries[name])*4)},
		}
		offset += uint64(len(entries[name]) * 4)
	}
	if offset != uint64(totalBytes) {
		return fmt.Errorf("tensor byte accounting mismatch: wrote %d bytes, expected %d", offset, totalBytes)
	}

	headerJSON, err := json.Marshal(personaSafeTensorsHeader{
		Metadata: metadata,
		Tensors:  tensorMap,
	})
	if err != nil {
		return fmt.Errorf("marshal safetensors header: %w", err)
	}

	paddedHeaderLen := uint64(len(headerJSON))
	if paddedHeaderLen%8 != 0 {
		paddedHeaderLen = ((paddedHeaderLen / 8) + 1) * 8
	}

	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create safetensors file: %w", err)
	}
	defer file.Close()

	if err := binary.Write(file, binary.LittleEndian, paddedHeaderLen); err != nil {
		return fmt.Errorf("write safetensors header length: %w", err)
	}
	if _, err := file.Write(headerJSON); err != nil {
		return fmt.Errorf("write safetensors header: %w", err)
	}
	for i := len(headerJSON); i < int(paddedHeaderLen); i++ {
		if _, err := file.Write([]byte{0}); err != nil {
			return fmt.Errorf("pad safetensors header: %w", err)
		}
	}

	for _, name := range names {
		for _, value := range entries[name] {
			if err := binary.Write(file, binary.LittleEndian, value); err != nil {
				return fmt.Errorf("write tensor %s: %w", name, err)
			}
		}
	}

	return nil
}

// LoadFile reads a safetensors file produced by WriteFile and reconstructs the bank.
func LoadFile(path string) (*PersonaBank, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open safetensors file: %w", err)
	}
	defer file.Close()

	var headerLen uint64
	if err := binary.Read(file, binary.LittleEndian, &headerLen); err != nil {
		return nil, fmt.Errorf("read safetensors header length: %w", err)
	}
	if headerLen == 0 {
		return nil, fmt.Errorf("empty safetensors header")
	}

	headerBytes := make([]byte, int(headerLen))
	if _, err := file.Read(headerBytes); err != nil {
		return nil, fmt.Errorf("read header payload: %w", err)
	}

	var header personaSafeTensorsHeader
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return nil, fmt.Errorf("decode safetensors header: %w", err)
	}

	bank := &PersonaBank{
		Version: "1",
		Tensors: map[string][]float32{},
	}
	if metadata, ok := header.Metadata["model"].(string); ok {
		bank.Model = metadata
	}
	if version, ok := header.Metadata["version"].(string); ok {
		bank.Version = version
	}
	if namesRaw, ok := header.Metadata["names"].([]any); ok {
		for _, raw := range namesRaw {
			if s, ok := raw.(string); ok {
				bank.Names = append(bank.Names, s)
			}
		}
	}

	dataStart := int64(8 + headerLen)
	if dataStart%8 != 0 {
		dataStart = ((dataStart / 8) + 1) * 8
	}
	if _, err := file.Seek(dataStart, 0); err != nil {
		return nil, fmt.Errorf("seek safetensors payload: %w", err)
	}

	for name, t := range header.Tensors {
		if len(t.DataOffsets) != 2 {
			return nil, fmt.Errorf("tensor %s has invalid data_offsets", name)
		}
		count := len(t.Shape)
		if count == 0 {
			continue
		}
		if t.Shape[0] <= 0 {
			continue
		}
		payloadLen := int(t.DataOffsets[1] - t.DataOffsets[0])
		if payloadLen <= 0 {
			return nil, fmt.Errorf("tensor %s has empty payload", name)
		}
		if payloadLen%4 != 0 {
			return nil, fmt.Errorf("tensor %s payload is not aligned to float32", name)
		}
		vectorLen := payloadLen / 4
		values := make([]float32, vectorLen)
		for i := range values {
			if err := binary.Read(file, binary.LittleEndian, &values[i]); err != nil {
				return nil, fmt.Errorf("read tensor %s: %w", name, err)
			}
		}
		bank.Tensors[name] = values
		if !contains(bank.Names, name) {
			bank.Names = append(bank.Names, name)
		}
	}
	sort.Strings(bank.Names)
	return bank, nil
}

// PersonaBankFor is shorthand for read-only generation use.
func PersonaBankFor(path string) (*PersonaBank, error) {
	return LoadFile(path)
}
