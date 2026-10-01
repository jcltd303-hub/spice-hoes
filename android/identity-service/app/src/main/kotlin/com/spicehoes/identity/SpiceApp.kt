package com.spicehoes.identity

import android.app.Application

class SpiceApp : Application() {
    override fun onCreate() {
        super.onCreate()
        DiagLog.init(filesDir.resolve("logs"))
        CrashReporter.install(this)
        DiagLog.log("I", "app start v${BuildConfig.VERSION_NAME} build ${BuildConfig.BUILD_ID} ${BuildConfig.GIT_SHA}")
    }
}
