package com.digitaltrustshield.verifier.models

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class VerificationResponse(
    val success: Boolean,
    val result: String,
    val reason: String,
    val authority_name: String? = null,
    val authority_id: String? = null,
    val key_id: String? = null,
    val details: Map<String, JsonElement>? = null
)
