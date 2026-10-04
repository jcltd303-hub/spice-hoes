#!/usr/bin/env bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$HOME/spice-hoes}"
cd "$ROOT"

# Load the native media/QNN environment used by the working spicemedia setup.
# Prefer the Termux-specific file when present, then fall back to .env.
if [[ -f "$ROOT/.env.spicemedia" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.spicemedia"
  set +a
elif [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Self-heal the two face-model paths when the files are installed in the
# repository-standard Termux location but the env file did not export them.
if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" && -s "$ROOT/models/face/scrfd_10g.bin" ]]; then
  export SPICE_FACE_DETECT_MODEL="$ROOT/models/face/scrfd_10g.bin"
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" && -s "$ROOT/models/face/arcface_w600k_r50.bin" ]]; then
  export SPICE_FACE_EMBED_MODEL="$ROOT/models/face/arcface_w600k_r50.bin"
fi

if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" || ! -s "${SPICE_FACE_DETECT_MODEL:-}" ]]; then
  echo "SCRFD model is not configured/found." >&2
  echo "Expected: $ROOT/models/face/scrfd_10g.bin" >&2
  echo "Run: bash scripts/install-face-embedding-termux.sh" >&2
  exit 4
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" || ! -s "${SPICE_FACE_EMBED_MODEL:-}" ]]; then
  echo "ArcFace model is not configured/found." >&2
  echo "Expected: $ROOT/models/face/arcface_w600k_r50.bin" >&2
  echo "Run: bash scripts/install-face-embedding-termux.sh" >&2
  exit 5
fi

echo "==> face detector: $SPICE_FACE_DETECT_MODEL"
echo "==> face embedder: $SPICE_FACE_EMBED_MODEL"

REFERENCE_ROOT="${SPICE_REFERENCE_ROOT:-data/references}"
OUT_ROOT="${SPICE_CANON_OUT_ROOT:-data/runs/canon-scenes}"
GENERATOR="${SPICE_CANON_GENERATOR:-qnn}"

# auto-detect a locally installed QNN generation model if the env file has not
# been populated yet. Validate the model layout before selecting it so the
# native core is never launched with an incompatible --type.
detect_qnn_model() {
  local root="${1:-$HOME/spice-models}"
  local d

  # Prefer a complete SDXL/QNN package.
  while IFS= read -r unet; do
    d="$(dirname "$unet")"
    if [[ -s "$d/tokenizer.json" &&
          -s "$d/clip.mnn" &&
          -s "$d/clip_2.mnn" &&
          -s "$d/pos_emb.bin" &&
          -s "$d/pos_emb_2.bin" &&
          -s "$d/token_emb.bin" &&
          -s "$d/token_emb_2.bin" &&
          -s "$d/vae_decoder.bin" ]]; then
      printf '%s|sdxl\n' "$d"
      return 0
    fi
  done < <(find "$root" -type f -name unet.bin -print 2>/dev/null)

  # Fall back to a complete SD15/QNN package.
  while IFS= read -r unet; do
    d="$(dirname "$unet")"
    if [[ -s "$d/tokenizer.json" &&
          -s "$d/clip_v2.mnn" &&
          -s "$d/pos_emb.bin" &&
          -s "$d/token_emb.bin" &&
          -s "$d/vae_decoder.bin" ]]; then
      printf '%s|sd15npu\n' "$d"
      return 0
    fi
  done < <(find "$root" -type f -name unet.bin -print 2>/dev/null)

  return 1
}

validate_qnn_model() {
  local d="$1"
  local t="$2"
  case "$t" in
    sdxl)
      [[ -s "$d/tokenizer.json" &&
         -s "$d/clip.mnn" &&
         -s "$d/clip_2.mnn" &&
         -s "$d/pos_emb.bin" &&
         -s "$d/pos_emb_2.bin" &&
         -s "$d/token_emb.bin" &&
         -s "$d/token_emb_2.bin" &&
         -s "$d/unet.bin" &&
         -s "$d/vae_decoder.bin" ]]
      ;;
    sd15npu)
      [[ -s "$d/tokenizer.json" &&
         -s "$d/clip_v2.mnn" &&
         -s "$d/pos_emb.bin" &&
         -s "$d/token_emb.bin" &&
         -s "$d/unet.bin" &&
         -s "$d/vae_decoder.bin" ]]
      ;;
    *)
      return 1
      ;;
  esac
}

