package com.spicehoes.identity

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

/** Native status UI. Renders immediately; never blank (spec section 6). */
class MainActivity : Activity() {
    private lateinit var statusView: TextView
    private lateinit var logView: TextView
    private lateinit var crashView: TextView
    private lateinit var crashDismiss: Button
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
        handler.post(tick)
    }

    override fun onPause() {
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

    private fun refresh() {
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
}
