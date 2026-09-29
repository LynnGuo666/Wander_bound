plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.deepsleeptt.travelmemory.upload"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.deepsleeptt.travelmemory.upload"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
}

kotlin {
    jvmToolchain(17)
}
