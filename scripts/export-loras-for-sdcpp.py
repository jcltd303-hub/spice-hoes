#!/usr/bin/env python3
import argparse
from pathlib import Path

from safetensors.torch import load_file, save_file

try:
    from diffusers.utils.state_dict_utils import convert_state_dict_to_kohya
except Exception as exc:
    raise SystemExit(
        "diffusers with convert_state_dict_to_kohya is required; "
        "install requirements-lora.txt first"
    ) from exc


def convert_one(src: Path, dst: Path) -> None:
    state = load_file(str(src), device="cpu")
    # Diffusers DreamBooth LoRA checkpoints use PEFT names. stable-diffusion.cpp
    # understands webui/Kohya-style LoRA names reliably, so normalize once.
    if any(".lora_A." in k or ".lora_B." in k for k in state):
        state = convert_state_dict_to_kohya(state)
    dst.parent.mkdir(parents=True, exist_ok=True)
    save_file(
        state,
        str(dst),
        metadata={
            "format": "pt",
            "source": src.name,
            "spice_target": "stable-diffusion.cpp",
        },
    )
    print(f"READY {src} -> {dst} ({len(state)} tensors)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default="artifacts/loras")
    ap.add_argument("--output-dir", default="artifacts/loras-sdcpp")
    args = ap.parse_args()

    src_dir = Path(args.input_dir)
    dst_dir = Path(args.output_dir)
    personas = [
        "zara_voss",
        "ruby_wren",
        "tess_wilder",
        "celeste_vale",
        "lila_hart",
    ]
    missing = []
    for persona in personas:
        src = src_dir / f"{persona}.safetensors"
        if not src.exists():
            missing.append(str(src))
            continue
        convert_one(src, dst_dir / src.name)
    if missing:
        raise SystemExit("Missing LoRAs: " + ", ".join(missing))


if __name__ == "__main__":
    main()
