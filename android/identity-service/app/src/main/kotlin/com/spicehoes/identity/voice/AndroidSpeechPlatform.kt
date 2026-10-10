package com.spicehoes.identity.voice

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.io.File
import java.util.Locale
import java.util.UUID

class AndroidVoiceDispatcher(private val handler: Handler = Handler(Looper.getMainLooper())) : VoiceDispatcher {
    override fun isMainThread() = Looper.myLooper() == handler.looper
    override fun post(block: () -> Unit) = handler.post { block() }
}

/** Uses only installed embedded voices and the API 31+ on-device recognizer factory. */
class AndroidSpeechPlatform(
    context: Context,
    private val activityVisible: () -> Boolean,
    private val handler: Handler = Handler(Looper.getMainLooper()),
) : SpeechPlatform {
    private val context = context.applicationContext
    private var tts: TextToSpeech? = null
    private var initializationToken: Any? = null
    private var closed = false
    private data class Utterance(val id: String, val complete: (Result<Unit>) -> Unit)
    private var utterance: Utterance? = null
    private var recognizer: SpeechRecognizer? = null
    private var recognitionComplete: ((Result<String>) -> Unit)? = null

    private fun requireMain() = check(Looper.myLooper() == handler.looper) { "Speech APIs require the main thread" }
    private fun requireOpen() {
        if (closed) throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Android speech backend is closed")
    }

    override fun initialize(complete: (Result<VoiceCatalog>) -> Unit): () -> Unit {
        requireMain()
        requireOpen()
        val token = Any()
        initializationToken = token
        // Always post: even a synchronous onInit cannot run before tts is assigned.
        val candidate = TextToSpeech(context) { status -> handler.post {
            if (closed || initializationToken !== token) return@post
            initializationToken = null
            val engine = tts ?: return@post
            try {
                if (status != TextToSpeech.SUCCESS) throw ServiceException(ErrorCode.VOICE_UNAVAILABLE,
                    "Android TTS engine failed to initialize; enable an offline TTS engine and install its voice data")
                if (engine.setOnUtteranceProgressListener(progressListener) != TextToSpeech.SUCCESS) {
                    throw ServiceException(ErrorCode.VOICE_FAILED, "TTS engine could not register completion callbacks")
                }
                val voices = (engine.voices ?: emptySet()).sortedBy { it.name }.map {
                    PlatformVoice(it.name, it.name, it.locale.toLanguageTag(), it.isNetworkConnectionRequired,
                        it.features?.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) == true)
                }
                complete(Result.success(VoiceCatalog(voices, engine.defaultVoice?.name, TextToSpeech.getMaxSpeechInputLength())))
            } catch (e: Exception) {
                runCatching { engine.shutdown() }
                tts = null
                complete(Result.failure(e))
            }
        } }
        tts = candidate
        return {
            requireMain()
            // A timeout may win after onInit posts its result but before it reaches the waiter.
            if (tts === candidate) {
                initializationToken = null
                tts = null
                runCatching { candidate.shutdown() }
            }
        }
    }

    override fun recognitionState(): RecognitionState {
        // Availability and permission queries do not create or start a recognizer.
        var reason: String? = null
        val available = if (Build.VERSION.SDK_INT >= 31) {
            try { SpeechRecognizer.isOnDeviceRecognitionAvailable(context) }
            catch (_: Exception) { reason = "Could not query the Android on-device recognition service."; false }
        } else false
        return RecognitionState(Build.VERSION.SDK_INT, available,
            context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED,
            activityVisible(), reason)
    }

    override fun startTts(options: SpeechOptions, output: File?, complete: (Result<Unit>) -> Unit): () -> Unit {
        requireMain()
        requireOpen()
        val engine = tts ?: throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Offline TTS has not initialized")
        val voice = engine.voices?.firstOrNull { it.name == options.voiceId }
            ?: throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Requested offline voice is no longer installed; restart the companion")
        if (voice.isNetworkConnectionRequired || voice.features?.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) == true) {
            throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Requested voice requires network access or missing voice data")
        }
        if (engine.setVoice(voice) != TextToSpeech.SUCCESS || engine.setPitch(options.pitch) != TextToSpeech.SUCCESS ||
            engine.setSpeechRate(options.pace) != TextToSpeech.SUCCESS) {
            throw ServiceException(ErrorCode.VOICE_FAILED, "TTS engine rejected the offline voice, pitch or pace")
        }
        val selected = engine.voice
        if (selected == null || selected.name != voice.name || selected.isNetworkConnectionRequired) {
            throw ServiceException(ErrorCode.VOICE_UNAVAILABLE, "TTS engine did not select the requested embedded voice")
        }
        val op = Utterance(UUID.randomUUID().toString(), complete)
        utterance = op
        val result = try {
            if (output != null) engine.synthesizeToFile(options.text, Bundle(), output, op.id)
            else engine.speak(options.text, TextToSpeech.QUEUE_FLUSH, Bundle(), op.id)
        } catch (e: Exception) {
            utterance = null
            runCatching { engine.stop() }
            output?.delete()
            throw e
        }
        if (result != TextToSpeech.SUCCESS) {
            utterance = null
            runCatching { engine.stop() }
            throw ServiceException(ErrorCode.VOICE_FAILED, "TTS engine rejected the speech request")
        }
        return {
            requireMain()
            if (utterance === op) {
                utterance = null
                runCatching { engine.stop() }
            }
            output?.delete()
        }
    }

    private val progressListener = object : UtteranceProgressListener() {
        override fun onStart(utteranceId: String?) = Unit
        override fun onDone(utteranceId: String?) { finishTts(utteranceId, Result.success(Unit)) }
        @Deprecated("Android legacy callback")
        override fun onError(utteranceId: String?) {
            finishTts(utteranceId, Result.failure(ServiceException(ErrorCode.VOICE_FAILED, "Offline TTS failed")))
        }
        override fun onError(utteranceId: String?, errorCode: Int) {
            val code = if (errorCode == TextToSpeech.ERROR_NOT_INSTALLED_YET) ErrorCode.VOICE_UNAVAILABLE else ErrorCode.VOICE_FAILED
            finishTts(utteranceId, Result.failure(ServiceException(code, "Offline TTS failed (Android error $errorCode); check installed voice data")))
        }
        override fun onStop(utteranceId: String?, interrupted: Boolean) {
            finishTts(utteranceId, Result.failure(ServiceException(ErrorCode.VOICE_FAILED, "Offline TTS was stopped")))
        }
    }

    private fun finishTts(id: String?, result: Result<Unit>) {
        handler.post {
            val op = utterance
            if (op != null && op.id == id) {
                utterance = null
                if (result.isFailure) runCatching { tts?.stop() }
                op.complete(result)
            }
        }
    }

    override fun startListening(options: ListenOptions, complete: (Result<String>) -> Unit): () -> Unit {
        requireMain()
        requireOpen()
        recognitionState().requireAvailable()
        if (Build.VERSION.SDK_INT < 31) throw ServiceException(ErrorCode.RECOGNITION_UNAVAILABLE, "On-device recognition requires API 31")
        // EXTRA_PREFER_OFFLINE alone is not a guarantee. Never call createSpeechRecognizer.
        val instance = try { SpeechRecognizer.createOnDeviceSpeechRecognizer(context) }
        catch (_: UnsupportedOperationException) {
            throw ServiceException(ErrorCode.RECOGNITION_UNAVAILABLE, "Android on-device recognizer became unavailable; enable its service and install offline language data")
        }
        recognizer = instance
        recognitionComplete = complete
        fun finish(result: Result<String>) {
            requireMain()
            if (recognizer !== instance) return
            val callback = recognitionComplete
            recognitionComplete = null
            recognizer = null
            runCatching { instance.destroy() }
            callback?.invoke(result)
        }
        try {
            instance.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) = Unit
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit
                override fun onPartialResults(partialResults: Bundle?) = Unit
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
                override fun onResults(results: Bundle?) {
                    val state = recognitionState()
                    if (!state.available) {
                        try { state.requireAvailable() } catch (e: ServiceException) { finish(Result.failure(e)) }
                        return
                    }
                    val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim()
                    if (text.isNullOrEmpty()) finish(Result.failure(ServiceException(ErrorCode.VOICE_FAILED, "No speech was recognized")))
                    else finish(Result.success(text))
                }
                override fun onError(error: Int) { finish(Result.failure(recognitionError(error))) }
            })
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, options.language ?: Locale.getDefault().toLanguageTag())
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            instance.startListening(intent)
        } catch (e: Exception) {
            recognitionComplete = null
            recognizer = null
            runCatching { instance.destroy() }
            throw if (e is SecurityException) ServiceException(ErrorCode.MICROPHONE_PERMISSION_REQUIRED, "Microphone permission was revoked; grant RECORD_AUDIO in the visible app") else e
        }
        return {
            requireMain()
            if (recognizer === instance) {
                recognitionComplete = null
                recognizer = null
                runCatching { instance.cancel() }
                runCatching { instance.destroy() }
            }
        }
    }

    private fun recognitionError(error: Int): ServiceException = when (error) {
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> ServiceException(ErrorCode.MICROPHONE_PERMISSION_REQUIRED, "Grant microphone access in the visible Spice Identity app")
        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
            ServiceException(ErrorCode.RECOGNITION_UNAVAILABLE, "Requested language has no installed on-device recognition model; install it in Android speech settings")
        SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
            ServiceException(ErrorCode.RECOGNITION_UNAVAILABLE, "On-device recognizer reported a network error; cloud fallback is disabled")
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY, SpeechRecognizer.ERROR_TOO_MANY_REQUESTS ->
            ServiceException(ErrorCode.SERVER_BUSY, "Android on-device recognizer is busy; retry shortly")
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> ServiceException(ErrorCode.VOICE_TIMEOUT, "No speech heard before the Android recognizer timed out")
        SpeechRecognizer.ERROR_NO_MATCH -> ServiceException(ErrorCode.VOICE_FAILED, "No speech matched; try again in the visible app")
        else -> ServiceException(ErrorCode.VOICE_FAILED, "On-device recognition failed (Android error $error)")
    }

    override fun close() {
        requireMain()
        if (closed) return
        closed = true
        initializationToken = null
        val engine = tts
        tts = null
        val activeTts = utterance
        utterance = null
        val activeRecognizer = recognizer
        recognizer = null
        val callback = recognitionComplete
        recognitionComplete = null
        val error = ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Android speech backend shut down")
        runCatching { engine?.stop() }
        runCatching { engine?.shutdown() }
        runCatching { activeRecognizer?.cancel() }
        runCatching { activeRecognizer?.destroy() }
        activeTts?.complete?.invoke(Result.failure(error))
        callback?.invoke(Result.failure(error))
    }
}
