package com.digitaltrustshield.verifier.api

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/**
 * Where the app looks for the API.
 *
 * This used to be a single compile-time constant, which is why the shipped
 * APK was still pointing at a Render service that had been superseded months
 * earlier. Every backend move meant rebuilding, re-signing and redistributing
 * an APK to people who had already installed one — so in practice the address
 * went stale and the app simply stopped verifying, with no way for anyone
 * holding it to fix that.
 *
 * The build-time value is now only a default. Whatever is stored here wins,
 * so a working install can be pointed at a new backend from inside the app.
 */
object Backend {

    private const val PREFS = "payproof.backend"
    private const val KEY_URL = "base_url"

    private lateinit var prefs: SharedPreferences

    fun attach(context: Context) {
        if (!Backend::prefs.isInitialized) {
            prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        }
    }

    /** The address in force: whatever was saved, else the build-time default. */
    fun baseUrl(default: String): String {
        val stored = if (Backend::prefs.isInitialized) prefs.getString(KEY_URL, null) else null
        return normalise(stored?.takeIf { it.isNotBlank() } ?: default)
    }

    /** Whether the address currently in use came from the user rather than the build. */
    fun isOverridden(): Boolean =
        Backend::prefs.isInitialized && !prefs.getString(KEY_URL, null).isNullOrBlank()

    fun save(url: String) {
        if (!Backend::prefs.isInitialized) return
        prefs.edit { putString(KEY_URL, url.trim().takeIf { it.isNotBlank() }) }
        ApiClient.invalidate()
    }

    fun reset() {
        if (!Backend::prefs.isInitialized) return
        prefs.edit { remove(KEY_URL) }
        ApiClient.invalidate()
    }

    /**
     * Repair the two ways an address typed by hand is usually wrong.
     *
     * A missing scheme, because Retrofit rejects a bare host outright and the
     * error it raises names neither the setting nor the value. And a missing
     * trailing slash, because Retrofit requires one on a base URL and throws
     * "baseUrl must end in /" — which reads like a bug in the app rather than
     * a typo in a text field.
     */
    fun normalise(raw: String): String {
        var url = raw.trim()
        if (url.isEmpty()) return url
        if (!url.startsWith("http://", true) && !url.startsWith("https://", true)) {
            // Plain http only for a loopback address, where TLS cannot work.
            // Anything else gets https: a public API on http would be blocked
            // by the network security policy in any case.
            val local = url.startsWith("10.0.2.2") ||
                url.startsWith("127.0.0.1") ||
                url.startsWith("localhost") ||
                url.startsWith("192.168.")
            url = (if (local) "http://" else "https://") + url
        }
        if (!url.endsWith("/")) url += "/"
        return url
    }
}
