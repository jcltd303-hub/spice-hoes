package com.spicehoes.identity

import android.content.Context
import android.os.Build
import android.os.PowerManager
import com.spicehoes.identity.api.ApiRouter
import com.spicehoes.identity.backend.IdentityBackend
import com.spicehoes.identity.backend.MockIdentityBackend
import com.spicehoes.identity.http.MiniHttpServer
import com.spicehoes.identity.image.AndroidImageInspector
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Owns the process-wide service lifecycle. Startup sequence (spec section 6):
 * bind HTTP first so /health answers immediately, then load the backend off the UI thread.
 */
object SpiceRuntime {
    val status = ServiceStatus()
    val meta: BuildMeta by lazy {
        BuildMeta(
            version = BuildConfig.VERSION_NAME,
            apiVersion = BuildConfig.API_VERSION,
            buildId = BuildConfig.BUILD_ID,
            commit = BuildConfig.GIT_SHA,
            host = Config.HOST,
            port = Config.PORT,
        )
    }

    private val started = AtomicBoolean(false)
    private var appCtx: Context? = null
    @Volatile private var server: MiniHttpServer? = null
    @Volatile private var backend: IdentityBackend? = null

    fun start(ctx: Context) {
        if (!started.compareAndSet(false, true)) return
        appCtx = ctx.applicationContext
        thread(name = "spice-startup") { boot() }
    }

    fun stop() {
        server?.stop()
        server = null
        backend?.close()
        backend = null
        status.setState(ServiceState.STOPPED)
        started.set(false)
    }

    private fun boot() {
        val be: IdentityBackend = MockIdentityBackend()
        backend = be
        val router = ApiRouter(status, be, AndroidImageInspector(), meta, ::thermalState)
        try {
            status.setState(ServiceState.HTTP_STARTING)
            val s = MiniHttpServer(
                Config.HOST, Config.PORT, Config.MAX_BODY_BYTES,
                router::handle, router::errorResponse,
            )
            s.start()
            server = s
            status.setState(ServiceState.HTTP_READY)

            be.initialize { status.setState(it) }
            status.setState(ServiceState.SELF_TEST)
            be.selfTest()
            status.setState(ServiceState.READY)
        } catch (t: Throwable) {
            status.lastError = t.toString()
            DiagLog.log("E", "startup failed: $t")
            status.setState(ServiceState.ERROR)
        }
    }

    fun backendSummary(): String = try {
        backend?.health()?.let { "${it.backend}/${it.provider} model=${it.modelId}" } ?: "none"
    } catch (_: Throwable) {
        "unknown"
    }

    /** NORMAL / WARM / HOT / CRITICAL (spec section 21). */
    fun thermalState(): String {
        if (Build.VERSION.SDK_INT < 29) return "NORMAL"
        val pm = appCtx?.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return "NORMAL"
        return when (pm.currentThermalStatus) {
            PowerManager.THERMAL_STATUS_NONE, PowerManager.THERMAL_STATUS_LIGHT -> "NORMAL"
            PowerManager.THERMAL_STATUS_MODERATE -> "WARM"
            PowerManager.THERMAL_STATUS_SEVERE -> "HOT"
            else -> "CRITICAL"
        }
    }

    /** Diagnostics text for the UI (spec section 25). */
    fun statusText(): String {
        val h = try { backend?.health() } catch (_: Throwable) { null }
        val s = status
        return buildString {
            appendLine("Spice Identity v${meta.version}  build #${meta.buildId}  commit ${meta.commit}")
            appendLine("API version: ${meta.apiVersion}")
            appendLine()
            appendLine("STATE: ${s.state}")
            appendLine("Endpoint: http://${meta.host}:${meta.port}")
            appendLine("HTTP server: ${if (server != null) "listening" else "not listening"}")
            appendLine("Backend: ${h?.backend ?: "-"}   Provider: ${h?.provider ?: "-"}")
            appendLine("Model: ${h?.modelId ?: "-"}   SHA-256: ${h?.modelSha256 ?: "-"}")
            appendLine("Accelerated: ${(h?.accelerated ?: false) && s.state == ServiceState.READY}")
            appendLine("Identity applied: ${h?.identityApplied ?: false}")
            appendLine("Thermal: ${thermalState()}")
            appendLine()
            appendLine("Last request: ${s.lastRequest ?: "-"}")
            appendLine("Last inference: ${if (s.lastInferenceMs >= 0) "${s.lastInferenceMs} ms" else "-"}")
            appendLine("Last error: ${s.lastError ?: "-"}")
            append("Requests completed: ${s.completed.get()}   failed: ${s.failed.get()}")
        }
    }
}
