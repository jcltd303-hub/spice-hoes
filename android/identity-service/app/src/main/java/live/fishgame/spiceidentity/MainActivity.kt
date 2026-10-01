package live.fishgame.spiceidentity

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import java.net.Socket
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply {
            text = "Spice Identity\nStarting local service…"
            textSize = 20f
            setPadding(48, 64, 48, 48)
        }
        setContentView(LinearLayout(this).apply { addView(status) })
        startService(Intent(this, IdentityService::class.java))
    }

    override fun onResume() {
        super.onResume()
        startService(Intent(this, IdentityService::class.java))
        thread {
            Thread.sleep(400)
            val message = try {
                Socket("127.0.0.1", 8082).use { "Spice Identity\nService READY\n127.0.0.1:8082" }
            } catch (e: Exception) {
                "Spice Identity\nService NOT LISTENING\n${e.javaClass.simpleName}: ${e.message}"
            }
            runOnUiThread { status.text = message }
        }
    }
}
