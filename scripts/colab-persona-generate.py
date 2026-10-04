#!/usr/bin/env python3
import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path

# Colab images can ship an old torchao that PEFT detects and rejects.
# Remove it before importing diffusers/peft; torchao is not required for this LoRA path.
try:
    torchao_version = importlib.metadata.version("torchao")
except importlib.metadata.PackageNotFoundError:
    torchao_version = None

if torchao_version:
    from packaging.version import Version
    if Version(torchao_version) < Version("0.16.0"):
        print(f"Removing incompatible torchao {torchao_version}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchao"],
            check=True,
        )

import torch
from diffusers import StableDiffusionXLPipeline

PERSONAS = {
    "zara_voss": ("spzara", "Zara Voss"),
    "ruby_wren": ("spruby", "Ruby Wren"),
    "tess_wilder": ("sptess", "Tess Wilder"),
    "celeste_vale": ("spceleste", "Celeste Vale"),
    "lila_hart": ("splila", "Lila Hart"),
}

PERSONA_CUES = {
    "zara_voss": "dark compact-curly high bun, warm medium olive skin, strong brows, amber-brown deep-set almond eyes",
    "ruby_wren": "vivid copper-red short textured bob, fair neutral skin with freckles, green-hazel eyes, youthful adult facial proportions",
    "tess_wilder": "tied-back dark brown hair, neutral light-medium freckled skin, gray-green slightly hooded almond eyes, athletic adult face, balanced jawline",
    "celeste_vale": "dark brunette hair pulled back, olive skin, hazel-brown almond eyes, refined dark brows, angular mature elegance, beauty mark on left cheek",
    "lila_hart": "warm light freckled complexion, green-gray round-almond eyes, light chestnut hair with subtle highlights pulled back, soft approachable adult facial geometry",
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
    ap.add_argument("--persona", choices=["all", *sorted(PERSONAS)], default="lila_hart")
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

    personas = list(PERSONAS) if args.persona == "all" else [args.persona]
    missing = [
        str(Path(args.lora_dir) / f"{persona}.safetensors")
        for persona in personas
        if not (Path(args.lora_dir) / f"{persona}.safetensors").is_file()
    ]
    if missing:
        raise SystemExit("Missing LoRA(s):\n" + "\n".join(missing))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pipe = StableDiffusionXLPipeline.from_pretrained(
        args.base_model,
        dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )

    # T4-friendly: load SDXL once, then hot-swap the five persona LoRAs.
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()

    for index, persona in enumerate(personas):
        token, label = PERSONAS[persona]
        lora = Path(args.lora_dir) / f"{persona}.safetensors"
        out_path = out_dir / f"{persona}-{args.seed}.png"

        try:
            pipe.unload_lora_weights()
        except Exception:
            pass

        pipe.load_lora_weights(str(lora.parent), weight_name=lora.name, adapter_name=persona)
        pipe.set_adapters([persona], adapter_weights=[args.strength])

        prompt = args.prompt.strip() or DEFAULT_SCENE.format(token=token)
        prompt = prompt.replace("TOKEN", token)
        cue = PERSONA_CUES.get(persona, "")
        if cue:
            prompt = f"{prompt}, identity traits: {cue}"
        if token not in prompt:
            prompt = f"{token}, {prompt}"

        generator = torch.Generator(device="cuda").manual_seed(args.seed + index)
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
