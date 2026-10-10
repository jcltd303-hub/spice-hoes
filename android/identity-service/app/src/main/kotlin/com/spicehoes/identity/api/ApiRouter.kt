package com.spicehoes.identity.api

import com.spicehoes.identity.BuildMeta
import com.spicehoes.identity.DiagLog
import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.Hashing
import com.spicehoes.identity.InferenceGate
import com.spicehoes.identity.ServiceException
import com.spicehoes.identity.ServiceState
import com.spicehoes.identity.ServiceStatus
import com.spicehoes.identity.backend.IdentityBackend
import com.spicehoes.identity.backend.TransferOptions
import com.spicehoes.identity.http.HttpRequest
import com.spicehoes.identity.http.HttpResponse
import com.spicehoes.identity.image.ImageInspector
import com.spicehoes.identity.voice.UnavailableVoiceBackend
import com.spicehoes.identity.voice.VoiceBackend
import com.spicehoes.identity.voice.DenyVoiceAuthorizer
import com.spicehoes.identity.voice.VoiceAuthorizer
import org.json.JSONException
import org.json.JSONObject
import java.util.Base64
import java.util.UUID

/**
 * GET  /health   server / model / acceleration state (always answers, even while loading)
 * POST /transfer JSON {reference_image, target_image, preserve_composition?, response_format?}
 *                Images are base64 PNG/JPEG/WebP. Response is JSON+base64 by default, or raw
 *                image/png when `Accept: image/png` or response_format="png" (metadata in X-* headers).
 */
