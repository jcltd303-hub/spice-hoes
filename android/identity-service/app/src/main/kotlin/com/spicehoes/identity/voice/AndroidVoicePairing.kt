package com.spicehoes.identity.voice

import android.content.Context

/** Only the visible native UI exports the token; there is no HTTP pairing/token endpoint. */
object AndroidVoicePairing {
    private fun pairing(context: Context): VoicePairing {
        val preferences = context.applicationContext.getSharedPreferences("spice_voice_pairing", Context.MODE_PRIVATE)
        return VoicePairing(object : VoiceTokenStore {
            override fun read(): String? = try { preferences.getString("pairing_token", null) }
                catch (_: ClassCastException) { null }
            override fun write(token: String) = preferences.edit().putString("pairing_token", token).commit()
        })
    }

    fun token(context: Context): String = pairing(context).token()
    fun command(context: Context): String = pairing(context).pairingCommand()
}
