package com.spicehoes.identity.voice

import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutionException
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** One active operation, no waiting queue, and no blocking of Android's callback thread. */
class VoiceOperations(private val dispatcher: VoiceDispatcher) : AutoCloseable {
    private class Call<T>(val kind: String) {
        val result = CompletableFuture<T>()
        val ended = AtomicBoolean(false)
        // Assigned and invoked only on the dispatcher thread.
        var cancel: (() -> Unit)? = null
    }

    private val closed = AtomicBoolean(false)
    private val active = AtomicReference<Call<*>?>(null)

    fun <T> run(kind: String, timeoutMs: Long, start: ((Result<T>) -> Unit) -> (() -> Unit)): T {
        if (closed.get()) throw unavailable()
        if (dispatcher.isMainThread()) throw ServiceException(ErrorCode.SERVER_BUSY, "Voice requests must not block the main thread")
        val call = Call<T>(kind)
        if (!active.compareAndSet(null, call)) throw ServiceException(ErrorCode.SERVER_BUSY, "Another speech operation is active; retry after it completes")
        try {
            if (closed.get()) abort(call, unavailable())
            else if (!dispatch {
                if (!call.ended.get() && !closed.get()) {
                    try {
                        call.cancel = start { result ->
                            if (!call.ended.get() && !dispatch {
                                if (call.ended.compareAndSet(false, true)) {
                                    result.fold(call.result::complete) { call.result.completeExceptionally(failure(it)) }
                                }
                            }) abort(call, unavailable())
                        }
                    } catch (t: Throwable) { abort(call, failure(t)) }
                }
            }) abort(call, unavailable())
            return try {
                call.result.get(timeoutMs, TimeUnit.MILLISECONDS)
            } catch (_: TimeoutException) {
                val error = ServiceException(ErrorCode.VOICE_TIMEOUT, "$kind timed out after ${timeoutMs}ms")
                abort(call, error)
                throw error
            } catch (_: InterruptedException) {
                val error = ServiceException(ErrorCode.VOICE_FAILED, "$kind was interrupted")
                abort(call, error)
                Thread.currentThread().interrupt()
                throw error
            } catch (e: ExecutionException) { throw failure(e.cause ?: e) }
        } finally { active.compareAndSet(call, null) }
    }

    private fun abort(call: Call<*>, error: ServiceException) {
        if (!call.ended.compareAndSet(false, true)) return
        // Enqueue cancellation before waking the HTTP worker, so it precedes the next start.
        dispatch {
            val cancel = call.cancel
            call.cancel = null
            try { cancel?.invoke() } catch (_: Exception) { /* A failed engine cannot strand a waiter. */ }
        }
        call.result.completeExceptionally(error)
    }

    private fun dispatch(block: () -> Unit): Boolean =
        try { dispatcher.post(block) } catch (_: Exception) { false }

    fun cancelActive(kind: String, error: ServiceException) {
        active.get()?.takeIf { it.kind == kind }?.let { abort(it, error) }
    }

    override fun close() {
        if (closed.compareAndSet(false, true)) active.get()?.let { abort(it, unavailable()) }
    }

    private fun unavailable() = ServiceException(ErrorCode.VOICE_UNAVAILABLE, "Voice service is stopped or its main dispatcher is unavailable")
    private fun failure(t: Throwable): ServiceException = when (t) {
        is ServiceException -> t
        is OutOfMemoryError -> ServiceException(ErrorCode.OUT_OF_MEMORY, "Voice operation ran out of memory")
        else -> ServiceException(ErrorCode.VOICE_FAILED, t.message ?: "Voice operation failed")
    }
}
