package com.spicehoes.identity

import com.spicehoes.identity.api.ApiRouter
import com.spicehoes.identity.backend.MockIdentityBackend
import com.spicehoes.identity.http.HttpRequest
import com.spicehoes.identity.http.MiniHttpServer
import com.spicehoes.identity.image.ImageInfo
import com.spicehoes.identity.image.ImageInspector
import com.spicehoes.identity.voice.*
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertArrayEquals
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64

private class TestVoiceBackend : VoiceBackend {
    var calls = 0
    var snapshot = VoiceHealth(true, null, RecognitionState(35, true, true, true))
    var speechOptions: SpeechOptions? = null
    var listenOptions: ListenOptions? = null
    val wav = byteArrayOf(
        82,73,70,70,38,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,
        1,0,1,0,-128,62,0,0,0,125,0,0,2,0,16,0,100,97,116,97,2,0,0,0,0,0,
    )
    override fun health(): VoiceHealth { calls++; return snapshot }
    override fun voices(): List<OfflineVoice> { calls++; return listOf(OfflineVoice("offline-en", "English", "en-US")) }
    override fun synthesize(options: SpeechOptions): ByteArray { calls++; speechOptions = options; return wav }
    override fun speak(options: SpeechOptions) { calls++; speechOptions = options }
    override fun listen(options: ListenOptions): String { calls++; listenOptions = options; return "hello offline" }
    override fun close() = Unit
}

class VoiceApiRouterTest {
    private val pairingToken = "0123456789abcdef".repeat(4)
    private fun authorizedHeaders(contentType: String? = "application/json"): Map<String, String> =
        mapOf("authorization" to "Bearer $pairingToken") +
            (contentType?.let { mapOf("content-type" to it) } ?: emptyMap())
    private fun router(voice: VoiceBackend = UnavailableVoiceBackend, identityReady: Boolean = true,
        authorizer: VoiceAuthorizer = BearerVoiceAuthorizer { pairingToken }): ApiRouter = ApiRouter(
        ServiceStatus().apply { if (identityReady) setState(ServiceState.READY) },
        MockIdentityBackend(),
        object : ImageInspector {
            override fun inspect(bytes: ByteArray) = ImageInfo(1, 1, "image/png")
            override fun toPng(bytes: ByteArray) = bytes
        },
        BuildMeta("test", 1, "local", "test", "127.0.0.1", 8082),
        voice = voice,
        voiceAuthorizer = authorizer,
    )

    @Test fun unavailableVoiceHealthDoesNotBorrowMockIdentityReadiness() {
        val response = router().handle(HttpRequest("GET", "/voice/health", emptyMap(), byteArrayOf()))
        assertEquals(200, response.status)
        val body = JSONObject(String(response.body))
        assertFalse(body.getBoolean("ready"))
        assertFalse(body.getBoolean("tts_ready"))
        assertFalse(body.getBoolean("recognition_available"))
    }

    @Test fun voiceRoutesRejectWrongMethods() {
        for ((method, path) in listOf(
            "POST" to "/voice/health", "POST" to "/voice/voices",
            "GET" to "/voice/synthesize", "GET" to "/voice/speak", "GET" to "/voice/listen",
        )) {
            val response = router().handle(HttpRequest(method, path, emptyMap(), byteArrayOf()))
            assertEquals(path, 405, response.status)
        }
    }

    @Test fun malformedVoiceRequestIsInvalidEvenWhenBackendUnavailable() {
        val response = router().handle(HttpRequest("POST", "/voice/synthesize", authorizedHeaders(), "bad".toByteArray()))
        assertEquals(400, response.status)
        assertEquals("INVALID_REQUEST", JSONObject(String(response.body)).getJSONObject("error").getString("code"))
    }

    @Test fun invalidSpeechFieldsAreRejectedBeforeReadinessChecks() {
        val invalid = listOf(
            "{}", "{\"text\":\"   \"}", "{\"text\":17}",
            "{\"text\":\"hello\",\"pitch\":0}", "{\"text\":\"hello\",\"pace\":-1}",
            "{\"text\":\"hello\",\"pitch\":\"1.0\"}", "{\"text\":\"hello\",\"pace\":5}",
            "{\"text\":\"hello\",\"voice_id\":3}", "{\"text\":\"hello\",\"language\":\"\"}",
            "{\"text\":\"hello\",\"language\":\"not_a_locale\"}",
            JSONObject().put("text", "a".repeat(4001)).toString(),
            "[]", "null",
        )
        for (path in listOf("/voice/synthesize", "/voice/speak")) {
            for (body in invalid) {
                val response = router().handle(HttpRequest("POST", path, authorizedHeaders(), body.toByteArray()))
                assertEquals("$path: $body", 400, response.status)
            }
        }
    }

    @Test fun invalidListenTimeoutAndLanguageAreRejected() {
        for (body in listOf(
            "{\"timeout_seconds\":0}", "{\"timeout_seconds\":31}",
            "{\"timeout_seconds\":\"10\"}", "{\"language\":4}", "{\"language\":\"bad_tag\"}",
        )) {
            val response = router().handle(HttpRequest("POST", "/voice/listen", authorizedHeaders(), body.toByteArray()))
            assertEquals(body, 400, response.status)
        }
    }