class ApiRouter(
    private val status: ServiceStatus,
    private val backend: IdentityBackend,
    private val inspector: ImageInspector,
    private val meta: BuildMeta,
    private val thermal: () -> String = { "NORMAL" },
    private val gate: InferenceGate = InferenceGate(),
    voice: VoiceBackend = UnavailableVoiceBackend,
    voiceAuthorizer: VoiceAuthorizer = DenyVoiceAuthorizer,
) {
    private val voiceRouter = VoiceApiRouter(voice, voiceAuthorizer)

    fun handle(req: HttpRequest): HttpResponse = try {
        when {
            voiceRouter.handles(req.path) -> voiceRouter.handle(req)
            req.path == "/health" && req.method == "GET" -> health()
            req.path == "/transfer" && req.method == "POST" -> transfer(req)
            req.path == "/health" || req.path == "/transfer" ->
                throw ServiceException(ErrorCode.INVALID_REQUEST, "method not allowed", 405)
            else -> throw ServiceException(ErrorCode.INVALID_REQUEST, "unknown endpoint ${req.path}", 404)
        }
    } catch (t: Throwable) {
        errorResponse(t)
    }

    fun errorResponse(t: Throwable): HttpResponse {
        val e = toServiceException(t)
        val err = JSONObject()
            .put("code", e.code.name)
            .put("message", e.message ?: "")
            .put("request_id", e.requestId ?: JSONObject.NULL)
        val headers = if (e.code == ErrorCode.UNAUTHORIZED) mapOf("WWW-Authenticate" to "Bearer realm=\"spice-voice\"") else emptyMap()
        return json(e.httpStatus, JSONObject().put("error", err), headers)
    }

    private fun toServiceException(t: Throwable): ServiceException = when (t) {
        is ServiceException -> t
        is OutOfMemoryError -> ServiceException(ErrorCode.OUT_OF_MEMORY, "out of memory")
        else -> ServiceException(ErrorCode.INTERNAL_ERROR, t.toString())
    }

    private fun health(): HttpResponse {
        val h = backend.health()
        val ready = status.state == ServiceState.READY
        val body = JSONObject()
            .put("ready", ready)
            .put("state", status.state.name)
            .put("service", "spice-identity")
            .put("version", meta.version)
            .put("api_version", meta.apiVersion)
            .put("build_id", meta.buildId)
            .put("commit", meta.commit)
            .put("port", meta.port)
            .put("model", h.modelId)
            .put("model_loaded", h.modelLoaded)
            .put("backend", h.backend)
            .put("provider", h.provider)
            .put("accelerated", ready && h.accelerated)
            .put("identity_applied", h.identityApplied)
            .put("thermal", thermal())
            .put("completed", status.completed.get())
            .put("failed", status.failed.get())
            .put("last_error", status.lastError ?: JSONObject.NULL)
        return json(200, body)
    }

    private fun transfer(req: HttpRequest): HttpResponse {
        val requestId = UUID.randomUUID().toString().replace("-", "").take(12)
        val t0 = System.nanoTime()
        return try {
            doTransfer(req, requestId, t0)
        } catch (t: Throwable) {
            val e = toServiceException(t)
            e.requestId = requestId
            status.failed.incrementAndGet()
            status.lastError = "${e.code}: ${e.message}"
            status.lastRequest = "POST /transfer FAILED id=$requestId ${e.code}"
            DiagLog.log("W", "transfer $requestId failed: ${e.code} ${e.message}")
            throw e
        }
    }

    private fun doTransfer(req: HttpRequest, requestId: String, t0: Long): HttpResponse {
        val body = try {
            JSONObject(String(req.body, Charsets.UTF_8))
        } catch (e: JSONException) {
            throw ServiceException(ErrorCode.INVALID_REQUEST, "body must be a JSON object")
        }
        val reference = decodeImage(body, "reference_image", ErrorCode.REFERENCE_REQUIRED)
        val target = decodeImage(body, "target_image", ErrorCode.TARGET_REQUIRED)
        val preserve = body.optBoolean("preserve_composition", true)
        val wantsPng = body.optString("response_format", "").equals("png", true) ||
            req.headers["accept"]?.contains("image/png", ignoreCase = true) == true

        if (status.state != ServiceState.READY) {
            throw ServiceException(ErrorCode.MODEL_NOT_READY, "service state is ${status.state}")
        }
        if (thermal() == "CRITICAL") {
            throw ServiceException(ErrorCode.SERVER_BUSY, "device thermal state CRITICAL; try later")
        }

        val tPre = System.nanoTime()
        inspector.inspect(reference)
        val targetInfo = inspector.inspect(target)
        val preMs = msSince(tPre)

        val (result, infMs) = gate.run {
            val ti = System.nanoTime()
            val r = backend.transfer(reference, target, TransferOptions(preserve))
            r to msSince(ti)
        }

        val tEnc = System.nanoTime()
        val out = inspector.toPng(result.imageBytes)
        val outInfo = inspector.inspect(out)
        if (preserve && (outInfo.width != targetInfo.width || outInfo.height != targetInfo.height)) {
            throw ServiceException(
                ErrorCode.INFERENCE_FAILED,
                "output ${outInfo.width}x${outInfo.height} != target ${targetInfo.width}x${targetInfo.height}",
            )
        }
        val encMs = msSince(tEnc)
        val totalMs = msSince(t0)

        val h = backend.health()
        val refSha = Hashing.sha256Hex(reference)
        val tgtSha = Hashing.sha256Hex(target)
        val outSha = Hashing.sha256Hex(out)

        status.completed.incrementAndGet()
        status.lastInferenceMs = infMs
        status.lastRequest = "POST /transfer ok id=$requestId ${totalMs}ms"
        DiagLog.log(
            "I",
            "transfer $requestId ok backend=${h.backend}/${h.provider} " +
                "${outInfo.width}x${outInfo.height} pre=${preMs}ms inf=${infMs}ms enc=${encMs}ms total=${totalMs}ms",
        )

        val accelerated = h.accelerated
        return if (wantsPng) {
            HttpResponse(
                200, "image/png", out,
                mapOf(
                    "X-Request-Id" to requestId,
                    "X-Reference-Sha256" to refSha,
                    "X-Target-Sha256" to tgtSha,
                    "X-Output-Sha256" to outSha,
                    "X-Backend" to h.backend,
                    "X-Provider" to h.provider,
                    "X-Accelerated" to accelerated.toString(),
                    "X-Identity-Applied" to h.identityApplied.toString(),
                    "X-Width" to outInfo.width.toString(),
                    "X-Height" to outInfo.height.toString(),
                    "X-Total-Ms" to totalMs.toString(),
                ),
            )
        } else {
            val timings = JSONObject()
                .put("preprocess", preMs).put("inference", infMs)
                .put("encode", encMs).put("total", totalMs)
            json(
                200,
                JSONObject()
                    .put("request_id", requestId)
                    .put("width", outInfo.width)
                    .put("height", outInfo.height)
                    .put("backend", h.backend)
                    .put("provider", h.provider)
                    .put("accelerated", accelerated)
                    .put("identity_applied", h.identityApplied)
                    .put("model", h.modelId)
                    .put(
                        "sha256",
                        JSONObject().put("reference", refSha).put("target", tgtSha).put("output", outSha),
                    )
                    .put("timings_ms", timings)
                    .put("image_base64", Base64.getEncoder().encodeToString(out)),
            )
        }
    }

    private fun decodeImage(body: JSONObject, key: String, missing: ErrorCode): ByteArray {
        val s = body.optString(key, "")
        if (s.isEmpty()) throw ServiceException(missing, "$key is required")
        val data = if (s.startsWith("data:")) s.substringAfter(',') else s
        val bytes = try {
            Base64.getMimeDecoder().decode(data)
        } catch (e: IllegalArgumentException) {
            throw ServiceException(ErrorCode.INVALID_IMAGE, "$key is not valid base64")
        }
        if (bytes.isEmpty()) throw ServiceException(ErrorCode.INVALID_IMAGE, "$key decoded to zero bytes")
        return bytes
    }

    private fun msSince(nanoStart: Long) = (System.nanoTime() - nanoStart) / 1_000_000

    private fun json(status: Int, o: JSONObject, headers: Map<String, String> = emptyMap()) =
        HttpResponse(status, "application/json", o.toString().toByteArray(Charsets.UTF_8), headers)
}
