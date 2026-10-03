# Identity gate calibration

> Canonical identity flow: QNN generation -> SCRFD detection -> five-point alignment -> ArcFace embedding -> calibrated max/mean reference comparison -> quality gate. See [architecture.md](architecture.md) and [master-references.md](master-references.md).

The generation gate (`identity_threshold`, `identity_mean_threshold`) compares a generated image to
a persona's reference pack using ArcFace (w600k_r50) cosine similarity. Thresholds set without
measuring this model on your own data are guesses. `spicecalibrate` measures them.

```bash
go run ./cmd/spicecalibrate -root data/references -out calibration.json
```

It embeds every persona's reference pack with the production SCRFD 5-point + ArcFace path, then
reports, per persona:

- **Leave-one-out max/mean**: each reference scored against the *other* references with the same
  max/mean statistics the gate uses. This is what a perfect same-identity image would score.
- **Impostor max/mean**: other personas' references scored against this persona's pack.
- **Recommended gates**: the lowest threshold that rejects every impostor (plus `-margin`) while
  still accepting every real reference. If the ranges overlap it says so; no threshold can fix that,
  and the reference pack needs work (more consistent frontal references).

Then pass the values to generation, e.g. `{"identity_threshold": 0.58, "identity_mean_threshold": 0.45}`.

## Reading the output

- Needs at least 3 usable references per persona (4+ preferred) and at least 2 personas with packs.
- References that fail face detection are listed under `skipped` and excluded from the gate. Profile,
  eye close-up and back views often fail or score low; keep them out of the pack the gate scores
  against, or gate on frontal references only.
- The swap source (centroid / ranked references) is built from the same pack the gate scores against,
  so post-swap scores are optimistic. Treat the leave-one-out numbers as the honest ceiling.
