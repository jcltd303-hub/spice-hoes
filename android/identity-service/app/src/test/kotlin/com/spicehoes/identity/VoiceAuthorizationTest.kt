package com.spicehoes.identity

import com.spicehoes.identity.voice.*
import org.junit.Assert.*
import org.junit.Test
import java.security.SecureRandom
import java.util.concurrent.CyclicBarrier
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

private class MemoryVoiceTokenStore(private val slowWrite: Boolean = false) : VoiceTokenStore {
    @Volatile var value: String? = null
    var canWrite = true
    val writes = AtomicInteger()
    override fun read() = value
    override fun write(token: String): Boolean {
        writes.incrementAndGet()
        if (!canWrite) return false
        if (slowWrite) Thread.sleep(5) // Model the filesystem commit at this external boundary.
        value = token
        return true
    }
}

private class FixtureSecureRandom : SecureRandom() {
    override fun nextBytes(bytes: ByteArray) { for (i in bytes.indices) bytes[i] = i.toByte() }
}

class VoiceAuthorizationTest {
    private val fixtureToken = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

    @Test fun generationPersistsAll32RandomBytesAsLowercaseHex() {
        val store = MemoryVoiceTokenStore()
        val pairing = VoicePairing(store, FixtureSecureRandom())
        assertEquals(fixtureToken, pairing.token())
        assertEquals(fixtureToken, store.value)
        assertEquals(1, store.writes.get())
    }

    @Test fun pairingTokenSurvivesNewStoreConsumersAndServiceRestarts() {
        val store = MemoryVoiceTokenStore()
        VoicePairing(store, FixtureSecureRandom()).token()
        val randomMustNotRun = object : SecureRandom() {
            override fun nextBytes(bytes: ByteArray) { fail("must reuse persisted pairing token") }
        }
        val restarted = VoicePairing(store, randomMustNotRun)
        assertEquals(fixtureToken, restarted.token())
        assertEquals("export SPICE_ANDROID_VOICE_TOKEN='$fixtureToken'", restarted.pairingCommand())
        assertEquals(1, store.writes.get())
    }

    @Test fun invalidStoredTokensAreReplacedBeforeAnyAuthorizationCanSucceed() {
        for (value in listOf("", "bad-token", "a".repeat(63), "A".repeat(64))) {
            val store = MemoryVoiceTokenStore().apply { this.value = value }
            assertEquals(fixtureToken, VoicePairing(store, FixtureSecureRandom()).token())
            assertEquals(fixtureToken, store.value)
            assertEquals(1, store.writes.get())
        }
    }

    @Test fun failedPersistenceNeverReturnsAnEphemeralPairingCredential() {
        val store = MemoryVoiceTokenStore().apply { canWrite = false }
        try {
            VoicePairing(store, FixtureSecureRandom()).token()
            fail("must reject a token that could not be persisted")
        } catch (e: ServiceException) {
            assertEquals(ErrorCode.VOICE_UNAVAILABLE, e.code)
            assertFalse(e.message!!.contains(fixtureToken))
        }
        assertNull(store.value)
    }

    @Test fun simultaneousUiAndHttpConsumersShareOnePersistedToken() {
        val store = MemoryVoiceTokenStore(slowWrite = true)
        val barrier = CyclicBarrier(6)
        val pool = Executors.newFixedThreadPool(6)
        try {
            val results = (1..6).map {
                pool.submit<String> { barrier.await(1, TimeUnit.SECONDS); VoicePairing(store, FixtureSecureRandom()).token() }
            }
            results.forEach { assertEquals(fixtureToken, it.get(1, TimeUnit.SECONDS)) }
            assertEquals(1, store.writes.get())
        } finally { pool.shutdownNow() }
    }

    @Test fun exactBearerTokenIsRequiredWhileHttpAuthSchemeIsCaseInsensitive() {
        val authorizer = BearerVoiceAuthorizer { fixtureToken }
        assertTrue(authorizer.isAuthorized("Bearer $fixtureToken"))
        assertTrue(authorizer.isAuthorized("bearer $fixtureToken"))
        for (header in listOf(null, "", fixtureToken, "Basic $fixtureToken", "Bearer", "Bearer  $fixtureToken",
            "Bearer $fixtureToken ", "Bearer " + fixtureToken.dropLast(1), "Bearer " + fixtureToken + "0",
            "Bearer f" + fixtureToken.drop(1), "Bearer " + fixtureToken.dropLast(1) + "0", "Bearer " + fixtureToken.uppercase())) {
            assertFalse(authorizer.isAuthorized(header))
        }
    }

    @Test fun missingOrFailedTokenProviderFailsClosedWithoutExposingCredentials() {
        assertFalse(DenyVoiceAuthorizer.isAuthorized("Bearer $fixtureToken"))
        assertFalse(BearerVoiceAuthorizer { "" }.isAuthorized("Bearer $fixtureToken"))
        assertFalse(BearerVoiceAuthorizer { throw IllegalStateException("unavailable private store") }.isAuthorized("Bearer $fixtureToken"))
    }

    @Test fun comparisonRejectsMismatchesAtEveryTokenPosition() {
        val authorizer = BearerVoiceAuthorizer { fixtureToken }
        for (index in fixtureToken.indices) {
            val altered = fixtureToken.toCharArray().apply { this[index] = if (this[index] == 'f') '0' else 'f' }.concatToString()
            assertFalse(authorizer.isAuthorized("Bearer $altered"))
        }
    }
}
