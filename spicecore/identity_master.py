"""Character identity master builder.

Orchestrates master-board creation through the media provider interface, so it
runs against whichever lane is configured — LocalDream over HTTP or the native
Go/QNN lane backed by the cyber_realistic_v10 safetensors
(`scripts/download-cyberrealistic-xl-desire.sh`, `SPICE_QNN_MODEL_DIR`).

Layout (per the identity-master spec):
- Portrait board: one square image, 2x2 grid of closeup portraits
  (front, left 3/4, right 3/4, smile) with the eye closeup composited dead center.
- Rotation set: full-body front / left profile / right profile / back.

Pipeline per docs/master-references.md:
1. Generate per-view images from the persona's `identity_reference` spec.
2. Composite the portrait board with PIL.
3. Score every face-detectable view with the IdentityGate; split the pack into
   `gate/` (ArcFace-stable, for the numerical gate) and `conditioning/`
   (visual continuity only — profiles, back views, eye crops often fail detection).
4. Promote to `data/references/<persona_id>/` and record the ledger.

Personas must be fictional adults (`fictional is True`, `age >= 18`) or generation
is refused. Wardrobe follows the persona's `identity_reference.wardrobe_mode`
(neutral reference clothing; never part of the identity lock).
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .assetgen import DEFAULT_NEGATIVE
from .identity import IdentityGate, load_reference_pack

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

# (view_id, framing description)
PORTRAIT_VIEWS: List[Tuple[str, str]] = [
    ("portrait_front", "closeup portrait, front view, neutral expression"),
    ("portrait_left34", "closeup portrait, left three-quarter view, neutral expression"),
    ("portrait_right34", "closeup portrait, right three-quarter view, neutral expression"),
    ("portrait_smile", "closeup portrait, front view, gentle closed-lip smile"),
]
CENTER_VIEW: Tuple[str, str] = ("eye_closeup", "extreme closeup of one eye, detailed iris")
ROTATION_VIEWS: List[Tuple[str, str]] = [
    ("body_front", "full body, front view, neutral standing pose, arms relaxed"),
    ("body_left", "full body, left profile view, neutral standing pose, arms relaxed"),
    ("body_right", "full body, right profile view, neutral standing pose, arms relaxed"),
    ("body_back", "full body, back view, neutral standing pose, arms relaxed"),
]

MASTER_NEGATIVE = DEFAULT_NEGATIVE + ", sexualized styling, suggestive pose, lingerie, nudity"


def _require_fictional_adult(persona: Dict[str, Any]) -> None:
    if persona.get("fictional") is not True or int(persona.get("age", 0)) < 18:
        raise ValueError("identity master requires a fictional adult persona")


def _identity_anchor(persona: Dict[str, Any]) -> str:
    physical = persona.get("physical", {}) or {}
    ref = persona.get("identity_reference", {}) or {}
    bits = [
        f"Original fictional AI-generated adult character {persona['name']}, age {persona['age']}.",
        f"Distinctive look: {persona.get('visual', '')}.",
    ]
    for key in ("eye_color", "eye_shape", "hair_color", "hair_texture", "skin_tone"):
        if physical.get(key):
            bits.append(f"{key.replace('_', ' ')}: {physical[key]}.")
    feats = physical.get("distinguishing_features") or []
    if feats:
        bits.append("Distinguishing features: " + "; ".join(feats) + ".")
    if ref.get("hair_mode"):
        bits.append(f"Hair: {ref['hair_mode']}.")
    if ref.get("body_prompt"):
        bits.append(f"Body: {ref['body_prompt']}.")
    if ref.get("wardrobe_mode"):
        bits.append(f"Wardrobe: {ref['wardrobe_mode']}.")
    bits.append(
        "Photorealistic reference photography, neutral studio lighting, plain neutral "
        "background, natural skin texture, coherent anatomy. Do not resemble any real "
        "person or public figure."
    )
    return " ".join(b for b in bits if b.strip())


def build_master_prompts(persona: Dict[str, Any]) -> Dict[str, str]:
    """Per-view generation prompts for the identity master set."""
    _require_fictional_adult(persona)
    anchor = _identity_anchor(persona)
    prompts = {}
    for view_id, framing in PORTRAIT_VIEWS + [CENTER_VIEW]:
        prompts[view_id] = f"{anchor} Framing: {framing}."
    for view_id, framing in ROTATION_VIEWS:
        prompts[view_id] = f"{anchor} Framing: {framing}."
    return prompts


def _decode_first_image(result: dict) -> bytes:
    if result.get("image_base64"):
        raw = result["image_base64"]
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw, validate=True)
    images = result.get("images") or []
    if images:
        first = images[0]
        raw = first if isinstance(first, str) else first.get("base64", "")
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw, validate=True)
    raise ValueError("media provider response did not contain image bytes")


def generate_master_views(
    provider,
    persona: Dict[str, Any],
    seed: Optional[int] = None,
    size: int = 1024,
    reference_strength: float = 0.85,
) -> Dict[str, bytes]:
    """Generate every master view through the provider. Returns view_id -> PNG bytes."""
    prompts = build_master_prompts(persona)
    views: Dict[str, bytes] = {}
    for i, (view_id, prompt) in enumerate(prompts.items()):
        view_seed = None if seed is None else seed + i
        is_body = view_id.startswith("body_")
        width, height = (size, size) if not is_body else (size * 3 // 4, size)
        result = provider.generate_image(
            prompt=prompt,
            negative_prompt=MASTER_NEGATIVE,
            seed=view_seed,
            width=width,
            height=height,
            reference_strength=reference_strength,
        )
        views[view_id] = _decode_first_image(result)
    return views


def composite_portrait_board(
    views: Dict[str, bytes],
    cell: int = 1024,
    eye_size: int = 512,
    background: Tuple[int, int, int] = (240, 240, 240),
) -> "PILImage":
    """Assemble the 2x2 portrait grid with the eye closeup dead center."""
    from PIL import Image

    required = [v for v, _ in PORTRAIT_VIEWS] + [CENTER_VIEW[0]]
    missing = [v for v in required if v not in views]
    if missing:
        raise ValueError(f"missing portrait views: {missing}")
    board = Image.new("RGB", (cell * 2, cell * 2), background)
    positions = [(0, 0), (cell, 0), (0, cell), (cell, cell)]
    for (view_id, _), (x, y) in zip(PORTRAIT_VIEWS, positions):
        img = Image.open(__import__("io").BytesIO(views[view_id])).convert("RGB")
        board.paste(img.resize((cell, cell), Image.LANCZOS), (x, y))
    eye = Image.open(__import__("io").BytesIO(views[CENTER_VIEW[0]])).convert("RGB")
    eye = eye.resize((eye_size, eye_size), Image.LANCZOS)
    board.paste(eye, (cell - eye_size // 2, cell - eye_size // 2))
    return board


def promote_master(
    store,
    provider,
    persona: Dict[str, Any],
    views: Dict[str, bytes],
    board: "PILImage",
    reference_root: str | Path = "data/references",
    identity_threshold: float = 0.82,
) -> Dict[str, Any]:
    """Gate each face-detectable view, split gate/conditioning, promote the pack.

    Returns the promotion record (also written to the ledger).
    """
    import io

    reference_root = Path(reference_root)
    gate_dir = reference_root / persona["id"] / "gate"
    cond_dir = reference_root / persona["id"] / "conditioning"
    gate_dir.mkdir(parents=True, exist_ok=True)
    cond_dir.mkdir(parents=True, exist_ok=True)

    board_bytes = io.BytesIO()
    board.save(board_bytes, format="PNG")
    boards_dir = reference_root / persona["id"] / "boards"
    boards_dir.mkdir(parents=True, exist_ok=True)
    (boards_dir / "portrait_board.png").write_bytes(board_bytes.getvalue())

    gate = IdentityGate(provider, threshold=identity_threshold)
    pack = load_reference_pack(persona["id"], reference_root)
    gate_files, cond_files = [], []
    for view_id, raw in views.items():
        score = gate.score(raw, "image/png", pack)
        passed = bool(score.get("scored")) and bool(score.get("passed"))
        dest = gate_dir if passed else cond_dir
        path = dest / f"{view_id}.png"
        path.write_bytes(raw)
        (gate_files if passed else cond_files).append(view_id)
        store.record_event("identity_master_view_scored", {
            "persona_id": persona["id"],
            "view_id": view_id,
            "gate": passed,
            "identity_score": score.get("score"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    record = {
        "persona_id": persona["id"],
        "gate": sorted(gate_files),
        "conditioning": sorted(cond_files),
        "board": "boards/portrait_board.png",
        "reference_root": str(reference_root / persona["id"]),
    }
    store.record_event("identity_master_promoted", record)
    return record
