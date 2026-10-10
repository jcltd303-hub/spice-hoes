package com.spicehoes.identity.http

import com.spicehoes.identity.DiagLog
import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.io.BufferedInputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors
import kotlin.concurrent.thread

class HttpRequest(
    val method: String,
    val path: String,
    /** Header names lower-cased. */
    val headers: Map<String, String>,
    val body: ByteArray,
)

class HttpResponse(
    val status: Int,
    val contentType: String,
    val body: ByteArray,
    val headers: Map<String, String> = emptyMap(),
)

/**
 * Minimal HTTP/1.1 server, bound to a single (loopback) address. Requests need
 * Content-Length (no chunked), one request per connection.
 */
class MiniHttpServer(
    private val host: String,
    private val port: Int,
    private val maxBody: Int,
    private val handler: (HttpRequest) -> HttpResponse,
    private val onError: (Throwable) -> HttpResponse,
) {
    private var serverSocket: ServerSocket? = null
    private val pool = Executors.newFixedThreadPool(4)
    @Volatile private var running = false

    val boundPort: Int get() = serverSocket?.localPort ?: -1

    fun start() {
        val ss = ServerSocket()
        ss.reuseAddress = true
        ss.bind(InetSocketAddress(InetAddress.getByName(host), port), 16)
        serverSocket = ss
        running = true
        thread(name = "spice-http-accept", isDaemon = true) { acceptLoop(ss) }
        DiagLog.log("I", "HTTP listening on $host:${ss.localPort}")
    }

    fun stop() {
        running = false
        try {
            serverSocket?.close()
        } catch (_: IOException) {
        }
        pool.shutdownNow()
    }

    private fun acceptLoop(ss: ServerSocket) {
        while (running && !ss.isClosed) {
            val sock = try {
                ss.accept()
            } catch (e: IOException) {
                if (running) DiagLog.log("W", "accept failed: $e")
                continue
            }
            try {
                pool.execute { serve(sock) }
            } catch (e: Exception) {
                sock.close()
            }
        }
    }

    private fun serve(sock: Socket) {
        sock.use { s ->
            try {
                // Defense in depth on top of the loopback bind.
                if (!s.inetAddress.isLoopbackAddress) return
                s.soTimeout = 30_000
                val input = BufferedInputStream(s.getInputStream())
                val out = s.getOutputStream()
                val response = try {
                    handler(readRequest(input, out))
                } catch (t: Throwable) {
                    onError(t)
                }
                write(out, response)
                drain(s, input)
            } catch (e: IOException) {
                DiagLog.log("W", "connection error: $e")
            }
        }
    }

    private fun readRequest(input: InputStream, out: OutputStream): HttpRequest {
        val requestLine = readLine(input) ?: throw bad("empty request")
        val parts = requestLine.split(" ")
        if (parts.size < 3) throw bad("malformed request line")
        val method = parts[0].uppercase()
        val path = parts[1].substringBefore('?')

        val headers = HashMap<String, String>()
        while (true) {
            val line = readLine(input) ?: throw bad("truncated headers")
            if (line.isEmpty()) break
            val i = line.indexOf(':')
            if (i > 0) headers[line.substring(0, i).trim().lowercase()] = line.substring(i + 1).trim()
            if (headers.size > 64) throw bad("too many headers")
        }

        if (headers["transfer-encoding"]?.contains("chunked", ignoreCase = true) == true) {
            throw ServiceException(ErrorCode.INVALID_REQUEST, "chunked bodies unsupported; send Content-Length", 411)
        }
        val len = headers["content-length"]?.toLongOrNull() ?: 0L
        if (len < 0) throw bad("bad Content-Length")
        if (len > maxBody) {
            throw ServiceException(ErrorCode.IMAGE_TOO_LARGE, "request body exceeds $maxBody bytes")
        }
        if (len > 0 && headers["expect"]?.contains("100-continue", ignoreCase = true) == true) {
            out.write("HTTP/1.1 100 Continue\r\n\r\n".toByteArray())
            out.flush()
        }

        val body = ByteArray(len.toInt())
        var off = 0
        while (off < body.size) {
            val n = input.read(body, off, body.size - off)
            if (n < 0) throw bad("truncated body")
            off += n
        }
        return HttpRequest(method, path, headers, body)
    }

    private fun readLine(input: InputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val b = input.read()
            if (b < 0) return if (sb.isEmpty()) null else sb.toString()
            if (b == '\n'.code) break
            if (b != '\r'.code) sb.append(b.toChar())
            if (sb.length > 8192) throw bad("header line too long")
        }
        return sb.toString()
    }

    private fun bad(msg: String) = ServiceException(ErrorCode.INVALID_REQUEST, msg)

    private fun write(out: OutputStream, r: HttpResponse) {
        val head = StringBuilder()
            .append("HTTP/1.1 ${r.status} ${reason(r.status)}\r\n")
            .append("Content-Type: ${r.contentType}\r\n")
            .append("Content-Length: ${r.body.size}\r\n")
            .append("Connection: close\r\n")
        r.headers.forEach { (k, v) -> head.append("$k: $v\r\n") }
        head.append("\r\n")
        out.write(head.toString().toByteArray(Charsets.ISO_8859_1))
        out.write(r.body)
        out.flush()
    }

    /** Avoid a TCP reset clobbering the response when we rejected an unread body. */
    private fun drain(s: Socket, input: InputStream) {
        try {
            s.shutdownOutput()
            s.soTimeout = 500
            val buf = ByteArray(8192)
            var total = 0
            while (total < 4_000_000) {
                val n = input.read(buf)
                if (n <= 0) break
                total += n
            }
        } catch (_: IOException) {
        }
    }

    private fun reason(status: Int) = when (status) {
        200 -> "OK"
        400 -> "Bad Request"
        401 -> "Unauthorized"
        403 -> "Forbidden"
        404 -> "Not Found"
        405 -> "Method Not Allowed"
        409 -> "Conflict"
        411 -> "Length Required"
        413 -> "Payload Too Large"
        415 -> "Unsupported Media Type"
        422 -> "Unprocessable Entity"
        503 -> "Service Unavailable"
        504 -> "Gateway Timeout"
        507 -> "Insufficient Storage"
        else -> if (status >= 500) "Internal Server Error" else "OK"
    }
}
