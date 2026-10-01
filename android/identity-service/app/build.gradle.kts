plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android { namespace="live.fishgame.spiceidentity"; compileSdk=35
 defaultConfig { applicationId="live.fishgame.spiceidentity"; minSdk=28; targetSdk=35; versionCode=1; versionName="0.1.0" }
}
dependencies { implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0") }
