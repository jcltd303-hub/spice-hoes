package com.spicehoes.identity

import java.security.MessageDigest
import java.util.concurrent.Semaphore
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

object Config {
    /** Loopback only. Must never default to 0.0.0.0 (spec section 5). */
    const val HOST = "127.0.0.1"
    const val PORT = 8082
    const val MAX_BODY_BYTES = 64 * 1024 * 1024
    const val MAX_IMAGE_DIM = 4096
}

/** Startup state machine (spec section 7). */
enum class ServiceState {
    STARTING, HTTP_STARTING, HTTP_READY, RUNTIME_LOADING, MODEL_LOADING,
    ACCELERATOR_INITIALIZING, SELF_TEST, READY, DEGRADED, ERROR, STOPPED
}

/** Machine-readable error contract (spec section 10). */
enum class ErrorCode(val http: Int) {
    INVALID_REQUEST(400),
    UNAUTHORIZED(401),
    UNSUPPORTED_MEDIA_TYPE(415),
    INVALID_IMAGE(400),
    IMAGE_TOO_LARGE(413),
    REFERENCE_REQUIRED(400),
    TARGET_REQUIRED(400),
    MODEL_NOT_READY(503),
    MODEL_LOAD_FAILED(500),
    NO_FACE_DETECTED(422),
    MULTIPLE_FACES(422),
    INFERENCE_FAILED(500),
    ACCELERATOR_FAILED(500),
    OUT_OF_MEMORY(507),
    SERVER_BUSY(503),
    VOICE_UNAVAILABLE(503),
    RECOGNITION_UNAVAILABLE(503),
    MICROPHONE_PERMISSION_REQUIRED(403),
    ACTIVITY_NOT_VISIBLE(409),
    VOICE_TIMEOUT(504),
    VOICE_FAILED(500),
    INTERNAL_ERROR(500),
}

class ServiceException(
    val code: ErrorCode,
    message: String,
    val httpStatus: Int = code.http,
) : Exception(message) {
    var requestId: String? = null
}

data class BuildMeta(
    val version: String,
    val apiVersion: Int,
    val buildId: String,
    val commit: String,
    val host: String,
    val port: Int,
)

class ServiceStatus {
    @Volatile var state: ServiceState = ServiceState.STARTING
        private set
    @Volatile var lastError: String? = null
    @Volatile var lastRequest: String? = null
    @Volatile var lastInferenceMs: Long = -1
    val completed = AtomicLong()
    val failed = AtomicLong()

    fun setState(s: ServiceState) {
        state = s
        DiagLog.log("I", "state -> $s")
    }
}

/**
 * One active inference at a time, small bounded queue, otherwise SERVER_BUSY
 * (spec section 20).
 */
class InferenceGate(private val maxWaiting: Int = 2, private val waitMs: Long = 60_000) {
    private val sem = Semaphore(1, true)
    private val waiting = AtomicInteger()

    fun <T> run(block: () -> T): T {
        if (!sem.tryAcquire()) {
            if (waiting.incrementAndGet() > maxWaiting) {
                waiting.decrementAndGet()
                throw ServiceException(ErrorCode.SERVER_BUSY, "inference queue full")
            }
            val got = try {
                sem.tryAcquire(waitMs, TimeUnit.MILLISECONDS)
            } finally {
                waiting.decrementAndGet()
            }
            if (!got) throw ServiceException(ErrorCode.SERVER_BUSY, "timed out waiting for inference slot")
        }
        try {
            return block()
        } finally {
            sem.release()
        }
    }
}

object Hashing {
    fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
