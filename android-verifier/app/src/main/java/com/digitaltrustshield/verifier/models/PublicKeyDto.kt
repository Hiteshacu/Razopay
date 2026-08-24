package com.digitaltrustshield.verifier.models

import kotlinx.serialization.Serializable

@Serializable
data class PublicKeyDto(
    val key_id: String,
    val authority_id: String,
    val authority_name: String,
    val public_key_pem: String,
    val algorithm: String,
    val key_size: Int,
    val created_at: String,
    val active: Boolean,
    val fingerprint_sha256: String
)

