package com.digitaltrustshield.verifier.api

import com.digitaltrustshield.verifier.models.ChatRequest
import com.digitaltrustshield.verifier.models.ChatResponse
import com.digitaltrustshield.verifier.models.PublicKeyDto
import com.digitaltrustshield.verifier.models.VerificationResponse
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.GET
import retrofit2.http.Body
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

interface VerificationApi {
    @GET("api/keys/public")
    suspend fun publicKeys(): List<PublicKeyDto>

    @Multipart
    @POST("api/verify")
    suspend fun verify(
        @Part file: MultipartBody.Part,
        @Part("key_id") keyId: RequestBody
    ): VerificationResponse

    @POST("api/chat")
    suspend fun chat(@Body request: ChatRequest): ChatResponse
}
