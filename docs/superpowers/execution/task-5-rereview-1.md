**HTTPResponse.read(65536) can buffer trickle SSE beyond total deadline** — NOT ADDRESSED, spicecore/localdream.py:26-33,59-65. Non-chunked payload reads are corrected, but HTTPResponse.read1 delegates chunked responses to _read1_chunked, whose _get_chunk_left performs buffered readline for the next chunk-size/extension line and buffered reads for framing/trailers. A peer can trickle a valid long chunk extension faster than the fixed per-socket inactivity timeout yet keep one read1 call inside readline beyond the total budget. The post-read clock check cannot interrupt that operation. The regression at tests/test_localdream.py:48-83 uses no Transfer-Encoding: chunked header and therefore does not exercise this remaining path. Bound transport reads themselves by the monotonic deadline, including HTTP chunk framing, and add a chunked slow-framing regression.

**Size-limit fixture did not reach actual stream cap** — ADDRESSED, tests/test_localdream.py:38-43. The 65545-byte fixture exceeds the 65544-byte cap for max_image_bytes=4 and asserts the specific stream-limit error; the valid 6-byte RGB completion separately asserts decoded image-limit rejection.

**New Breakage in the Fix Diff** — None found; the chunked deadline problem is the existing finding remaining open.

**Out-of-Scope Observations** — None.

**Checks** — Read task brief, appended fix report, and fix diff once; inspected amended source/tests at head36f7ecb004148aef9168cdcad8b6e51fc2afee90. Report names test_httpresponse_trickle_respects_deadline, records RED78 tests/sole failure6553.6 simulated seconds, and GREEN78 tests/OK in1.811s (Actions36751338315). No suite rerun. Verified CPython3.12 Lib/http/client.py:551-610,694-748 confirms read1 chunked framing may perform multiple buffered reads. Runtime unavailable; no focused execution claimed.

**Fix round:** Findings remain open — total deadline under chunked HTTP framing.
