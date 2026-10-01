package com.spicehoes.identity

import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Small rotating app-private log (spec section 25). */
object DiagLog {
    private const val MAX_BYTES = 256 * 1024L
    private var file: File? = null
    private val fmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    @Synchronized
    fun init(dir: File) {
        dir.mkdirs()
        file = File(dir, "spice.log")
    }

    @Synchronized
    fun log(level: String, msg: String) {
        val line = "${fmt.format(Date())} $level $msg"
        Log.i("SpiceIdentity", line)
        val f = file ?: return
        try {
            if (f.length() > MAX_BYTES) {
                val old = File(f.parentFile, "spice.log.1")
                old.delete()
                f.renameTo(old)
            }
            f.appendText(line + "\n")
        } catch (_: Exception) {
            // Logging must never take the service down.
        }
    }

    @Synchronized
    fun tail(maxLines: Int = 40): String {
        val f = file
        if (f == null || !f.exists()) return "(no log)"
        return try {
            f.readLines().takeLast(maxLines).joinToString("\n")
        } catch (e: Exception) {
            "(log unreadable: $e)"
        }
    }
}
