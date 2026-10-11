# Canon and Local Dream realism test

The five existing `data/references/<persona>/canon-01.png` boards remain the
authoritative fictional adult identities. Each board was visually inspected and
preserved unchanged. Dimensions and SHA-256 checksums, including the 46 archived
legacy images, are recorded in `data/references/manifest.json`.

The Go reference loader already requires canon filenames. The optional Python
adapter now selects only canon whenever canon is present, before applying its
image limit. Legacy-only packs remain supported by that historical adapter.
New bootstrap/support outputs in active folders remain ignored by Git.

Run one test on the S24 from the repository, with the Local Dream HTTP generation
service running and the SCRFD/ArcFace native face runtime installed:

```bash
bash scripts/test-local-dream-image.sh celeste_vale
```

Other valid personas are `lila_hart`, `ruby_wren`, `tess_wilder` and `zara_voss`.
Preview the request without contacting the runtime or changing banks:

```bash
bash scripts/test-local-dream-image.sh celeste_vale --dry-run
```

The test loads `.env`, then `.env.spicemedia`, preserving an explicitly supplied
`LOCAL_DREAM_URL` and `LOCAL_DREAM_TOKEN`. The default generation URL is
`http://127.0.0.1:8081`. A loopback URL reaches only the machine running the
command; this workspace cannot reach the phone through its own loopback address.

The test uses `generator=local-dream` through `spicemedia identity-generate`.
It rebuilds all five ArcFace persona banks from canon first, staging the entire
set before replacing existing banks and retaining previous banks in the archive.
The old anchor-weighted bank rebuild is replaced by this canon-only path.

The `photo-test` prompt starts with photographic capture and face traits. It
omits body, hobbies and lifestyle cues to isolate a plain head-and-shoulders
portrait. Defaults are one candidate, seed 41000, 24 steps, guidance 5.5 and
768x1024. These are test settings, not measured optimal settings. Local Dream's
SDXL backend may render a fixed 1024x1024 canvas; actual output dimensions are
reported after decoding.

Override settings when comparing the same installed model:

```bash
SPICE_TEST_GUIDANCE=6 SPICE_TEST_STEPS=28 SPICE_TEST_SEED=41000 \
  bash scripts/test-local-dream-image.sh celeste_vale
```

`SPICE_TEST_WIDTH`, `SPICE_TEST_HEIGHT`, `SPICE_TEST_SCENE`, `SPICE_TEST_OUT_ROOT`
and `SPICE_TEST_OPEN=0` are also supported. Select an installed photographic
checkpoint in Local Dream before testing; an anti-cartoon negative prompt cannot
establish that the active checkpoint produces photographs.

Canon banks provide identity scoring and, when available, the existing InSwapper
identity-transfer stage. They are ArcFace identity vectors, not diffusion LoRAs
or textual-inversion tokens. The Local Dream SD/SDXL text-to-image request does
not directly condition on the canon board pixels. A configured textual-inversion
token is used only when the runtime reports it loaded. Inspect identity and
quality scores alongside visual likeness; do not treat a generated candidate as
a new canon image automatically.

Each run saves `request.json`, `health.json`, `banks.log`, `result.json`, the PNG
and its generation sidecar under ignored `data/runs/local-dream-realism/`.
The client requests PNG transport and still handles raw RGB/RGBA from older
runtimes; the Go pipeline always writes an encoded PNG. Pillow verifies the
saved file. On Android, the test copies it to shared Downloads when writable and
uses `termux-open --view --content-type image/png`. A viewer failure leaves the
image available and does not turn a completed generation into a failure.

Visual acceptance still requires viewing the actual generated image. Software
tests, dry runs and a reachable health endpoint do not prove model realism or
S24 inference success.
