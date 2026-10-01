package com.spicehoes.identity

import com.spicehoes.identity.api.ApiRouter
import com.spicehoes.identity.backend.MockIdentityBackend
import com.spicehoes.identity.http.HttpRequest
import com.spicehoes.identity.http.HttpResponse
import com.spicehoes.identity.image.ImageInfo
import com.spicehoes.identity.image.ImageInspector
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.util.Base64
import java.util.concurrent.CountDownLatch
import kotlin.concurrent.thread

private class FakeInspector : ImageInspector {
    override fun inspect(bytes: ByteArray): ImageInfo {
        if (bytes.isEmpty() || bytes[0] == 'X'.code.toByte()) {
            throw ServiceException(ErrorCode.INVALID_IMAGE, "bad")
        }
        return ImageInfo(bytes.size, 2, "image/png")
    }

    override fun toPng(bytes: ByteArray) = bytes
}

class ApiRouterTest {
    private val meta = BuildMeta("0.2.0", 1, "test", "abc", "127.0.0.1", 8082)
    private fun b64(s: String) = Base64.getEncoder().encodeToString(s.toByteArray())

    private fun router(ready: Boolean = true): ApiRouter {
        val status = ServiceStatus()
        if (ready) status.setState(ServiceState.READY)
        return ApiRouter(status, MockIdentityBackend(), FakeInspector(), meta)
    }

    private fun post(body: JSONObject, accept: String? = null) = HttpRequest(
        "POST", "/transfer",
        if (accept != null) mapOf("accept" to accept) else emptyMap(),
        body.toString().toByteArray(),
    )

    private fun valid() = JSONObject()
        .put("reference_image", b64("reference"))
        .put("target_image", b64("target-scene"))

    private fun HttpResponse.json() = JSONObject(String(body))
    private fun HttpResponse.errorCode() = json().getJSONObject("error").getString("code")

    @Test fun healthWhileStartingIsNotReady() {
        val r = router(ready = false).handle(HttpRequest("GET", "/health", emptyMap(), ByteArray(0)))
        assertEquals(200, r.status)
        assertFalse(r.json().getBoolean("ready"))
        assertEquals("STARTING", r.json().getString("state"))
    }

    @Test fun healthReadyIsHonestAboutMock() {
        val j = router().handle(HttpRequest("GET", "/health", emptyMap(), ByteArray(0))).json()
        assertTrue(j.getBoolean("ready"))
        assertEquals("mock", j.getString("backend"))
        assertFalse(j.getBoolean("accelerated"))
        assertFalse(j.getBoolean("identity_applied"))
        assertEquals("spice-identity", j.getString("service"))
        assertEquals(1, j.getInt("api_version"))
    }

    @Test fun missingReference() {
        val r = router().handle(post(JSONObject().put("target_image", b64("t"))))
        assertEquals("REFERENCE_REQUIRED", r.errorCode())
    }

    @Test fun missingTarget() {
        val r = router().handle(post(JSONObject().put("reference_image", b64("r"))))
        assertEquals("TARGET_REQUIRED", r.errorCode())
    }

    @Test fun notReady() {
        val r = router(ready = false).handle(post(valid()))
        assertEquals(503, r.status)
        assertEquals("MODEL_NOT_READY", r.errorCode())
    }

    @Test fun invalidImage() {
        val body = JSONObject().put("reference_image", b64("Xjunk")).put("target_image", b64("t"))
        assertEquals("INVALID_IMAGE", router().handle(post(body)).errorCode())
    }

    @Test fun malformedJson() {
        val r = router().handle(HttpRequest("POST", "/transfer", emptyMap(), "nope".toByteArray()))
        assertEquals("INVALID_REQUEST", r.errorCode())
    }

    @Test fun unknownPath() {
        val r = router().handle(HttpRequest("GET", "/nope", emptyMap(), ByteArray(0)))
        assertEquals(404, r.status)
    }

    @Test fun transferJsonPassthrough() {
        val router = router()
        val r = router.handle(post(valid()))
        assertEquals(200, r.status)
        val j = r.json()
        assertEquals(b64("target-scene"), j.getString("image_base64"))
        assertFalse(j.getBoolean("identity_applied"))
        assertEquals(64, j.getJSONObject("sha256").getString("output").length)
        assertEquals(
            j.getJSONObject("sha256").getString("target"),
            j.getJSONObject("sha256").getString("output"),
        )
    }

    @Test fun transferRawPng() {
        val r = router().handle(post(valid(), accept = "image/png"))
        assertEquals(200, r.status)
        assertEquals("image/png", r.contentType)
        assertEquals("target-scene", String(r.body))
        assertTrue(r.headers.containsKey("X-Output-Sha256"))
    }

    @Test fun gateRejectsWhenQueueFull() {
        val gate = InferenceGate(maxWaiting = 0, waitMs = 10)
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val t = thread { gate.run { started.countDown(); release.await() } }
        started.await()
        try {
            gate.run { }
            fail("expected SERVER_BUSY")
        } catch (e: ServiceException) {
            assertEquals(ErrorCode.SERVER_BUSY, e.code)
        }
        release.countDown()
        t.join()
    }
}
