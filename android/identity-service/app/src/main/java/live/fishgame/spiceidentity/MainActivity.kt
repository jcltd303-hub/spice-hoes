package live.fishgame.spiceidentity

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView
import java.net.InetAddress
import java.net.ServerSocket
import kotlin.concurrent.thread

class MainActivity : Activity() {
    @Volatile private var running = true
    private var server: ServerSocket? = null
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        status = TextView(this).apply {
            text = "SPICE IDENTITY\n\nSTARTING 8082…\n\nBuild: activity-server-v1"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.BLACK)
            textSize = 24f
            gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64)
        }
        setContentView(status)
        startHttpServer()
    }

    private fun startHttpServer() {
        thread(name = "spice-identity-http") {
            try {
                val socket = ServerSocket(8082, 8, InetAddress.getByName("127.0.0.1"))
                server = socket
                runOnUiThread {
                    status.text = "SPICE IDENTITY\n\nREADY\n\n127.0.0.1:8082\n\nBuild: activity-server-v1"
                }
                socket.use { s ->
                    while (running) {
                        val client = s.accept()
                        client.use { conn ->
                            val input = conn.getInputStream().bufferedReader()
                            val request = input.readLine() ?: ""
                            while (true) {
                                val header = input.readLine()
                                if (header.isNullOrEmpty()) break
                            }
                            val healthy = request.startsWith("GET /health ")
                            val body = if (healthy) """{"ready":true,"backend":"activity-server","accelerated":false,"port":8082}""" else """{"error":"transfer backend not loaded"}"""
                            val code = if (healthy) "200 OK" else "503 Service Unavailable"
                            val bytes = body.toByteArray()
                            val out = conn.getOutputStream()
                            out.write(("HTTP/1.1 $code\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n").toByteArray())
                            out.write(bytes)
                            out.flush()
                        }
                    }
                }
            } catch (e: Throwable) {
                runOnUiThread {
                    status.text = "SPICE IDENTITY\n\nSERVER FAILED\n\n${e.javaClass.simpleName}\n${e.message ?: "(no message)"}\n\nBuild: activity-server-v1"
                }
            }
        }
    }

    override fun onDestroy() {
        running = false
        try { server?.close() } catch (_: Throwable) {}
        super.onDestroy()
    }
}
