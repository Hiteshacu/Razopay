package com.digitaltrustshield.verifier

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.digitaltrustshield.verifier.api.ApiClient
import com.digitaltrustshield.verifier.models.ChatRequest
import com.digitaltrustshield.verifier.models.ChatSource
import com.digitaltrustshield.verifier.models.PublicKeyDto
import com.digitaltrustshield.verifier.models.VerificationResponse
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import retrofit2.HttpException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    DigitalTrustShieldApp()
                }
            }
        }
    }
}

private enum class AppTab(val label: String) {
    Verify("Verification"),
    Chat("Chatbot")
}

private data class LanguageOption(
    val label: String,
    val code: String,
    val speechLocale: String
)

private data class ChatBubble(
    val fromUser: Boolean,
    val text: String,
    val sources: List<ChatSource> = emptyList()
)

private val languageOptions = listOf(
    LanguageOption("English", "en", "en-IN"),
    LanguageOption("Kannada", "kn", "kn-IN"),
    LanguageOption("Hindi", "hi", "hi-IN")
)

@Composable
fun DigitalTrustShieldApp() {
    var selectedTab by remember { mutableStateOf(AppTab.Verify) }

    Scaffold(
        bottomBar = {
            NavigationBar(containerColor = Color.White) {
                NavigationBarItem(
                    selected = selectedTab == AppTab.Verify,
                    onClick = { selectedTab = AppTab.Verify },
                    label = { Text(AppTab.Verify.label) },
                    icon = { Text("DTS") }
                )
                NavigationBarItem(
                    selected = selectedTab == AppTab.Chat,
                    onClick = { selectedTab = AppTab.Chat },
                    label = { Text(AppTab.Chat.label) },
                    icon = { Text("AI") }
                )
            }
        }
    ) { padding ->
        when (selectedTab) {
            AppTab.Verify -> VerificationScreen(padding)
            AppTab.Chat -> ChatbotScreen(padding)
        }
    }
}

@Composable
fun VerificationScreen(padding: PaddingValues) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var keys by remember { mutableStateOf<List<PublicKeyDto>>(emptyList()) }
    var selectedKey by remember { mutableStateOf<PublicKeyDto?>(null) }
    var showKeyPicker by remember { mutableStateOf(false) }
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    var result by remember { mutableStateOf<VerificationResponse?>(null) }
    var status by remember { mutableStateOf("Ready") }
    var loading by remember { mutableStateOf(false) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        selectedUri = uri
        result = null
    }

    LaunchedEffect(Unit) {
        runCatching { ApiClient.api.publicKeys() }
            .onSuccess {
                keys = it.filter { key -> key.active }
                selectedKey = keys.firstOrNull()
                status = "Loaded ${keys.size} public keys"
            }
            .onFailure { status = "Could not load public keys: ${it.message}" }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF4F1E8))
            .verticalScroll(rememberScrollState())
            .padding(padding)
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        AppHeader("Digital Trust Shield", "Verify official posters, notices, receipts, and PDFs against authority public keys.")

        Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                OutlinedButton(onClick = { picker.launch("image/*") }, modifier = Modifier.fillMaxWidth()) {
                    Text(selectedUri?.lastPathSegment ?: "Select image from gallery")
                }

                OutlinedButton(
                    onClick = { showKeyPicker = true },
                    enabled = keys.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        selectedKey?.let { "${it.authority_name} - ${it.key_id.takeLast(6)}" }
                            ?: if (keys.isEmpty()) "No public keys available" else "Select authority/public key"
                    )
                }

                Button(
                    enabled = selectedUri != null && selectedKey != null && !loading,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        val uri = selectedUri ?: return@Button
                        val key = selectedKey ?: return@Button
                        loading = true
                        status = "Verifying..."
                        result = null
                        scope.launch {
                            runCatching {
                                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                                    ?: error("Could not read selected image")
                                val body = bytes.toRequestBody("image/*".toMediaType())
                                val part = MultipartBody.Part.createFormData("file", "verification_image.png", body)
                                val keyBody = key.key_id.toRequestBody("text/plain".toMediaType())
                                ApiClient.api.verify(part, keyBody)
                            }.onSuccess {
                                result = it
                                status = "Verification complete"
                            }.onFailure {
                                status = verificationFailureMessage(it)
                            }
                            loading = false
                        }
                    }
                ) {
                    Text(if (loading) "Verifying..." else "Verify")
                }
            }
        }

        if (showKeyPicker) {
            KeyPickerDialog(keys, onSelect = {
                selectedKey = it
                showKeyPicker = false
            }, onDismiss = { showKeyPicker = false })
        }

        result?.let { VerificationResultCard(it) }
        Text(status, color = Color(0xFF475569))
    }
}

