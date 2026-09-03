package com.digitaltrustshield.verifier

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
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
import com.digitaltrustshield.verifier.api.Backend
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
                    PayProofApp()
                }
            }
        }
    }
}

private enum class AppTab(val label: String) {
    Verify("Verify"),
    Settings("Server")
}

@Composable
fun PayProofApp() {
    var selectedTab by remember { mutableStateOf(AppTab.Verify) }

    Scaffold(
        bottomBar = {
            NavigationBar(containerColor = Color.White) {
                NavigationBarItem(
                    selected = selectedTab == AppTab.Verify,
                    onClick = { selectedTab = AppTab.Verify },
                    label = { Text(AppTab.Verify.label) },
                    icon = { Text("PP") }
                )
                NavigationBarItem(
                    selected = selectedTab == AppTab.Settings,
                    onClick = { selectedTab = AppTab.Settings },
                    label = { Text(AppTab.Settings.label) },
                    icon = { Text("@") }
                )
            }
        }
    ) { padding ->
        when (selectedTab) {
            AppTab.Verify -> VerificationScreen(padding)
            AppTab.Settings -> ServerScreen(padding)
        }
    }
}

/**
 * Where the app is pointing, and a way to change it.
 *
 * This screen exists because the previous build hard-coded its backend and
 * shipped pointing at a service that had already been replaced. Anyone holding
 * that APK had no way to correct it and no way to see what was wrong: the app
 * simply failed to load any keys. The address is now visible, testable and
 * editable on the device, so a backend move no longer needs a new APK.
 */
@Composable
fun ServerScreen(padding: PaddingValues) {
    val scope = rememberCoroutineScope()
    var draft by remember { mutableStateOf(ApiClient.currentBaseUrl()) }
    var testing by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }
    var ok by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(padding)
            .padding(20.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        AppHeader("Server", "Where this app looks for keys and verification")

        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it; result = null },
            label = { Text("API address") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        Text(
            if (Backend.isOverridden()) "Using a saved address."
            else "Using the address this build shipped with.",
            style = MaterialTheme.typography.bodySmall
        )

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                enabled = !testing && draft.isNotBlank(),
                onClick = {
                    val candidate = Backend.normalise(draft)
                    draft = candidate
                    testing = true
                    result = null
                    scope.launch {
                        // Saved before the probe so the probe goes to the
                        // address being tested, not the one still in force.
                        Backend.save(candidate)
                        val reached = runCatching { ApiClient.api.ping() }
                        val keyCount = if (reached.isSuccess) {
                            runCatching { ApiClient.api.publicKeys().size }.getOrNull()
                        } else {
                            null
                        }
                        testing = false
                        ok = reached.isSuccess && keyCount != null && keyCount > 0
                        result = when {
                            reached.isFailure -> "Could not reach it. " +
                                verificationFailureMessage(
                                    reached.exceptionOrNull() ?: RuntimeException("unknown")
                                )
                            keyCount == null -> "Reachable, but the key list could not be read."
                            keyCount == 0 -> "Reachable, but no authority has published a key yet."
                            else -> "Connected. " + keyCount + " published key" +
                                (if (keyCount == 1) "" else "s") + " available."
                        }
                    }
                }
            ) { Text(if (testing) "Testing..." else "Save and test") }

            OutlinedButton(
                enabled = !testing,
                onClick = {
                    Backend.reset()
                    draft = ApiClient.currentBaseUrl()
                    ok = true
                    result = "Reset to the address this build shipped with."
                }
            ) { Text("Reset") }
        }

        result?.let { message ->
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(
                    containerColor = if (ok) Color(0xFFE8F6F0) else Color(0xFFF7E4E0)
                )
            ) {
                Text(
                    message,
                    modifier = Modifier.padding(14.dp),
                    color = if (ok) Color(0xFF0B8A5A) else Color(0xFFB91C1C)
                )
            }
        }
    }
}

@Composable
fun VerificationScreen(padding: PaddingValues) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var keys by remember { mutableStateOf<List<PublicKeyDto>>(emptyList()) }
    var signerQuery by remember { mutableStateOf("") }
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
                status = if (keys.isEmpty()) {
                    "No public keys published yet"
                } else {
                    "Ready - enter the signer's name to begin"
                }
            }
            .onFailure { status = "Could not load public keys: ${it.message}" }
    }

    // Keys held by whoever the typed name matches.
    //
    // A blank name matches nothing, deliberately. The screen used to select
    // the first key in the list on load, so tapping Verify checked the
    // document against a key nobody had chosen -- and a failure then meant
    // "wrong key", which reads exactly like "forged". Naming the signer
    // first makes the answer mean something.
    val matchingKeys = remember(keys, signerQuery) {
        val query = signerQuery.trim().lowercase()
        if (query.isEmpty()) {
            emptyList()
        } else {
            keys.filter { (it.owner_username ?: "").contains(query) }
        }
    }
    val matchedSigners = remember(matchingKeys) {
        matchingKeys.mapNotNull { it.owner_username }.filter { it.isNotBlank() }.distinct()
    }

    // Settle on a key only when there is no choice to make. Picking one of
    // several on the user's behalf would be the same mistake again.
    LaunchedEffect(matchingKeys) {
        selectedKey = matchingKeys.singleOrNull()
        result = null
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

                OutlinedTextField(
                    value = signerQuery,
                    onValueChange = { signerQuery = it },
                    label = { Text("Who signed it?") },
                    placeholder = { Text("e.g. pramila") },
                    singleLine = true,
                    enabled = keys.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth()
                )

                if (signerQuery.isNotBlank()) {
                    Text(
                        if (matchedSigners.isEmpty()) {
                            "No signer named \"${signerQuery.trim()}\""
                        } else {
                            val count = matchingKeys.size
                            "${matchedSigners.joinToString(", ")} - $count key" +
                                if (count == 1) "" else "s"
                        },
                        color = if (matchedSigners.isEmpty()) Color(0xFFB91C1C) else Color(0xFF0F766E)
                    )
                }

                OutlinedButton(
                    onClick = { showKeyPicker = true },
                    // Only offer the picker when there is genuinely a choice.
                    enabled = matchingKeys.size > 1,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        when {
                            keys.isEmpty() -> "No public keys available"
                            signerQuery.isBlank() -> "Enter a name above first"
                            matchingKeys.isEmpty() -> "No authority for that name"
                            selectedKey != null ->
                                "${selectedKey!!.authority_name} - ${selectedKey!!.key_id.takeLast(6)}"
                            else -> "Choose one of ${matchingKeys.size} authorities"
                        }
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
            KeyPickerDialog(matchingKeys, onSelect = {
                selectedKey = it
                showKeyPicker = false
            }, onDismiss = { showKeyPicker = false })
        }

        result?.let { VerificationResultCard(it) }
        Text(status, color = Color(0xFF475569))
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
private fun KeyPickerDialog(
    keys: List<PublicKeyDto>,
    onSelect: (PublicKeyDto) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Which authority?") },
        text = {
            if (keys.isEmpty()) {
                Text("This signer has no active public keys.")
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
            }
        }
    }
}
