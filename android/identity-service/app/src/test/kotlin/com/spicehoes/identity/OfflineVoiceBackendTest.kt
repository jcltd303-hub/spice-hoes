package com.spicehoes.identity

import com.spicehoes.identity.voice.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

private class TestSpeechPlatform(private val main: TestVoiceDispatcher) : SpeechPlatform {
    @Volatile var state = RecognitionState(35, true, true, true)
    var catalog = VoiceCatalog(listOf(
        PlatformVoice("offline-en", "English offline", "en-US", false, false),
        PlatformVoice("offline-es", "Spanish offline", "es-ES", false, false),
        PlatformVoice("network", "Network only", "en-US", true, false),
        PlatformVoice("download", "Missing data", "en-US", false, true),
    ), "network", 4000)
    var initializeResult: Result<VoiceCatalog>? = Result.success(catalog)
    @Volatile var initializationCallback: ((Result<VoiceCatalog>) -> Unit)? = null
    val initializationDispatched = CountDownLatch(1)
    var ttsRequest: SpeechOptions? = null
    @Volatile var listenCallback: ((Result<String>) -> Unit)? = null
    var outputBytes = byteArrayOf(
        82,73,70,70,38,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,
        1,0,1,0,-128,62,0,0,0,125,0,0,2,0,16,0,100,97,116,97,2,0,0,0,0,0,
    )
    @Volatile var listening = false
    val listenStarted = CountDownLatch(1)
    var recognitionProbe: (() -> RecognitionState)? = null
    val cancelled = CountDownLatch(1)
    val closed = CountDownLatch(1)
    override fun initialize(complete: (Result<VoiceCatalog>) -> Unit): () -> Unit {
        assertTrue(main.isMainThread())
        initializationCallback = complete
        initializationDispatched.countDown()
        initializeResult?.let(complete)
        return { cancelled.countDown() }
    }
    override fun recognitionState() = recognitionProbe?.invoke() ?: state
    override fun startTts(options: SpeechOptions, output: File?, complete: (Result<Unit>) -> Unit): () -> Unit {
        assertTrue(main.isMainThread())
        ttsRequest = options
        output?.writeBytes(outputBytes)
        complete(Result.success(Unit))
        return { cancelled.countDown() }
    }
    override fun startListening(options: ListenOptions, complete: (Result<String>) -> Unit): () -> Unit {
        assertTrue(main.isMainThread())
        listening = true
        listenCallback = complete
        listenStarted.countDown()
        return { listening = false; cancelled.countDown() }
    }
    override fun close() { assertTrue(main.isMainThread()); closed.countDown() }
}

class OfflineVoiceBackendTest {
    private fun fixture(initializationTimeoutMs: Long = 1000, block: (OfflineVoiceBackend, TestSpeechPlatform, File) -> Unit) {
        val dir = Files.createTempDirectory("voice-test-").toFile()
        TestVoiceDispatcher().use { main ->
            val platform = TestSpeechPlatform(main)
            val backend = OfflineVoiceBackend(platform, main, dir, initializationTimeoutMs, ttsTimeoutMs = 1000)
            try { block(backend, platform, dir) }
            finally {
                backend.close()
                assertTrue(platform.closed.await(1, TimeUnit.SECONDS))
                dir.deleteRecursively()
            }
        }
    }

    private fun expectCode(code: ErrorCode, block: () -> Unit) {
        try { block(); fail("expected $code") }
        catch (e: ServiceException) { assertEquals(code, e.code) }
    }

    @Test fun initializationFiltersNetworkAndUninstalledVoices() = fixture { backend, _, _ ->
        assertFalse(backend.health().ttsReady)
        backend.initialize()
        assertTrue(backend.health().ttsReady)
        assertEquals(listOf("offline-en", "offline-es"), backend.voices().map { it.id })
    }

