package com.neuroleague.twa

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Bundle
import com.google.androidbrowserhelper.trusted.LauncherActivity

class MainActivity : LauncherActivity() {
  private var networkCallback: ConnectivityManager.NetworkCallback? = null

  override fun onCreate(savedInstanceState: Bundle?) {
    DeeplinkAnalytics.flushPending(applicationContext)
    DeeplinkAnalytics.maybeTrack(applicationContext, intent?.data)
    registerNetworkFlush()
    super.onCreate(savedInstanceState)
  }

  override fun onDestroy() {
    unregisterNetworkFlush()
    super.onDestroy()
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

  private fun registerNetworkFlush() {
    if (networkCallback != null) return
    try {
      val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
      val cb =
        object : ConnectivityManager.NetworkCallback() {
          override fun onAvailable(network: Network) {
            DeeplinkAnalytics.flushPending(applicationContext)
          }
        }
      cm.registerDefaultNetworkCallback(cb)
      networkCallback = cb
    } catch (_: Exception) {
      networkCallback = null
    }
  }

  private fun unregisterNetworkFlush() {
    val cb = networkCallback ?: return
    networkCallback = null
    try {
      val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
      cm.unregisterNetworkCallback(cb)
    } catch (_: Exception) {
      // ignore
    }
  }
}
