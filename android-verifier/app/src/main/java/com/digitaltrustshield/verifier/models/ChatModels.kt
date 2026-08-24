package com.digitaltrustshield.verifier.models

import kotlinx.serialization.Serializable

@Serializable
data class ChatRequest(
    val message: String,
    val language: String
)

@Serializable
data class ChatSource(
    val title: String,
    val url: String,
    val content: String? = null
)

@Serializable
data class ChatResponse(
    val success: Boolean,
    val answer: String,
    val language: String,
    val sources: List<ChatSource> = emptyList()
)