    @Test fun unavailableSpeechReturnsActionableBlocker() {
        val response = router().handle(HttpRequest(
            "POST", "/voice/synthesize", authorizedHeaders(), "{\"text\":\"hello\"}".toByteArray(),
        ))
        assertEquals(503, response.status)
        val error = JSONObject(String(response.body)).getJSONObject("error")
        assertEquals("VOICE_UNAVAILABLE", error.getString("code"))
        assertFalse(error.getString("message").isBlank())
    }

    @Test fun healthyVoiceIsIndependentOfLoadingIdentityAndDoesNotClaimAcceleration() {
        val router = router(TestVoiceBackend(), identityReady = false)
        val voice = JSONObject(String(router.handle(HttpRequest("GET", "/voice/health", emptyMap(), byteArrayOf())).body))
        assertTrue(voice.getBoolean("ready"))
        assertTrue(voice.getBoolean("tts_ready"))
        assertTrue(voice.getBoolean("recognition_available"))
        assertFalse(voice.getBoolean("accelerated"))
        assertEquals(0, voice.getJSONArray("reasons").length())
        val identity = JSONObject(String(router.handle(HttpRequest("GET", "/health", emptyMap(), byteArrayOf())).body))
        assertFalse(identity.getBoolean("ready"))
        assertEquals("mock", identity.getString("backend"))
        assertFalse(identity.getBoolean("identity_applied"))
        assertFalse(identity.getBoolean("accelerated"))
    }

    @Test fun voicesListNamesLanguageAndStableOfflineId() {
        val response = router(TestVoiceBackend()).handle(HttpRequest("GET", "/voice/voices", authorizedHeaders(), byteArrayOf()))
        assertEquals(200, response.status)
        val body = JSONObject(String(response.body))
        val voice = body.getJSONArray("voices").getJSONObject(0)
        assertEquals("offline-en", voice.getString("voice_id"))
        assertEquals("English", voice.getString("name"))
        assertEquals("en-US", voice.getString("language"))
        assertTrue(voice.getBoolean("offline"))
        assertEquals("android-offline", body.getString("provider"))
        assertEquals(0, body.getInt("cost_cents"))
    }

    @Test fun synthesizeAndSpeakPreserveOptionsAndFreeOfflineProvider() {
        for (path in listOf("/voice/synthesize", "/voice/speak")) {
            val backend = TestVoiceBackend()
            val payload = "{\"text\":\"hello\",\"voice_id\":\"offline-en\",\"language\":\"en-US\",\"pitch\":1.2,\"pace\":0.8}"
            val response = router(backend).handle(HttpRequest("POST", path, authorizedHeaders(), payload.toByteArray()))
            assertEquals(200, response.status)
            val body = JSONObject(String(response.body))
            assertEquals("android-offline", body.getString("provider"))
            assertEquals(0, body.getInt("cost_cents"))
            assertEquals(SpeechOptions("hello", "offline-en", "en-US", 1.2f, 0.8f), backend.speechOptions)
            if (path.endsWith("synthesize")) {
                assertEquals("audio/wav", body.getString("mime_type"))
                assertArrayEquals(backend.wav, Base64.getDecoder().decode(body.getString("audio_base64")))
            } else assertTrue(body.getBoolean("spoken"))
        }
    }

    @Test fun listenUsesDefaultOrRequestedBoundedOptions() {
        for ((payload, expected) in listOf("{}" to ListenOptions(), "{\"language\":\"es-ES\",\"timeout_seconds\":2.5}" to ListenOptions("es-ES", 2.5))) {
            val backend = TestVoiceBackend()
            val response = router(backend).handle(HttpRequest("POST", "/voice/listen", authorizedHeaders(), payload.toByteArray()))
            assertEquals(200, response.status)
            val body = JSONObject(String(response.body))
            assertEquals("hello offline", body.getString("text"))
            assertEquals("android-on-device", body.getString("provider"))
            assertEquals(0, body.getInt("cost_cents"))
            assertEquals(expected, backend.listenOptions)
        }
    }

    @Test fun healthAndListenExposeActualRecognitionBlockers() {
        for ((state, code, status) in listOf(
            Triple(RecognitionState(30, true, true, true), "RECOGNITION_UNAVAILABLE", 503),
            Triple(RecognitionState(35, false, true, true), "RECOGNITION_UNAVAILABLE", 503),
            Triple(RecognitionState(35, true, false, true), "MICROPHONE_PERMISSION_REQUIRED", 403),
            Triple(RecognitionState(35, true, true, false), "ACTIVITY_NOT_VISIBLE", 409),
        )) {
            val backend = TestVoiceBackend().apply { snapshot = snapshot.copy(recognition = state) }
            val router = router(backend)
            val health = JSONObject(String(router.handle(HttpRequest("GET", "/voice/health", emptyMap(), byteArrayOf())).body))
            assertTrue(health.getBoolean("tts_ready"))
            assertFalse(health.getBoolean("recognition_available"))
            assertTrue(health.getJSONArray("recognition_reasons").length() > 0)
            val response = router.handle(HttpRequest("POST", "/voice/listen", authorizedHeaders(), "{}".toByteArray()))
            assertEquals(status, response.status)
            assertEquals(code, JSONObject(String(response.body)).getJSONObject("error").getString("code"))
            assertEquals(null, backend.listenOptions)
        }
    }

