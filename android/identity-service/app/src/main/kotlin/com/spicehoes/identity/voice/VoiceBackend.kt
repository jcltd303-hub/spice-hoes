package com.spicehoes.identity.voice

import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException

data class OfflineVoice(val id: String, val name: String, val language: String)

data class SpeechOptions(
    val text: String,
    val voiceId: String? = null,
    val language: String? = null,
    val pitch: Float = 1f,
    val pace: Float = 1f,
)

data class ListenOptions(val language: String? = null, val timeoutSeconds: Double = 15.0)

data class RecognitionState(
    val sdkInt: Int,
    val onDeviceAvailable: Boolean,
    val microphoneGranted: Boolean,
    val activityVisible: Boolean,
    val serviceReason: String? = null,
) {
    val reasons: List<String> get() = buildList {
        if (sdkInt < 31) add("On-device recognition requires Android 12 (API 31) or newer.")
        else if (!onDeviceAvailable) add("No on-device recognition service is available; enable one and install its offline language model.")
        if (!microphoneGranted) add("Tap Grant microphone access in Spice Identity to allow RECORD_AUDIO.")
        if (!activityVisible) add("Keep the Spice Identity activity visible/resumed, for example in split-screen with Termux.")
        if (serviceReason != null) add(serviceReason)
    }
    val available: Boolean get() = reasons.isEmpty()

    fun requireAvailable() {
        val code = when {
            !activityVisible -> ErrorCode.ACTIVITY_NOT_VISIBLE
            !microphoneGranted -> ErrorCode.MICROPHONE_PERMISSION_REQUIRED
            else -> ErrorCode.RECOGNITION_UNAVAILABLE
        }
        if (!available) throw ServiceException(code, reasons.joinToString(" "))
    }
}

data class VoiceHealth(
    val ttsReady: Boolean,
    val ttsReason: String?,
    val recognition: RecognitionState,
    val running: Boolean = true,
) {
    val recognitionAvailable: Boolean get() = running && recognition.available
    val ready: Boolean get() = ttsReady || recognitionAvailable
    val recognitionReasons: List<String> get() =
        (if (running) emptyList() else listOf("Voice service is stopped or not initialized.")) + recognition.reasons
}

/** Blocking HTTP-worker boundary; platform implementations must never wait on the main thread. */
interface VoiceBackend : AutoCloseable {
    fun health(): VoiceHealth
    fun voices(): List<OfflineVoice>
    fun synthesize(options: SpeechOptions): ByteArray
    fun speak(options: SpeechOptions)
    fun listen(options: ListenOptions): String
    override fun close()
}

object UnavailableVoiceBackend : VoiceBackend {
    override fun health() = VoiceHealth(
        false, "Voice backend is not initialized; start the Android companion.",
        RecognitionState(0, false, false, false), running = false,
    )
    private fun unavailable(): Nothing = throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, health().ttsReason!!)
    override fun voices(): List<OfflineVoice> = unavailable()
    override fun synthesize(options: SpeechOptions): ByteArray = unavailable()
    override fun speak(options: SpeechOptions): Unit = unavailable()
    override fun listen(options: ListenOptions): String = unavailable()
    override fun close() = Unit
}