if [[ -z "${SPICE_QNN_MODEL_DIR:-}" ||
      -z "${SPICE_QNN_TYPE:-}" ||
      ! -d "${SPICE_QNN_MODEL_DIR:-}" ]] ||
   ! validate_qnn_model "${SPICE_QNN_MODEL_DIR:-}" "${SPICE_QNN_TYPE:-}"; then
  detected="$(detect_qnn_model "$HOME/spice-models" || true)"
  if [[ -n "$detected" ]]; then
    export SPICE_QNN_MODEL_DIR="${detected%%|*}"
    export SPICE_QNN_TYPE="${detected##*|}"
  else
    unset SPICE_QNN_MODEL_DIR
  fi
fi

mkdir -p "$OUT_ROOT" personas

# Self-heal Go module checksums before compiling spicemedia. This is required
# on fresh Termux clones when go.mod contains a dependency that is not yet in go.sum.
echo "==> syncing Go module checksums"
go mod tidy

PERSONAS=(
  zara_voss
  ruby_wren
  tess_wilder
  celeste_vale
  lila_hart
)

echo "==> generation backend: $GENERATOR"
if [[ "$GENERATOR" == "qnn" ]]; then
  if [[ -z "${SPICE_QNN_MODEL_DIR:-}" || ! -d "${SPICE_QNN_MODEL_DIR:-}" ]]; then
    echo "QNN generation requested but SPICE_QNN_MODEL_DIR is missing or invalid: ${SPICE_QNN_MODEL_DIR:-<unset>}" >&2
    echo "Install/select a photoreal SDXL QNN model before running this script." >&2
    echo "Recommended: bash scripts/download-cyberrealistic-xl-desire.sh" >&2
    exit 6
  fi
  echo "==> QNN model: $SPICE_QNN_MODEL_DIR"
fi

# Build identity banks with the lightweight face-only QNN core. Starting the
# full SDXL core just to run SCRFD/ArcFace can exceed the nativecore startup
# timeout and is unnecessary.
BANK_BUILD_QNN_MODEL_DIR="${SPICE_QNN_MODEL_DIR:-}"
BANK_BUILD_QNN_TYPE="${SPICE_QNN_TYPE:-}"
unset SPICE_QNN_MODEL_DIR
echo "==> bank-build QNN mode: face-only"

