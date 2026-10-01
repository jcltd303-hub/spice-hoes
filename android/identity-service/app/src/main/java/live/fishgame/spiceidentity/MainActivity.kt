package live.fishgame.spiceidentity

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import java.net.Socket
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        status = TextView(this).apply {
            text = "SPICE IDENTITY\n\nSTARTING…\n\nBuild: diagnostic-v2"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.rgb(20, 20, 20))
            textSize = 24f
            gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64)
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(20, 20, 20))
            addView(status, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT))
        })
        launchServiceAndProbe()
    }

    override fun onResume() {
        super.onResume()
        launchServiceAndProbe()
    }

    private fun launchServiceAndProbe() {
        try {
            startService(Intent(this, IdentityService::class.java))
        } catch (e: Exception) {
            status.text = "SPICE IDENTITY\n\nSERVICE START FAILED\n\n${e.javaClass.simpleName}: ${e.message}\n\nBuild: diagnostic-v2"
            return
        }
        thread(name = "spice-ui-probe") {
            Thread.sleep(500)
            val message = try {
                Socket("127.0.0.1", 8082).use { "SPICE IDENTITY\n\nSERVICE READY\n\n127.0.0.1:8082\n\nBuild: diagnostic-v2" }
            } catch (e: Exception) {
                "SPICE IDENTITY\n\nSERVICE NOT LISTENING\n\n${e.javaClass.simpleName}: ${e.message}\n\nBuild: diagnostic-v2"
            }
            runOnUiThread { status.text = message }
        }
    }
}
