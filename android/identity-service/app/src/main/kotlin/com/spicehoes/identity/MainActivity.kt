package com.spicehoes.identity

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PersistableBundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.spicehoes.identity.voice.AndroidVoicePairing

/** Native status UI. Renders immediately; never blank (spec section 6). */
class MainActivity : Activity() {
    private lateinit var statusView: TextView
    private lateinit var logView: TextView
    private lateinit var crashView: TextView
    private lateinit var crashDismiss: Button
    private lateinit var microphoneButton: Button
    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            refresh()
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        refresh()

        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        startForegroundService(Intent(this, IdentityService::class.java))
    }

    override fun onResume() {
        super.onResume()
        SpiceRuntime.setActivityVisible(true)
        handler.post(tick)
    }

    override fun onPause() {
        SpiceRuntime.setActivityVisible(false)
        handler.removeCallbacks(tick)
        super.onPause()
    }

    private fun buildUi() {
        val pad = (12 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }

        crashView = TextView(this).apply {
            setTextColor(Color.RED)
            typeface = Typeface.MONOSPACE
            textSize = 11f
            visibility = View.GONE
        }
        crashDismiss = Button(this).apply {
            text = "Dismiss crash report"
            visibility = View.GONE
            setOnClickListener {
                CrashReporter.clear(this@MainActivity)
                refresh()
            }
        }
        statusView = mono(13f)
        logView = mono(10f)

        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        buttons.addView(button("Copy status") { copy("status", SpiceRuntime.statusText()) })
        buttons.addView(button("Copy log") { copy("log", DiagLog.tail(200)) })
        buttons.addView(button("Restart") {
            SpiceRuntime.stop()
            SpiceRuntime.start(applicationContext)
        })

        root.addView(crashView)
        root.addView(crashDismiss)
        root.addView(statusView)
        root.addView(buttons)
        root.addView(TextView(this).apply {
            text = "Offline voice: microphone access is optional and used only for /voice/listen. Keep this screen visible/resumed (split-screen with Termux works). Hiding it cancels listening."
        })
        root.addView(button("Copy voice pairing command") { copyVoicePairingCommand() })
        microphoneButton = button("Grant microphone access") {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MICROPHONE_REQUEST)
        }
        root.addView(microphoneButton)
        root.addView(TextView(this).apply { text = "--- log (tail) ---" })
        root.addView(logView)

        setContentView(ScrollView(this).apply {
            fitsSystemWindows = true
            addView(root)
        })
    }

    private fun mono(size: Float) = TextView(this).apply {
        typeface = Typeface.MONOSPACE
        textSize = size
        setTextIsSelectable(true)
    }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { onClick() }
    }

    private fun copy(label: String, text: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText(label, text))
        Toast.makeText(this, "Copied $label", Toast.LENGTH_SHORT).show()
    }

    private fun copyVoicePairingCommand() {
        try {
            val clip = ClipData.newPlainText("Spice voice pairing command", AndroidVoicePairing.command(applicationContext))
            if (Build.VERSION.SDK_INT >= 33) {
                clip.description.extras = PersistableBundle().apply { putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true) }
            }
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, "Voice pairing command copied. Paste into Termux.", Toast.LENGTH_SHORT).show()
        } catch (_: Exception) {
            Toast.makeText(this, "Could not save or copy the voice pairing command. Check app storage and restart.", Toast.LENGTH_LONG).show()
        }
    }

    private fun refresh() {
        val granted = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        microphoneButton.isEnabled = !granted
        microphoneButton.text = if (granted) "Microphone access granted" else "Grant microphone access"
        statusView.text = SpiceRuntime.statusText()
        logView.text = DiagLog.tail(30)
        val crash = CrashReporter.previous(this)
        if (crash != null) {
            crashView.text = "PREVIOUS CRASH:\n$crash"
            crashView.visibility = View.VISIBLE
            crashDismiss.visibility = View.VISIBLE
        } else {
            crashView.visibility = View.GONE
            crashDismiss.visibility = View.GONE
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == MICROPHONE_REQUEST) {
            SpiceRuntime.onVoicePrerequisitesChanged()
            if (grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
                Toast.makeText(this, "Microphone access denied. You can allow it in Android Settings → Apps → Spice Identity → Permissions.", Toast.LENGTH_LONG).show()
            }
            refresh()
        }
    }

    private companion object { const val MICROPHONE_REQUEST = 2 }
}