@Composable
fun ChatbotScreen(padding: PaddingValues) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val messages = remember {
        mutableStateListOf(
            ChatBubble(
                fromUser = false,
                text = "Namaste. Ask me about government schemes, cyber safety, poster verification, public notices, or current facts. I can search the web and answer in English, Kannada, or Hindi."
            )
        )
    }
    var selectedLanguage by remember { mutableStateOf(languageOptions.first()) }
    var showLanguagePicker by remember { mutableStateOf(false) }
    var input by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("Ready") }
    var loading by remember { mutableStateOf(false) }

    val speechLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spokenText = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
            if (!spokenText.isNullOrBlank()) {
                input = spokenText
                status = "Voice captured"
            }
        }
    }

    fun startVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, selectedLanguage.speechLocale)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak in ${selectedLanguage.label}")
        }
        runCatching { speechLauncher.launch(intent) }
            .onFailure { status = "Voice input is not available on this device." }
    }

    val microphonePermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startVoiceInput() else status = "Microphone permission denied"
    }

    fun sendMessage() {
        val message = input.trim()
        if (message.isBlank() || loading) return
        messages.add(ChatBubble(fromUser = true, text = message))
        input = ""
        loading = true
        status = "Searching web and asking Groq..."
        scope.launch {
            runCatching {
                ApiClient.api.chat(ChatRequest(message = message, language = selectedLanguage.code))
            }.onSuccess { response ->
                messages.add(ChatBubble(fromUser = false, text = response.answer, sources = response.sources))
                status = "Answer ready"
            }.onFailure { error ->
                messages.add(ChatBubble(fromUser = false, text = chatFailureMessage(error)))
                status = "Chat failed"
            }
            loading = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF4F1E8))
            .verticalScroll(rememberScrollState())
            .padding(padding)
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        AppHeader("DTS Sahayak", "A web-search chatbot powered by Tavily + Groq, with voice input and Indian language support.")

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { showLanguagePicker = true }, modifier = Modifier.weight(1f)) {
                Text(selectedLanguage.label)
            }
            OutlinedButton(
                onClick = {
                    if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        startVoiceInput()
                    } else {
                        microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                    }
                },
                modifier = Modifier.weight(1f)
            ) {
                Text("Voice")
            }
        }

        Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                messages.forEach { bubble -> ChatBubbleCard(bubble) }
            }
        }

        OutlinedTextField(
            value = input,
            onValueChange = { input = it },
            modifier = Modifier.fillMaxWidth(),
            minLines = 2,
            label = { Text("Ask something...") }
        )

        Button(enabled = input.isNotBlank() && !loading, onClick = { sendMessage() }, modifier = Modifier.fillMaxWidth()) {
            Text(if (loading) "Thinking..." else "Ask Sahayak")
        }

        Text(status, color = Color(0xFF475569))
    }

    if (showLanguagePicker) {
        AlertDialog(
            onDismissRequest = { showLanguagePicker = false },
            title = { Text("Choose language") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    languageOptions.forEach { language ->
                        OutlinedButton(
                            onClick = {
                                selectedLanguage = language
                                showLanguagePicker = false
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(language.label)
                        }
                    }
                }
            },
            confirmButton = {},
            dismissButton = {
                TextButton(onClick = { showLanguagePicker = false }) { Text("Close") }
            }
        )
    }
}

