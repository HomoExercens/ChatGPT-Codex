package com.neuroleague.twa

import android.content.Context
import android.net.Uri
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import org.json.JSONObject

object DeeplinkAnalytics {
  private const val PREFS = "neuroleague_twa"
  private const val KEY_DEVICE_ID = "device_id"

  fun maybeTrack(context: Context, deepLink: Uri?) {
    if (deepLink == null) return
    val scheme = deepLink.scheme ?: return
    if (scheme != "https" && scheme != "http") return
    val host = deepLink.host ?: return

    val apiUrl = buildString {
      append(scheme)
      append("://")
      append(host)
      val port = deepLink.port
      if (port > 0) {
        append(":")
        append(port)
      }
      append("/api/events")
    }

    val deviceId = getOrCreateDeviceId(context)
    val sessionId = UUID.randomUUID().toString()

    val utm = JSONObject()
    for (k in listOf("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")) {
      val v = deepLink.getQueryParameter(k)
      if (!v.isNullOrBlank()) utm.put(k, v)
    }

    val meta = JSONObject()
    meta.put("deeplink_url", deepLink.toString())
    meta.put("deeplink_path", deepLink.path ?: "")
    meta.put("deeplink_query", deepLink.query ?: "")
    meta.put("from", "android_twa")

    val body = JSONObject()
    body.put("type", "app_open_deeplink")
    body.put("url", deepLink.toString())
    body.put("source", "android_twa")
    val ref = deepLink.getQueryParameter("ref")
    if (!ref.isNullOrBlank()) body.put("ref", ref)
    body.put("utm", utm)
    body.put("meta", meta)

    Thread {
      try {
        val conn = (URL(apiUrl).openConnection() as HttpURLConnection).apply {
          requestMethod = "POST"
          connectTimeout = 2500
          readTimeout = 2500
          doOutput = true
          setRequestProperty("content-type", "application/json")
          setRequestProperty("x-device-id", deviceId)
          setRequestProperty("x-session-id", sessionId)
        }
        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { w -> w.write(body.toString()) }
        conn.inputStream.use { _ -> }
        conn.disconnect()
      } catch (_: Exception) {
        // ignore
      }
    }.start()
  }

  private fun getOrCreateDeviceId(context: Context): String {
    val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    val existing = prefs.getString(KEY_DEVICE_ID, null)
    if (!existing.isNullOrBlank()) return existing
    val created = "dev_" + UUID.randomUUID().toString().replace("-", "")
    prefs.edit().putString(KEY_DEVICE_ID, created).apply()
    return created
  }
}