    @Test fun voiceContractRoundTripsOverLoopbackHttp() {
        val backend = TestVoiceBackend()
        val router = router(backend)
        val server = MiniHttpServer("127.0.0.1", 0, 32 * 1024, router::handle, router::errorResponse)
        server.start()
        try {
            val connection = URL("http://127.0.0.1:${server.boundPort}/voice/synthesize").openConnection() as HttpURLConnection
            connection.connectTimeout = 1000
            connection.readTimeout = 1000
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $pairingToken")
            val payload = "{\"text\":\"hello\"}".toByteArray()
            connection.setFixedLengthStreamingMode(payload.size)
            connection.outputStream.use { it.write(payload) }
            assertEquals(200, connection.responseCode)
            val body = JSONObject(connection.inputStream.use { it.readBytes().toString(Charsets.UTF_8) })
            assertArrayEquals(backend.wav, Base64.getDecoder().decode(body.getString("audio_base64")))
            assertEquals("android-offline", body.getString("provider"))
            connection.disconnect()
        } finally { server.stop() }
    }

    @Test fun unauthenticatedSpeechCannotReachEvenBackendReadinessChecks() {
        for (path in listOf("/voice/listen", "/voice/synthesize", "/voice/speak")) {
            val backend = TestVoiceBackend()
            val response = router(backend).handle(HttpRequest(
                "POST", path, mapOf("content-type" to "application/json"), "{\"text\":\"hello\"}".toByteArray(),
            ))
            assertEquals(path, 0, backend.calls)
            assertEquals(401, response.status)
            assertEquals("UNAUTHORIZED", JSONObject(String(response.body)).getJSONObject("error").getString("code"))
            assertEquals("Bearer realm=\"spice-voice\"", response.headers["WWW-Authenticate"])
            assertFalse(String(response.body).contains(pairingToken))
        }
    }

    @Test fun voiceEnumerationRequiresAuthorization() {
        val backend = TestVoiceBackend()
        val response = router(backend).handle(HttpRequest("GET", "/voice/voices", emptyMap(), byteArrayOf()))
        assertEquals(0, backend.calls)
        assertEquals(401, response.status)
    }

    @Test fun missingMalformedOrIncorrectBearerCannotStartSpeech() {
        for (header in listOf("", "Bearer", "Basic credentials", "Bearer wrong-token", "Bearer " + "f".repeat(64), "Bearer $pairingToken extra")) {
            val backend = TestVoiceBackend()
            val response = router(backend).handle(HttpRequest(
                "POST", "/voice/listen", mapOf("content-type" to "application/json", "authorization" to header), "{}".toByteArray(),
            ))
            assertEquals(0, backend.calls)
            assertEquals(401, response.status)
            assertFalse(String(response.body).contains(pairingToken))
            if (header.length > 7) assertFalse(String(response.body).contains(header))
        }
    }

    @Test fun unauthenticatedHealthAdvertisesPairingWithoutLeakingTokenOrStartingSpeech() {
        val backend = TestVoiceBackend()
        val response = router(backend).handle(HttpRequest("GET", "/voice/health", emptyMap(), byteArrayOf()))
        assertEquals(200, response.status)
        val body = JSONObject(String(response.body))
        assertTrue(body.has("auth_required"))
        assertTrue(body.getBoolean("auth_required"))
        assertFalse(body.has("token"))
        assertFalse(body.has("pairing_token"))
        assertFalse(String(response.body).contains(pairingToken))
        assertEquals(1, backend.calls)
        assertEquals(null, backend.speechOptions)
        assertEquals(null, backend.listenOptions)
    }

    @Test fun authorizedVoicePostsRejectBrowserFormAndNonJsonContentTypesBeforeBackend() {
        for (path in listOf("/voice/listen", "/voice/synthesize", "/voice/speak")) {
            for (contentType in listOf(null, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonp")) {
                val backend = TestVoiceBackend()
                val response = router(backend).handle(HttpRequest(
                    "POST", path, authorizedHeaders(contentType), "{\"text\":\"hello\"}".toByteArray(),
                ))
                assertEquals(0, backend.calls)
                assertEquals(415, response.status)
                assertEquals("UNSUPPORTED_MEDIA_TYPE", JSONObject(String(response.body)).getJSONObject("error").getString("code"))
            }
        }
    }

    @Test fun unauthenticatedMalformedBodyStillFailsAuthorizationBeforeParsing() {
        val backend = TestVoiceBackend()
        val response = router(backend).handle(HttpRequest("POST", "/voice/listen", emptyMap(), "invalid".toByteArray()))
        assertEquals(401, response.status)
        assertEquals(0, backend.calls)
    }
}