@Composable
private fun AppHeader(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Black)
        Text(subtitle, color = Color(0xFF1F2937))
    }
}

@Composable
private fun ChatBubbleCard(message: ChatBubble) {
    val background = if (message.fromUser) Color(0xFFEDE9FE) else Color(0xFFF8FAFC)
    val title = if (message.fromUser) "You" else "DTS Sahayak"
    Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = background)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, fontWeight = FontWeight.Bold, color = Color(0xFF4C1D95))
            Text(message.text)
            if (message.sources.isNotEmpty()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text("Sources", fontWeight = FontWeight.Bold)
                message.sources.take(3).forEachIndexed { index, source ->
                    Text("${index + 1}. ${source.title}\n${source.url}", color = Color(0xFF475569))
                }
            }
        }
    }
}

@Composable
private fun KeyPickerDialog(
    keys: List<PublicKeyDto>,
    onSelect: (PublicKeyDto) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select authority/public key") },
        text = {
            if (keys.isEmpty()) {
                Text("No active public keys were loaded from the backend.")
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    keys.forEach { key ->
                        OutlinedButton(onClick = { onSelect(key) }, modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.fillMaxWidth()) {
                                Text(key.authority_name, fontWeight = FontWeight.Bold)
                                Text(key.key_id)
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Close") }
        }
    )
}

private fun verificationFailureMessage(error: Throwable): String {
    return when (error) {
        is SocketTimeoutException -> {
            "Verification network timeout. Check that backend is running at ${BuildConfig.API_BASE_URL} and rebuild the app if your laptop IP changed."
        }
        is ConnectException, is UnknownHostException -> {
            "Cannot reach backend at ${BuildConfig.API_BASE_URL}. Use your laptop Wi-Fi IP in app/build.gradle.kts, then rebuild the app."
        }
        else -> "Verification failed: ${error.message ?: error::class.java.simpleName}"
    }
}

private fun chatFailureMessage(error: Throwable): String {
    return when (error) {
        is SocketTimeoutException -> "The chatbot request timed out. Please check the backend and try again."
        is ConnectException, is UnknownHostException -> "Cannot reach chatbot backend at ${BuildConfig.API_BASE_URL}."
        is HttpException -> "Chat failed: ${backendErrorDetail(error)}"
        else -> "Chat failed: ${error.message ?: error::class.java.simpleName}"
    }
}

private fun backendErrorDetail(error: HttpException): String {
    val fallback = "HTTP ${error.code()} ${error.message()}"
    val body = error.response()?.errorBody()?.string().orEmpty()
    if (body.isBlank()) return fallback
    return runCatching {
        val detail = JSONObject(body).opt("detail")
        when (detail) {
            is String -> detail
            null -> fallback
            else -> detail.toString()
        }
    }.getOrDefault(fallback)
}

@Composable
fun VerificationResultCard(response: VerificationResponse) {
    val authentic = response.result == "AUTHENTIC"
    val color = if (authentic) Color(0xFF15803D) else Color(0xFFB91C1C)
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(
            modifier = Modifier.padding(18.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            verticalAlignment = Alignment.Top
        ) {
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .background(color, RoundedCornerShape(4.dp))
            )
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text(if (authentic) "Authentic" else response.result.replace("_", " "), color = color, fontWeight = FontWeight.Black)
                Text(response.reason)
                Spacer(modifier = Modifier.height(4.dp))
                Text("Authority: ${response.authority_name ?: "Unknown"}")
                Text("Key: ${response.key_id ?: "Not selected"}")
            }
        }
    }
}
