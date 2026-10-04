#!/usr/bin/env python3
import argparse
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
    "photorealistic portrait photo of {token} woman, fictional adult woman, "
    "natural daylight, realistic skin texture, realistic eyes, detailed hair, "
    "85mm lens, shallow depth of field"
)

NEGATIVE = (
    "cartoon, anime, illustration, painting, drawing, cgi, 3d render, plastic skin, "
    "doll, deformed, extra fingers, duplicate person, text, watermark"
)

def main():
    ap = argparse.ArgumentParser(description="Fast SDXL persona LoRA inference for Google Colab")
    ap.add_argument("--persona", choices=sorted(PERSONAS), default="lila_hart")
    ap.add_argument("--lora-dir", default="/content/drive/MyDrive/spice-hoes/loras")
    ap.add_argument("--out-dir", default="/content/drive/MyDrive/spice-hoes/generated")
    ap.add_argument("--base-model", default="stabilityai/stable-diffusion-xl-base-1.0")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative", default=NEGATIVE)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--cfg", type=float, default=5.5)
    ap.add_argument("--strength", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=768)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required. In Colab: Runtime > Change runtime type > T4 GPU")

    token, label = PERSONAS[args.persona]
    lora = Path(args.lora_dir) / f"{args.persona}.safetensors"
    if not lora.is_file():
        raise SystemExit(f"Missing LoRA: {lora}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.persona}-{args.seed}.png"

    pipe = StableDiffusionXLPipeline.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.load_lora_weights(str(lora.parent), weight_name=lora.name, adapter_name=args.persona)
    pipe.set_adapters([args.persona], adapter_weights=[args.strength])

    # T4-friendly: keep the heavy UNet/VAE moving through CUDA while avoiding OOM.
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()

    prompt = args.prompt.strip() or DEFAULT_SCENE.format(token=token)
    if token not in prompt:
        prompt = f"{token}, {prompt}"

    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    image = pipe(
        prompt=prompt,
        negative_prompt=args.negative,
        num_inference_steps=args.steps,
        guidance_scale=args.cfg,
        width=args.width,
        height=args.height,
        generator=generator,
    ).images[0]

    image.save(out_path)
    print(f"READY {label}: {out_path}")

if __name__ == "__main__":
    main()
