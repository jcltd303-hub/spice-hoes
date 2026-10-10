package com.spicehoes.identity.voice

import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

class OfflineVoiceBackend(
    private val platform: SpeechPlatform,
    private val dispatcher: VoiceDispatcher,
    private val cacheDir: File,
    private val initializationTimeoutMs: Long = 15_000,
    private val ttsTimeoutMs: Long = 60_000,
) : VoiceBackend {
    private val closed = AtomicBoolean(false)
    private val initializationStarted = AtomicBoolean(false)
    private val operations = VoiceOperations(dispatcher)
    @Volatile private var catalog: VoiceCatalog? = null
    @Volatile private var ttsReason: String? = "Offline TTS is initializing; wait for /voice/health to report tts_ready."

    /** Called on a startup worker. Its timeout does not prevent identity/HTTP readiness. */
    fun initialize() {
        if (closed.get() || !initializationStarted.compareAndSet(false, true)) return
        try {
            val result = operations.run<VoiceCatalog>("initialize", initializationTimeoutMs, platform::initialize)
            if (closed.get()) return
            val offline = result.voices.filter { !it.networkRequired && !it.requiresDownload }
            catalog = result.copy(voices = offline)
            ttsReason = if (offline.isEmpty()) "No installed offline TTS voice is available; install voice data in Android text-to-speech settings, then restart the companion." else null
        } catch (e: Exception) {
            ttsReason = "Offline TTS initialization failed: ${e.message}. Check Android TTS settings and restart the companion."
        }
    }

    override fun health(): VoiceHealth {
        val running = !closed.get()
        val ready = running && catalog?.voices?.isNotEmpty() == true
        return VoiceHealth(ready, if (running) ttsReason else "Voice service is stopped.", platform.recognitionState(), running)
    }

    override fun voices(): List<OfflineVoice> = requireTts().voices.map { OfflineVoice(it.id, it.name, it.language) }

    override fun synthesize(options: SpeechOptions): ByteArray {
        val selected = selectVoice(options)
        val output = File.createTempFile("speech-", ".wav", cacheDir)
        try {
            operations.run<Unit>("synthesize", ttsTimeoutMs) { done ->
                requireTts()
                platform.startTts(selected, output, done)
            }
            if (output.length() !in 44..(8 * 1024 * 1024).toLong()) {
                throw ServiceException(ErrorCode.VOICE_FAILED, "TTS output is empty or exceeds the 8 MiB WAV limit")
            }
            val wav = output.readBytes()
            if (!isWav(wav)) throw ServiceException(ErrorCode.VOICE_FAILED, "TTS engine did not produce a valid WAV file")
            return wav
        } finally { output.delete() }
    }

    override fun speak(options: SpeechOptions) {
        val selected = selectVoice(options)
        operations.run<Unit>("speak", ttsTimeoutMs) { done ->
            requireTts()
            platform.startTts(selected, null, done)
        }
    }

    override fun listen(options: ListenOptions): String {
        requireRunning()
        platform.recognitionState().requireAvailable()
        if (!options.timeoutSeconds.isFinite() || options.timeoutSeconds !in 1.0..30.0) {
            throw ServiceException(ErrorCode.INVALID_REQUEST, "timeout_seconds must be between 1 and 30")
        }
        val text = operations.run<String>("listen", (options.timeoutSeconds * 1000).toLong()) { done ->
            requireRunning()
            // Recheck on the main thread: the UI/permission may change after HTTP admission.
            platform.recognitionState().requireAvailable()
            platform.startListening(options, done)
        }.trim()
        if (text.isEmpty()) throw ServiceException(ErrorCode.VOICE_FAILED, "No speech was recognized; try again while the activity is visible")
        return text
    }

    fun onForegroundChanged() {
        val state = platform.recognitionState()
        if (!state.available) {
            val error = try { state.requireAvailable(); null } catch (e: ServiceException) { e }
            if (error != null) operations.cancelActive("listen", error)
        }
    }

    private fun requireRunning() {
        if (closed.get()) throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Voice service is stopped")
    }

    private fun requireTts(): VoiceCatalog {
        requireRunning()
        return catalog?.takeIf { it.voices.isNotEmpty() }
            ?: throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, ttsReason ?: "Offline TTS is unavailable")
    }

    private fun selectVoice(options: SpeechOptions): SpeechOptions {
        val catalog = requireTts()
        if (options.text.isBlank() || options.text.length > minOf(4000, catalog.maxTextLength) ||
            !options.pitch.isFinite() || options.pitch !in 0.5f..2f || !options.pace.isFinite() || options.pace !in 0.5f..2f) {
            throw ServiceException(ErrorCode.INVALID_REQUEST, "Invalid speech text, pitch or pace")
        }
        fun matches(voice: PlatformVoice): Boolean {
            val tag = options.language ?: return true
            return voice.language.equals(tag, true) ||
                (!tag.contains('-') && Locale.forLanguageTag(voice.language).language.equals(tag, true))
        }
        val candidates = catalog.voices.filter { matches(it) }
        val selected = if (options.voiceId != null) candidates.find { it.id == options.voiceId }
        else candidates.find { it.id == catalog.defaultVoiceId } ?: candidates.firstOrNull()
        if (selected == null) throw ServiceException(ErrorCode.VOICE_UNAVAILABLE,
            "Requested voice/language is not installed for offline TTS; select an entry from /voice/voices or install its offline voice data.")
        return options.copy(voiceId = selected.id, language = selected.language)
    }

    private fun isWav(bytes: ByteArray): Boolean {
        fun tag(offset: Int) = String(bytes, offset, 4, Charsets.US_ASCII)
        val data = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        if (bytes.size < 44 || tag(0) != "RIFF" || tag(8) != "WAVE" ||
            (data.getInt(4).toLong() and 0xffffffffL) + 8 != bytes.size.toLong()) return false
        var offset = 12
        var hasFormat = false
        var hasAudio = false
        while (offset + 8 <= bytes.size) {
            val length = data.getInt(offset + 4).toLong() and 0xffffffffL
            if (offset + 8L + length > bytes.size) return false
            when (tag(offset)) {
                "fmt " -> {
                    if (length < 16 || data.getShort(offset + 10) <= 0 || data.getInt(offset + 12) <= 0) return false
                    hasFormat = true
                }
                "data" -> hasAudio = length > 0
            }
            val next = offset + 8L + length + (length % 2)
            if (next > bytes.size) return false
            offset = next.toInt()
        }
        return hasFormat && hasAudio && offset == bytes.size
    }

    override fun close() {
        if (closed.compareAndSet(false, true)) {
            operations.close()
            dispatcher.post { platform.close() }
        }
    }
}
