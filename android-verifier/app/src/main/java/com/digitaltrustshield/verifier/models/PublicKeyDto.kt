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
    val fingerprint_sha256: String,
    // Who holds this key: the part of their account address before the @.
    // Nullable because a key issued before accounts owned authorities has
    // nobody recorded, and an old key must not crash a new app.
    val owner_username: String? = null
)

