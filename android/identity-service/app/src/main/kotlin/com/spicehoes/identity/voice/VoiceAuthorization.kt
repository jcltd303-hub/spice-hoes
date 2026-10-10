package com.spicehoes.identity.voice

import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.SecureRandom

fun interface VoiceAuthorizer {
    fun isAuthorized(authorization: String?): Boolean
}

/** Fail closed when a router has not been wired to the private Android token store. */
object DenyVoiceAuthorizer : VoiceAuthorizer {
    override fun isAuthorized(authorization: String?) = false
}

class BearerVoiceAuthorizer(private val tokenProvider: () -> String) : VoiceAuthorizer {
    override fun isAuthorized(authorization: String?): Boolean {
        if (authorization == null || !authorization.startsWith("Bearer ", ignoreCase = true)) return false
        val presented = authorization.substring(7)
        if (!isVoicePairingToken(presented)) return false
        val expected = try { tokenProvider() } catch (_: Exception) { return false }
        if (!isVoicePairingToken(expected)) return false
        // Both inputs are exactly 64 ASCII bytes, avoiding length-dependent comparison paths.
        return MessageDigest.isEqual(expected.toByteArray(StandardCharsets.US_ASCII), presented.toByteArray(StandardCharsets.US_ASCII))
    }
}

private val tokenPattern = Regex("[0-9a-f]{64}")
internal fun isVoicePairingToken(value: String) = tokenPattern.matches(value)

interface VoiceTokenStore {
    fun read(): String?
    fun write(token: String): Boolean
}

class VoicePairing(private val store: VoiceTokenStore, private val random: SecureRandom = SecureRandom()) {
    fun token(): String = synchronized(tokenLock) {
        val saved = try { store.read() } catch (_: Exception) { throw persistenceFailure() }
        if (saved != null && isVoicePairingToken(saved)) return@synchronized saved
        val bytes = ByteArray(32)
        random.nextBytes(bytes)
        val alphabet = "0123456789abcdef"
        val generated = buildString(64) {
            for (byte in bytes) {
                val value = byte.toInt() and 0xff
                append(alphabet[value ushr 4])
                append(alphabet[value and 0x0f])
            }
        }
        bytes.fill(0)
        if (!try { store.write(generated) } catch (_: Exception) { false }) throw persistenceFailure()
        generated
    }

    fun pairingCommand() = "export SPICE_ANDROID_VOICE_TOKEN='${token()}'"

    private fun persistenceFailure() = ServiceException(ErrorCode.VOICE_UNAVAILABLE,
        "Private voice pairing token could not be saved; check app storage and restart the companion")

    private companion object {
        // UI and HTTP consumers may create separate adapters over the same SharedPreferences file.
        val tokenLock = Any()
    }
}
