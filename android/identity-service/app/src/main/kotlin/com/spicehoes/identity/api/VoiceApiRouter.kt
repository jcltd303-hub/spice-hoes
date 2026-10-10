package com.spicehoes.identity.api

import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import com.spicehoes.identity.http.HttpRequest
import com.spicehoes.identity.http.HttpResponse
import com.spicehoes.identity.voice.ListenOptions
import com.spicehoes.identity.voice.SpeechOptions
import com.spicehoes.identity.voice.VoiceBackend
import com.spicehoes.identity.voice.DenyVoiceAuthorizer
import com.spicehoes.identity.voice.VoiceAuthorizer
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.util.Base64
import java.util.Locale

/** Voice readiness is deliberately independent of the identity model's state. */
class VoiceApiRouter(private val backend: VoiceBackend, private val authorizer: VoiceAuthorizer = DenyVoiceAuthorizer) {
    private val methods = mapOf(
        "/voice/health" to "GET", "/voice/voices" to "GET",
        "/voice/synthesize" to "POST", "/voice/speak" to "POST", "/voice/listen" to "POST",
    )

    fun handles(path: String) = path in methods

    fun handle(req: HttpRequest): HttpResponse {
        if (req.method != methods[req.path]) throw ServiceException(ErrorCode.INVALID_REQUEST, "method not allowed", 405)
        if (req.path != "/voice/health" && !authorizer.isAuthorized(req.headers["authorization"])) {
            throw ServiceException(ErrorCode.UNAUTHORIZED,
                "Voice pairing required; tap Copy voice pairing command in the companion and send Authorization: Bearer with that token")
        }
        if (req.method == "POST" && req.headers["content-type"]?.substringBefore(';')?.trim()?.lowercase(Locale.ROOT) != "application/json") {
            throw ServiceException(ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Voice POST requests require Content-Type: application/json")
        }
        return when (req.path) {
            "/voice/health" -> health()
            "/voice/voices" -> {
                requireTts()
                val voices = backend.voices().map {
                    JSONObject().put("voice_id", it.id).put("name", it.name).put("language", it.language)
                        .put("offline", true)
                }
                json(freeTts().put("voices", JSONArray(voices)))
            }
            "/voice/synthesize" -> {
                val options = speechOptions(body(req))
                requireTts()
                json(freeTts().put("mime_type", "audio/wav")
                    .put("audio_base64", Base64.getEncoder().encodeToString(backend.synthesize(options))))
            }
            "/voice/speak" -> {
                val options = speechOptions(body(req))
                requireTts()
                backend.speak(options)
                json(freeTts().put("spoken", true))
            }
            "/voice/listen" -> {
                val body = body(req)
                val options = ListenOptions(language(body), number(body, "timeout_seconds", 15.0, 1.0, 30.0))
                val health = backend.health()
                if (!health.running) throw ServiceException(ErrorCode.RECOGNITION_UNAVAILABLE, health.recognitionReasons.joinToString(" "))
                health.recognition.requireAvailable()
                json(JSONObject().put("text", backend.listen(options)).put("provider", "android-on-device").put("cost_cents", 0))
            }
            else -> throw ServiceException(ErrorCode.INVALID_REQUEST, "unknown voice endpoint", 404)
        }
    }

    private fun health(): HttpResponse {
        val h = backend.health()
        val reasons = buildList {
            if (!h.ttsReady) add(h.ttsReason ?: "Offline TTS is unavailable.")
            addAll(h.recognitionReasons)
        }
        return json(JSONObject().put("auth_required", true).put("ready", h.ready).put("tts_ready", h.ttsReady)
            .put("recognition_available", h.recognitionAvailable)
            .put("tts_reason", h.ttsReason ?: JSONObject.NULL)
            .put("recognition_reasons", JSONArray(h.recognitionReasons)).put("reasons", JSONArray(reasons))
            .put("sdk_int", h.recognition.sdkInt).put("microphone_permission", h.recognition.microphoneGranted)
            .put("activity_visible", h.recognition.activityVisible).put("provider", "android-offline")
            .put("cost_cents", 0).put("accelerated", false)
            .put("acceleration", "Platform-managed speech; GPU/NPU acceleration is not verified."))
    }

    private fun requireTts() {
        val h = backend.health()
        if (!h.ttsReady) throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, h.ttsReason ?: "Offline TTS is unavailable.")
    }

    private fun speechOptions(body: JSONObject): SpeechOptions {
        val text = body.opt("text") as? String ?: invalid("text must be a string")
        if (text.isBlank() || text.length > 4000) invalid("text must contain 1 to 4000 characters and cannot be blank")
        return SpeechOptions(text, optionalString(body, "voice_id"), language(body),
            number(body, "pitch", 1.0, 0.5, 2.0).toFloat(), number(body, "pace", 1.0, 0.5, 2.0).toFloat())
    }

    private fun body(req: HttpRequest): JSONObject {
        if (req.body.size > 32 * 1024) invalid("voice JSON body exceeds 32 KiB")
        return try { JSONObject(String(req.body, Charsets.UTF_8)) }
        catch (_: JSONException) { invalid("body must be a JSON object") }
    }

    private fun optionalString(body: JSONObject, key: String): String? {
        if (!body.has(key) || body.isNull(key)) return null
        val value = body.opt(key) as? String ?: invalid("$key must be a string")
        if (value.isBlank() || value.length > 256) invalid("$key must be a nonblank string of at most 256 characters")
        return value
    }

    private fun language(body: JSONObject): String? {
        val tag = optionalString(body, "language") ?: return null
        try { Locale.Builder().setLanguageTag(tag).build() }
        catch (_: java.util.IllformedLocaleException) { invalid("language must be a BCP-47 language tag, for example en-US") }
        if (Locale.forLanguageTag(tag).language.isEmpty() || tag.equals("und", true)) invalid("language must identify a language")
        return tag
    }

    private fun number(body: JSONObject, key: String, default: Double, min: Double, max: Double): Double {
        if (!body.has(key)) return default
        val value = (body.opt(key) as? Number)?.toDouble() ?: invalid("$key must be a number")
        if (!value.isFinite() || value < min || value > max) invalid("$key must be between $min and $max")
        return value
    }

    private fun invalid(message: String): Nothing = throw ServiceException(ErrorCode.INVALID_REQUEST, message)
    private fun freeTts() = JSONObject().put("provider", "android-offline").put("cost_cents", 0)
    private fun json(body: JSONObject) = HttpResponse(200, "application/json", body.toString().toByteArray(Charsets.UTF_8))
}