    @Test fun synthesisSelectsOfflineVoiceAndDeletesTemporaryWav() = fixture { backend, platform, dir ->
        backend.initialize()
        val wav = backend.synthesize(SpeechOptions("hola", language = "es-ES", pitch = 1.2f, pace = 0.8f))
        assertArrayEquals(platform.outputBytes, wav)
        assertEquals(SpeechOptions("hola", "offline-es", "es-ES", 1.2f, 0.8f), platform.ttsRequest)
        assertEquals(0, dir.listFiles()!!.size)
    }

    @Test fun defaultNetworkVoiceNeverLeaksIntoOfflinePlayback() = fixture { backend, platform, _ ->
        backend.initialize()
        backend.speak(SpeechOptions("hello"))
        assertEquals("offline-en", platform.ttsRequest!!.voiceId)
        backend.speak(SpeechOptions("hello again", voiceId = "offline-en"))
        assertEquals(1f, platform.ttsRequest!!.pitch)
        assertEquals(1f, platform.ttsRequest!!.pace)
    }

    @Test fun unsupportedVoiceOrLanguageNeverFallsBackToNetwork() = fixture { backend, platform, _ ->
        backend.initialize()
        for (options in listOf(
            SpeechOptions("hello", voiceId = "network"), SpeechOptions("hello", voiceId = "download"),
            SpeechOptions("bonjour", language = "fr-FR"),
            SpeechOptions("hola", voiceId = "offline-en", language = "es-ES"),
        )) expectCode(ErrorCode.VOICE_UNAVAILABLE) { backend.speak(options) }
        assertNull(platform.ttsRequest)
    }

    @Test fun malformedAudioIsNotAdvertisedAsWavAndIsDeleted() = fixture { backend, platform, dir ->
        backend.initialize()
        platform.outputBytes = "this is not a WAV".toByteArray()
        expectCode(ErrorCode.VOICE_FAILED) { backend.synthesize(SpeechOptions("hello")) }
        assertEquals(0, dir.listFiles()!!.size)
    }

    @Test fun initializationTimeoutIgnoresLateSuccess() = fixture(40) { backend, platform, _ ->
        platform.initializeResult = null
        backend.initialize()
        assertFalse(backend.health().ttsReady)
        assertTrue(backend.health().ttsReason!!.contains("timed out", ignoreCase = true))
        assertTrue(platform.cancelled.await(1, TimeUnit.SECONDS))
        platform.initializationCallback!!(Result.success(platform.catalog))
        assertFalse(backend.health().ttsReady)
    }

    @Test fun missingOfflineVoiceDoesNotDisableAvailableRecognition() = fixture { backend, platform, _ ->
        platform.initializeResult = Result.success(VoiceCatalog(platform.catalog.voices.filter { it.networkRequired }, "network", 4000))
        backend.initialize()
        assertFalse(backend.health().ttsReady)
        assertTrue(backend.health().recognitionAvailable)
        assertTrue(backend.health().ttsReason!!.contains("offline", ignoreCase = true))
    }

    @Test fun listenRequiresApi31ServicePermissionAndVisibleActivity() = fixture { backend, platform, _ ->
        backend.initialize()
        val cases = listOf(
            RecognitionState(30, true, true, true) to ErrorCode.RECOGNITION_UNAVAILABLE,
            RecognitionState(35, false, true, true) to ErrorCode.RECOGNITION_UNAVAILABLE,
            RecognitionState(35, true, false, true) to ErrorCode.MICROPHONE_PERMISSION_REQUIRED,
            RecognitionState(35, true, true, false) to ErrorCode.ACTIVITY_NOT_VISIBLE,
        )
        for ((state, error) in cases) {
            platform.state = state
            assertFalse(backend.health().recognitionAvailable)
            expectCode(error) { backend.listen(ListenOptions()) }
        }
        assertFalse(platform.listening)
    }

