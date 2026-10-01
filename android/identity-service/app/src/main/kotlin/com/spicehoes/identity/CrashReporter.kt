package com.spicehoes.identity

import android.content.Context
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.util.Date

/** Uncaught-exception handler; previous crash is shown on next launch (spec section 26). */
object CrashReporter {
    private const val FILE = "crash_last.txt"

    fun install(ctx: Context) {
        val dir = ctx.filesDir
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                val sw = StringWriter()
                e.printStackTrace(PrintWriter(sw))
                File(dir, FILE).writeText(
                    "time=${Date()}\n" +
                        "thread=${t.name}\n" +
                        "exception=${e.javaClass.name}: ${e.message}\n" +
                        "state=${SpiceRuntime.status.state}\n" +
                        "backend=${SpiceRuntime.backendSummary()}\n\n" +
                        sw.toString()
                )
            } catch (_: Throwable) {
            }
            prev?.uncaughtException(t, e)
        }
    }

    fun previous(ctx: Context): String? =
        File(ctx.filesDir, FILE).takeIf { it.exists() }?.readText()

    fun clear(ctx: Context) {
        File(ctx.filesDir, FILE).delete()
    }
}
