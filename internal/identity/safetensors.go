package identity

import (
	"encoding/json"
	"fmt"
)

// SafeTensorsHeader represents the JSON metadata section of a safetensors file.
type SafeTensorsHeader struct {
	Metadata map[string]any              `json:"__metadata__"`
	Tensors  map[string]TensorMetadata   `json:"__tensors__"`
}

// TensorMetadata describes a tensor's shape and location in the safetensors payload.
type TensorMetadata struct {
	DType       string   `json:"dtype"`
	Shape       []int    `json:"shape"`
	DataOffsets []uint64 `json:"data_offsets"`
}

// ValidateSafeTensorsHeader checks that all tensors are properly formed.
func ValidateSafeTensorsHeader(h SafeTensorsHeader) error {
	for name, t := range h.Tensors {
		if t.DType != "F32" && t.DType != "F64" && t.DType != "F16" {
			return fmt.Errorf("tensor %s has unsupported dtype %s", name, t.DType)
		}
		if len(t.Shape) == 0 {
			return fmt.Errorf("tensor %s has empty shape", name)
		}
		if len(t.DataOffsets) != 2 {
			return fmt.Errorf("tensor %s has invalid data_offsets length", name)
		}
		if t.DataOffsets[1] <= t.DataOffsets[0] {
			return fmt.Errorf("tensor %s has invalid data_offsets range", name)
		}
	}
	return nil
}

// MarshalSafeTensorsHeader encodes a header to JSON bytes.
func MarshalSafeTensorsHeader(h SafeTensorsHeader) ([]byte, error) {
	return json.Marshal(h)
}

// UnmarshalSafeTensorsHeader decodes a header from JSON bytes.
func UnmarshalSafeTensorsHeader(data []byte) (SafeTensorsHeader, error) {
	var h SafeTensorsHeader
	if err := json.Unmarshal(data, &h); err != nil {
		return h, err
	}
	return h, nil
}
