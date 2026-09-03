package com.digitaltrustshield.verifier.api

import com.digitaltrustshield.verifier.BuildConfig
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

/**
 * The API, built against whatever address is currently in force.
 *
 * Rebuilt rather than fixed at startup, because the address can change while
 * the app is open — see Backend. `invalidate()` drops the cached Retrofit so
 * the next call picks up a new address without restarting the app.
 */
object ApiClient {
    private val json = Json { ignoreUnknownKeys = true }

    private val http = OkHttpClient.Builder()
        // A cold backend on a free tier can take the better part of a minute
        // to answer its first request, and verification itself runs several
        // recovery passes. Short timeouts here surface as "network error" on
        // a service that was merely waking up.
        .connectTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .callTimeout(150, TimeUnit.SECONDS)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                    else HttpLoggingInterceptor.Level.NONE
        })
        .build()

    @Volatile private var cached: VerificationApi? = null
    @Volatile private var cachedFor: String? = null

    /** The address the next request will go to. */
    fun currentBaseUrl(): String = Backend.baseUrl(BuildConfig.API_BASE_URL)

    fun invalidate() {
        cached = null
        cachedFor = null
    }

    val api: VerificationApi
        get() {
            val url = currentBaseUrl()
            val existing = cached
            if (existing != null && cachedFor == url) return existing
            val built = Retrofit.Builder()
                .baseUrl(url)
                .client(http)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(VerificationApi::class.java)
            cached = built
            cachedFor = url
            return built
        }
}
