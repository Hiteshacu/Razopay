plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

configurations.configureEach {
    if (name.endsWith("Copy")) {
        isCanBeResolved = true
        isCanBeConsumed = false
        @Suppress("UnstableApiUsage")
        isCanBeDeclared = false
    }
}

android {
    namespace = "com.digitaltrustshield.verifier"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.digitaltrustshield.verifier"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "2.0"
        // The DEFAULT address only. Whatever the user saves in Settings wins
        // at runtime - see api/Backend.kt.
        //
        // This was https://trust-shield-api.onrender.com/, which had been
        // superseded and now sleeps: its first request took over 25 seconds
        // to answer, so the shipped app looked broken on launch. It points at
        // the always-on service instead.
        //
        // For local work: http://10.0.2.2:8000/ from the emulator, or the
        // machine's LAN address from a handset. Both need cleartext allowed
        // in AndroidManifest, which release builds deliberately do not have.
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"https://p01--trust-shield-api--fbm4b6hyrltk.code.run/\""
        )
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-kotlinx-serialization:2.11.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