    @Test fun hidingActivityAbortsActiveMicrophoneCapture() = fixture { backend, platform, _ ->
        backend.initialize()
        val result = CompletableFuture<ErrorCode>()
        val worker = thread {
            try {
                backend.listen(ListenOptions(timeoutSeconds = 10.0))
                result.completeExceptionally(AssertionError("listening should be aborted"))
            } catch (e: ServiceException) { result.complete(e.code) }
        }
        assertTrue(platform.listenStarted.await(1, TimeUnit.SECONDS))
        assertNotNull(platform.listenCallback)
        platform.state = platform.state.copy(activityVisible = false)
        backend.onForegroundChanged()
        assertEquals(ErrorCode.ACTIVITY_NOT_VISIBLE, result.get(1, TimeUnit.SECONDS))
        assertTrue(platform.cancelled.await(1, TimeUnit.SECONDS))
        assertFalse(platform.listening)
        worker.join(1000)
    }

    @Test fun successfulRecognitionIsReturnedWithoutRequiringTts() = fixture { backend, platform, _ ->
        platform.initializeResult = Result.failure(IllegalStateException("no TTS engine"))
        backend.initialize()
        val result = CompletableFuture<String>()
        val worker = thread { result.complete(backend.listen(ListenOptions("en-US", 1.0))) }
        assertTrue(platform.listenStarted.await(1, TimeUnit.SECONDS))
        assertNotNull(platform.listenCallback)
        platform.listenCallback!!(Result.success("hello offline"))
        assertEquals("hello offline", result.get(1, TimeUnit.SECONDS))
        worker.join(1000)
    }

    @Test fun shutdownBeforeInitializationCannotResurrectVoiceReadiness() = fixture { backend, platform, _ ->
        backend.close()
        backend.initialize()
        assertFalse(backend.health().ready)
        assertFalse(backend.health().running)
        assertNull(platform.initializationCallback)
        expectCode(ErrorCode.VOICE_UNAVAILABLE) { backend.speak(SpeechOptions("hello")) }
    }

    @Test fun permissionRevokedBetweenAdmissionAndMainStartDoesNotOpenMicrophone() = fixture { backend, platform, _ ->
        backend.initialize()
        val probes = java.util.concurrent.atomic.AtomicInteger()
        platform.recognitionProbe = { platform.state.copy(microphoneGranted = probes.incrementAndGet() == 1) }
        expectCode(ErrorCode.MICROPHONE_PERMISSION_REQUIRED) { backend.listen(ListenOptions()) }
        assertFalse(platform.listening)
        assertNull(platform.listenCallback)
    }

    @Test fun shutdownDuringInitializationUnblocksItAndIgnoresLateCallback() = fixture { backend, platform, _ ->
        platform.initializeResult = null
        val finished = CompletableFuture<Unit>()
        val worker = thread { backend.initialize(); finished.complete(Unit) }
        assertTrue(platform.initializationDispatched.await(1, TimeUnit.SECONDS))
        assertNotNull(platform.initializationCallback)
        backend.close()
        finished.get(1, TimeUnit.SECONDS)
        platform.initializationCallback!!(Result.success(platform.catalog))
        assertFalse(backend.health().ready)
        assertFalse(backend.health().running)
        worker.join(1000)
    }

    @Test fun truncatedOrHeaderOnlyWavNeverReturnsSuccessfulAudio() = fixture { backend, platform, dir ->
        backend.initialize()
        val good = platform.outputBytes.copyOf()
        for (bytes in listOf(
            good.copyOf().apply { this[0] = 0 },
            good.copyOf().apply { this[40] = 100 },
            good.copyOf().apply { this[22] = 0 },
            good.copyOf(44).apply { this[4] = 36; this[40] = 0 },
        )) {
            platform.outputBytes = bytes
            expectCode(ErrorCode.VOICE_FAILED) { backend.synthesize(SpeechOptions("hello")) }
            assertEquals(0, dir.listFiles()!!.size)
        }
    }
}
