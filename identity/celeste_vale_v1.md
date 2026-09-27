# Celeste Vale — visual identity v1

Status: selected for production consistency tests. This is not a ranking of the five persona hypotheses.

## Canonical image

Four-panel reference sheet generated 2026-09-27. Use its first two close-up portraits as the facial source. Preserve the original image asset; do not regenerate the reference from a text description.

## Face anchors

- Fictional adult woman, age 32; warm olive skin with visible natural texture and faint freckles.
- Dark brown almond eyes; slightly asymmetric arched brows; straight, softly rounded nose.
- Natural full lips; small beauty mark on her left cheek (viewer right).
- Espresso-brown, collarbone-length, softly wavy hair.
- Understated sculptural gold earrings. Tailored clothes and restrained makeup are styling, not identity.

## Reusable edit prompt

Create ONE photorealistic editorial photograph of Celeste Vale, the same original fictional adult woman in the supplied four-panel reference sheet. Use the first two close-up panels as the authoritative facial identity. Preserve her exact face geometry, dark brown almond eyes, slightly asymmetric brows, warm olive skin with natural texture and faint freckles, natural lips, small beauty mark on her left cheek (viewer right), and espresso-brown collarbone-length softly wavy hair. She is 32. [SCENE, ACTION, OUTFIT, LIGHTING, CAMERA]. Maintain the identical recognizable face while changing only the specified styling and setting. Eye-level natural perspective, believable anatomy, candid expression. One image, no multi-panel layout, text, watermark, celebrity likeness, or exaggerated retouching.

Supply the actual reference image to the image editing endpoint on every generation. A text-only prompt cannot reliably enforce this identity. Keep a human approval step for any public image.

## Initial identity check

Two independent edits referenced the same sheet:
1. Warm boutique-hotel lobby, burgundy jacket, reviewing fabric samples and plans.
2. Jazz record shelves at dusk, black sweater, mixed window and lamp light.

Qualitative assessment: both retain the distinctive brow, eye, nose, cheek mark, hair, and overall face. The hotel image has a downward gaze, so it is weaker evidence for eye and full face geometry. The jazz image gives a clearer three-quarter face. Result: provisional pass, 2/2 recognizable to one reviewer. This does not establish a statistical identity-consistency rate.

## Next acceptance test

Generate 10 further images across front, three-quarter, and profile angles, outdoor and indoor lighting, and three outfits, always supplying the canonical sheet. Blindly shuffle with 10 other fictional faces and have two reviewers identify Celeste and flag changed facial features. Require at least 9/10 selections by each reviewer, with no recurring face drift, before calling the visual identity production-locked. Archive prompts, reference versions, accepted outputs, rejected outputs, and reviewer notes. Compare the five personas through equivalent content experiments; none has evidence-based priority yet.
