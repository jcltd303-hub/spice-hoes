package live.fishgame.spiceidentity

import android.app.Service
import android.content.Intent
import android.os.IBinder
import java.net.InetAddress
import java.net.ServerSocket
import kotlin.concurrent.thread

class IdentityService : Service() {
    @Volatile private var running = true
    private var server: ServerSocket? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        thread(name = "spice-identity-http") {
            try {
                ServerSocket(8082, 8, InetAddress.getByName("127.0.0.1")).also { server = it }.use { socket ->
                    while (running) {
                        val client = socket.accept()
                        client.use { conn ->
                            val input = conn.getInputStream().bufferedReader()
                            val request = input.readLine() ?: ""
                            while (true) {
                                val header = input.readLine()
                                if (header.isNullOrEmpty()) break
                            }
                            val healthy = request.startsWith("GET /health ")
                            val body = if (healthy) """{"ready":true,"backend":"service-shell","accelerated":false,"port":8082}""" else """{"error":"transfer backend not loaded"}"""
                            val status = if (healthy) "200 OK" else "503 Service Unavailable"
                            val bytes = body.toByteArray()
                            conn.getOutputStream().write(("HTTP/1.1 $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n").toByteArray())
                            conn.getOutputStream().write(bytes)
                            conn.getOutputStream().flush()
                        }
                    }
                }
            } catch (_: Exception) {
                if (running) stopSelf()
            }
        }
    }

    override fun onDestroy() {
        running = false
        try { server?.close() } catch (_: Exception) {}
        super.onDestroy()
    }
}
