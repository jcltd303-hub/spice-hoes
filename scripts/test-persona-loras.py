#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline

PERSONAS = {
    "zara_voss": ("spzara", "Zara Voss"),
    "ruby_wren": ("spruby", "Ruby Wren"),
    "tess_wilder": ("sptess", "Tess Wilder"),
    "celeste_vale": ("spceleste", "Celeste Vale"),
    "lila_hart": ("splila", "Lila Hart"),
}

DEFAULT_SCENE = (
    "photorealistic editorial portrait of {token} woman, fictional adult woman, "
    "natural skin texture, realistic eyes, realistic hair, soft daylight, "
    "85mm lens, shallow depth of field, neutral background"
)

NEGATIVE = (
    "cartoon, anime, illustration, painting, drawing, 3d render, plastic skin, "
    "doll, deformed, extra fingers, duplicate person, text, watermark"
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lora-dir", default="artifacts/loras")
    ap.add_argument("--out-dir", default="artifacts/lora-previews")
    ap.add_argument("--base-model", default="stabilityai/stable-diffusion-xl-base-1.0")
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--cfg", type=float, default=5.5)
    ap.add_argument("--strength", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=768)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    pipe = StableDiffusionXLPipeline.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        use_safetensors=True,
    ).to("cuda")
    pipe.enable_attention_slicing()

    g = torch.Generator(device="cuda").manual_seed(args.seed)

    for persona, (token, label) in PERSONAS.items():
        lora = Path(args.lora_dir) / f"{persona}.safetensors"
        if not lora.exists():
            print(f"SKIP {persona}: missing {lora}")
            continue

        try:
            pipe.unload_lora_weights()
        except Exception:
            pass

        pipe.load_lora_weights(str(lora.parent), weight_name=lora.name, adapter_name=persona)
        pipe.set_adapters([persona], adapter_weights=[args.strength])

        prompt = DEFAULT_SCENE.format(token=token)
        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE,
            num_inference_steps=args.steps,
            guidance_scale=args.cfg,
            width=args.width,
            height=args.height,
            generator=g,
        ).images[0]

        dest = out / f"{persona}.png"
        image.save(dest)
        print(f"READY {label}: {dest}")

if __name__ == "__main__":
    main()
