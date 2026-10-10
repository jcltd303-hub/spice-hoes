# S24 local compute and free GPU media

The requested outcome is an device-first influencer pipeline that uses the owner's S24 Ultra for as much work as its installed runtimes support. Large video, lip sync, and model training run in an attended free GPU notebook. Local voice interaction remains available without a cloud subscription.

## Runtime boundaries

- Keep the existing Go QNN diffusion, QNN face embedding, and stable-diffusion.cpp Vulkan paths. Report actual runtime health rather than assuming acceleration from the handset name.
- Add a local OpenAI-compatible planning adapter for llama.cpp on loopback. All MoA roles share the loaded GGUF model by default and execute serially to bound phone RAM. Preserve verified revenue and knowledge restrictions independently of provider branding.
- Extend the existing Android loopback companion with offline TextToSpeech and on-device SpeechRecognizer. Microphone access is user initiated with Android permission and visible UI. Never silently substitute cloud recognition or pretend the mock identity backend is accelerated.
- Provide a Python Android voice client and an explicit voice conversation CLI connecting native recognition, local planning, and native playback. Local Piper remains supported for desktop or independently installed Android runtimes.
- Replace media storage with content-addressed sanitized JPEG files in an explicitly configured public directory. A loopback read-only server can expose that directory through the owner's HTTPS hosting/tunnel. Publishing still requires platform tokens and a reachable HTTPS URL.
- Add portable media job bundles and an attended Colab notebook for video generation, speech, and lip sync. Results contain hashes and job identity; import validates them before local use. Free GPU unavailability is a visible pending/blocker condition, not a paid fallback.

## Retired hosted-provider removal

Delete the retired hosted-provider model adapter, SDK/configuration requirements, storage implementation, and training references. Update active docs, fixtures, and historical in-repo design documents so the checked-out project has no provider-specific dependency left. Git history remains intact. Existing external resources are outside repository cleanup scope.

## Verification

Exercise local chat payloads and serialized roles, verified knowledge behavior, sanitized public media delivery and traversal rejection, voice client contracts and unavailable recognition, job bundle integrity and safe extraction. Run the full Python suite, Go tests/builds, web build, shell syntax checks, notebook syntax checks, and Android build/tests where a toolchain is available. Hardware throughput and free GPU execution need the user's devices; report this boundary explicitly.