echo "==> rebuilding Canon persona safetensors"
for persona in "${PERSONAS[@]}"; do
  ref_dir="$REFERENCE_ROOT/$persona"
  if [[ ! -d "$ref_dir" ]]; then
    echo "missing Canon reference directory: $ref_dir" >&2
    exit 2
  fi

  mapfile -t canon_refs < <(
    find "$ref_dir" -maxdepth 1 -type f \( \
      -iname 'canon.png' -o -iname 'canon.jpg' -o -iname 'canon.jpeg' -o \
      -iname 'canon-*.png' -o -iname 'canon-*.jpg' -o -iname 'canon-*.jpeg' -o \
      -iname 'canon_*.png' -o -iname 'canon_*.jpg' -o -iname 'canon_*.jpeg' \
    \) | sort
  )

  if (( ${#canon_refs[@]} == 0 )); then
    echo "no strict Canon references found for $persona in $ref_dir" >&2
    echo "expected canon.png or canon-* / canon_* image files" >&2
    echo "old anchor-* and bootstrap-* files are intentionally ignored" >&2
    exit 3
  fi

  echo "  $persona Canon refs:"
  printf '    %s\n' "${canon_refs[@]}"

  go run ./cmd/spicemedia persona-bank-build \
    --persona "$persona" \
    --reference-root "$REFERENCE_ROOT" \
    --out "personas/${persona}.safetensors"
done

# Restore the full generation model after the face-only bank build.
if [[ -n "$BANK_BUILD_QNN_MODEL_DIR" ]]; then
  export SPICE_QNN_MODEL_DIR="$BANK_BUILD_QNN_MODEL_DIR"
fi
if [[ -n "$BANK_BUILD_QNN_TYPE" ]]; then
  export SPICE_QNN_TYPE="$BANK_BUILD_QNN_TYPE"
fi

# persona-bank-build may leave the shared QNN core running in face-only mode.
# A healthy face-only core has /health, /face/detect, and /identity/embed but
# no /generate, which produces HTTP 404. Restart it now so the first scene
# generation launches the core with the selected SDXL model directory.
if [[ "$GENERATOR" == "qnn" ]]; then
  echo "==> restarting QNN core in generation mode"
  pkill -f 'spice-qnn-core' >/dev/null 2>&1 || true
  pkill -f 'stable_diffusion_core' >/dev/null 2>&1 || true
  sleep 1
fi

generate_scene() {
  local persona="$1"
  local theme="$2"
  local scene="$3"
  local out_json="$OUT_ROOT/${persona}.json"

  echo "==> generating $persona"

  # identity-generate scores identity/quality but does not use those scores as
  # an output gate. The generated asset + metadata are emitted regardless of
  # pass/fail score. --require-persona-bank guarantees the freshly rebuilt
  # Canon safetensors is actually used.
  payload=$(jq -cn --arg generator "$GENERATOR" '{
    generator: $generator,
    negative_prompt: "illustration, cartoon, comic, anime, manga, cel shading, line art, vector art, digital painting, painterly, stylized render, graphic novel, flat colors, thick outlines, posterized skin, public figure likeness, child, teen, underage, youth-coded sexual styling, extra fingers, malformed hands, duplicate limbs, distorted face, waxy skin, plastic skin, 3d render, watermark, logo, text artifacts, soft focus, blurry face, smeared skin texture, motion blur, low facial contrast, excessive denoise"
  }')

  printf '%s' "$payload" | go run ./cmd/spicemedia identity-generate \
    --persona "$persona" \
    --persona-bank "personas/${persona}.safetensors" \
    --require-persona-bank \
    --theme "$theme" \
    --scene "$scene" \
    > "$out_json"

  jq '{
    persona_id,
    status,
    asset_path,
    documents_path,
    identity: {
      score: .identity.score,
      mean_score: .identity.mean_score,
      prototype_score: .identity.prototype_score,
      nearest_other_persona: .identity.nearest_other_persona,
      nearest_other_score: .identity.nearest_other_score,
      identity_margin: .identity.identity_margin,
      passed: .identity.passed
    },
    quality: {
      score: .quality.local_score,
      passed: .quality_passed
    },
    generator: .generation.generator
  }' "$out_json"
  printf '\n'
}

generate_scene   zara_voss   "editorial portrait in motion"   "humid neon night market, impromptu percussion set, colorful stalls and warm string lights, candid controlled posture, cinematic documentary realism"

generate_scene   ruby_wren   "creative editorial portrait"   "rooftop at dusk with telescope, astronomy notes and self-published zines, city lights softly blurred behind her, modern editorial realism"

generate_scene   tess_wilder   "athletic documentary portrait"   "indoor climbing gym between attempts, chalked hands, route wall behind her, functional training gear, preserve the left below-knee athletic prosthesis when visible"

generate_scene   celeste_vale   "luxury editorial portrait"   "refined boutique hotel interior at golden hour, reviewing material samples and design plans, sculptural jewelry, composed natural realism"

generate_scene   lila_hart   "warm lifestyle portrait"   "ceramics studio in soft daylight, shaping a clay bowl at the wheel, handmade pastel ceramics and herbs nearby, grounded adult contemporary realism"

echo "==> complete"
echo "scene metadata: $OUT_ROOT"
