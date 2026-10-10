package com.spicehoes.identity

import com.spicehoes.identity.voice.VoiceDispatcher
import com.spicehoes.identity.voice.VoiceOperations
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

internal class TestVoiceDispatcher : VoiceDispatcher, AutoCloseable {
    @Volatile private var main: Thread? = null
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "test-voice-main").apply { isDaemon = true; main = this }
    }
    override fun isMainThread() = Thread.currentThread() === main
    override fun post(block: () -> Unit): Boolean {
        executor.execute(block)
        return true
    }
    override fun close() { executor.shutdownNow() }
}

class VoiceOperationsTest {
    private fun expectCode(code: ErrorCode, block: () -> Unit) {
        try { block(); fail("expected $code") }
        catch (e: ServiceException) { assertEquals(code, e.code) }
    }

    @Test fun startsOnMainAndAcceptsCallbacksFromAnotherThread() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val result = ops.run<String>("tts", 1000) { complete ->
                assertTrue(main.isMainThread())
                thread { complete(Result.success("done")) };
                {}
            }
            assertEquals("done", result)
            ops.close()
        }
    }

    @Test fun timeoutCancelsOnMainAndLateCallbackCannotCompleteNextRequest() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val cancelled = CountDownLatch(1)
            var late: ((Result<String>) -> Unit)? = null
            expectCode(ErrorCode.VOICE_TIMEOUT) {
                ops.run<String>("listen", 40) { complete ->
                    late = complete
                    val cancel: () -> Unit = { assertTrue(main.isMainThread()); cancelled.countDown() }
                    cancel
                }
            }
            assertTrue(cancelled.await(1, TimeUnit.SECONDS))
            late!!(Result.success("stale"))
            assertEquals("fresh", ops.run<String>("listen", 1000) { done ->
                done(Result.success("fresh")); {}
            })
            ops.close()
        }
    }

    @Test fun timedOutQueuedStartNeverOpensMicrophoneLater() {
        val queue = LinkedBlockingQueue<() -> Unit>()
        val dispatcher = object : VoiceDispatcher {
            override fun isMainThread() = false
            override fun post(block: () -> Unit): Boolean { queue.add(block); return true }
        }
        val ops = VoiceOperations(dispatcher)
        var started = false
        expectCode(ErrorCode.VOICE_TIMEOUT) {
            ops.run<String>("listen", 20) { started = true; {} }
        }
        while (queue.isNotEmpty()) queue.remove().invoke()
        assertFalse(started)
        ops.close()
    }

    @Test fun concurrentSpeechIsRejectedWithoutBuildingAnUnboundedQueue() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val started = CountDownLatch(1)
            lateinit var complete: (Result<String>) -> Unit
            val result = CompletableFuture<String>()
            val worker = thread {
                result.complete(ops.run("tts", 1000) { callback -> complete = callback; started.countDown(); {} })
            }
            assertTrue(started.await(1, TimeUnit.SECONDS))
            expectCode(ErrorCode.SERVER_BUSY) { ops.run<Unit>("listen", 50) { {} } }
            complete(Result.success("first"))
            assertEquals("first", result.get(1, TimeUnit.SECONDS))
            worker.join(1000)
            ops.close()
        }
    }

    @Test fun closingAbortsActiveWaitAndPreventsNewStarts() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val started = CountDownLatch(1)
            val cancelled = CountDownLatch(1)
            val result = CompletableFuture<ErrorCode>()
            val worker = thread {
                try { ops.run<Unit>("listen", 10_000) { started.countDown(); { cancelled.countDown() } } }
                catch (e: ServiceException) { result.complete(e.code) }
            }
            assertTrue(started.await(1, TimeUnit.SECONDS))
            ops.close()
            assertEquals(ErrorCode.VOICE_UNAVAILABLE, result.get(1, TimeUnit.SECONDS))
            assertTrue(cancelled.await(1, TimeUnit.SECONDS))
            expectCode(ErrorCode.VOICE_UNAVAILABLE) { ops.run<Unit>("tts", 50) { {} } }
            worker.join(1000)
        }
    }

    @Test fun blockingMainThreadIsRejectedBeforeStarting() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val result = CompletableFuture<ErrorCode>()
            main.post {
                try { ops.run<Unit>("tts", 50) { fail("must not start"); {} } }
                catch (e: ServiceException) { result.complete(e.code) }
            }
            assertEquals(ErrorCode.SERVER_BUSY, result.get(1, TimeUnit.SECONDS))
            ops.close()
        }
    }

    @Test fun interruptionCancelsAndPreservesInterruptFlag() {
        TestVoiceDispatcher().use { main ->
            val ops = VoiceOperations(main)
            val started = CountDownLatch(1)
            val cancelled = CountDownLatch(1)
            val interrupted = CompletableFuture<Boolean>()
            val worker = thread {
                try { ops.run<Unit>("tts", 10_000) { started.countDown(); { cancelled.countDown() } } }
                catch (_: ServiceException) { interrupted.complete(Thread.currentThread().isInterrupted) }
            }
            assertTrue(started.await(1, TimeUnit.SECONDS))
            worker.interrupt()
            assertTrue(interrupted.get(1, TimeUnit.SECONDS))
            assertTrue(cancelled.await(1, TimeUnit.SECONDS))
            worker.join(1000)
            ops.close()
        }
    }

    @Test fun rejectedDispatchFailsQuicklyAndDoesNotReserveTheSlotForever() {
        val ops = VoiceOperations(object : VoiceDispatcher {
            override fun isMainThread() = false
            override fun post(block: () -> Unit) = false
        })
        repeat(2) { expectCode(ErrorCode.VOICE_UNAVAILABLE) { ops.run<Unit>("tts", 1000) { {} } } }
        ops.close()
    }

    @Test fun throwingDispatcherCannotStrandTheActiveWaitDuringShutdown() {
        val queue = LinkedBlockingQueue<() -> Unit>()
        val failDispatch = java.util.concurrent.atomic.AtomicBoolean(false)
        val dispatcher = object : VoiceDispatcher {
            override fun isMainThread() = false
            override fun post(block: () -> Unit): Boolean {
                if (failDispatch.get()) throw java.util.concurrent.RejectedExecutionException("dispatcher shut down")
                queue.add(block)
                return true
            }
        }
        val ops = VoiceOperations(dispatcher)
        val result = CompletableFuture<ErrorCode>()
        val worker = thread {
            try { ops.run<Unit>("tts", 10_000) { {} } }
            catch (e: ServiceException) { result.complete(e.code) }
        }
        queue.poll(1, TimeUnit.SECONDS)!!.invoke()
        failDispatch.set(true)
        try {
            ops.close()
            assertEquals(ErrorCode.VOICE_UNAVAILABLE, result.get(1, TimeUnit.SECONDS))
        } finally { worker.interrupt(); worker.join(1000) }
    }
}
