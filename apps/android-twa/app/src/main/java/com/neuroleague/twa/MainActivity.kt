package com.neuroleague.twa

import android.content.Intent
import android.os.Bundle
import com.google.androidbrowserhelper.trusted.LauncherActivity

class MainActivity : LauncherActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    DeeplinkAnalytics.maybeTrack(applicationContext, intent?.data)
    super.onCreate(savedInstanceState)
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    setIntent(intent)
    DeeplinkAnalytics.maybeTrack(applicationContext, intent.data)
    try {
      launchTwa()
    } catch (_: Exception) {
      // ignore
    }
  }
}

