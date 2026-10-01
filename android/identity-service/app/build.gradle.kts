plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release identification (spec section 35): CI injects these so a stale install is never ambiguous.
val gitSha: String = (System.getenv("GITHUB_SHA") ?: "dev").take(12)
val buildId: String = System.getenv("GITHUB_RUN_NUMBER") ?: "local"

android {
    namespace = "com.spicehoes.identity"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.spicehoes.identity"
        minSdk = 28
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"

        buildConfigField("String", "GIT_SHA", "\"$gitSha\"")
        buildConfigField("String", "BUILD_ID", "\"$buildId\"")
        buildConfigField("int", "API_VERSION", "1")
    }

    buildFeatures {
        buildConfig = true
    }

    // Java and Kotlin JVM targets must remain identical (spec section 33).
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    // Real org.json for JVM unit tests (android.jar only ships stubs).
    testImplementation("org.json:json:20240303")
}
