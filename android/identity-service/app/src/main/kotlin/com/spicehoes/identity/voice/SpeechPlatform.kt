package com.spicehoes.identity.voice

import java.io.File

interface VoiceDispatcher {
    fun isMainThread(): Boolean
    fun post(block: () -> Unit): Boolean
}

data class PlatformVoice(
    val id: String,
    val name: String,
    val language: String,
    val networkRequired: Boolean,
    val requiresDownload: Boolean,
)

data class VoiceCatalog(val voices: List<PlatformVoice>, val defaultVoiceId: String?, val maxTextLength: Int)

/** All resource-changing methods and their cancellation actions run on the dispatcher. */
interface SpeechPlatform : AutoCloseable {
    fun initialize(complete: (Result<VoiceCatalog>) -> Unit): () -> Unit
    fun recognitionState(): RecognitionState
    fun startTts(options: SpeechOptions, output: File?, complete: (Result<Unit>) -> Unit): () -> Unit
    fun startListening(options: ListenOptions, complete: (Result<String>) -> Unit): () -> Unit
    override fun close()
}
