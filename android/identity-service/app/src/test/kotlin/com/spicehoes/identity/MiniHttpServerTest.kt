package com.spicehoes.identity

import com.spicehoes.identity.http.HttpResponse
import com.spicehoes.identity.http.MiniHttpServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertArrayEquals
import org.junit.Before
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class MiniHttpServerTest {
    private lateinit var server: MiniHttpServer

    @Before fun setUp() {
        server = MiniHttpServer(
            "127.0.0.1", 0, 1024,
            { req -> HttpResponse(200, "text/plain", "${req.method} ${req.path}:".toByteArray() + req.body) },
            { e -> HttpResponse((e as? ServiceException)?.httpStatus ?: 500, "text/plain", (e.message ?: "").toByteArray()) },
        )
        server.start()
    }

    @After fun tearDown() = server.stop()

    private fun url(path: String) = URL("http://127.0.0.1:${server.boundPort}$path")

    @Test fun getRoundTrip() {
        val c = url("/health?x=1").openConnection() as HttpURLConnection
        assertEquals(200, c.responseCode)
        assertEquals("GET /health:", String(c.inputStream.readBytes()))
    }

    @Test fun postBodyRoundTrip() {
        val payload = ByteArray(500) { (it % 251).toByte() }
        val c = url("/transfer").openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.doOutput = true
        c.setFixedLengthStreamingMode(payload.size)
        c.outputStream.use { it.write(payload) }
        assertEquals(200, c.responseCode)
        assertArrayEquals("POST /transfer:".toByteArray() + payload, c.inputStream.readBytes())
    }
}
