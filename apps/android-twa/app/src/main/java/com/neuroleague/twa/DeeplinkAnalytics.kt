package com.neuroleague.twa

import android.content.Context
import android.net.Uri
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

object DeeplinkAnalytics {
  private const val PREFS = "neuroleague_twa"
  private const val KEY_DEVICE_ID = "device_id"
  private const val KEY_PENDING_EVENTS = "pending_events_v1"
  private const val MAX_QUEUE_LEN = 100
  private val lock = Any()
  @Volatile private var flushing: Boolean = false

  fun flushPending(context: Context) {
    flushAsync(context)
  }

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

    enqueue(
      context,
      JSONObject()
        .put("api_url", apiUrl)
        .put("session_id", sessionId)
        .put("body", body.toString()),
    )
    flushAsync(context)
  }

  private fun enqueue(context: Context, entry: JSONObject) {
    val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    synchronized(lock) {
      val q = loadQueue(prefs)
      q.put(entry)
      while (q.length() > MAX_QUEUE_LEN) {
        q.remove(0)
      }
      prefs.edit().putString(KEY_PENDING_EVENTS, q.toString()).apply()
    }
  }

  private fun flushAsync(context: Context) {
    synchronized(lock) {
      if (flushing) return
      flushing = true
    }
    Thread {
      try {
        flushLoop(context)
      } catch (_: Exception) {
        // ignore
      } finally {
        synchronized(lock) { flushing = false }
      }
    }.start()
  }

  private fun flushLoop(context: Context) {
    val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    val deviceId = getOrCreateDeviceId(context)
    while (true) {
      val next: JSONObject? =
        synchronized(lock) {
          val q = loadQueue(prefs)
          if (q.length() <= 0) return
          q.optJSONObject(0)
        }
      if (next == null) {
        synchronized(lock) {
          val q = loadQueue(prefs)
          if (q.length() > 0) {
            q.remove(0)
            prefs.edit().putString(KEY_PENDING_EVENTS, q.toString()).apply()
          }
        }
        continue
      }
      val apiUrl = next.optString("api_url", "").trim()
      val body = next.optString("body", "").trim()
      val sessionId = next.optString("session_id", "").trim().ifBlank { UUID.randomUUID().toString() }
      if (apiUrl.isBlank() || body.isBlank()) {
        synchronized(lock) {
          val q = loadQueue(prefs)
          if (q.length() > 0) {
            q.remove(0)
            prefs.edit().putString(KEY_PENDING_EVENTS, q.toString()).apply()
          }
        }
        continue
      }

      val ok = postJson(apiUrl = apiUrl, deviceId = deviceId, sessionId = sessionId, body = body)
      if (!ok) return

      synchronized(lock) {
        val q = loadQueue(prefs)
        if (q.length() > 0) {
          q.remove(0)
          prefs.edit().putString(KEY_PENDING_EVENTS, q.toString()).apply()
        }
      }
    }
  }

  private fun loadQueue(prefs: android.content.SharedPreferences): JSONArray {
    val raw = prefs.getString(KEY_PENDING_EVENTS, null)
    if (raw.isNullOrBlank()) return JSONArray()
    return try {
      val parsed = JSONArray(raw)
      if (parsed.length() > MAX_QUEUE_LEN) {
        val out = JSONArray()
        val start = parsed.length() - MAX_QUEUE_LEN
        for (i in start until parsed.length()) {
          val it = parsed.optJSONObject(i)
          if (it != null) out.put(it)
        }
        out
      } else {
        parsed
      }
    } catch (_: Exception) {
      JSONArray()
    }
  }

  private fun postJson(apiUrl: String, deviceId: String, sessionId: String, body: String): Boolean {
    try {
      val conn =
        (URL(apiUrl).openConnection() as HttpURLConnection).apply {
          requestMethod = "POST"
          connectTimeout = 2500
          readTimeout = 2500
          doOutput = true
          setRequestProperty("content-type", "application/json")
          setRequestProperty("x-device-id", deviceId)
          setRequestProperty("x-session-id", sessionId)
        }
      OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { w -> w.write(body) }
      val code = conn.responseCode
      if (code in 200..299) {
        try {
          conn.inputStream.use { _ -> }
        } catch (_: Exception) {
          // ignore
        }
        conn.disconnect()
        return true
      }
      try {
        conn.errorStream?.use { _ -> }
      } catch (_: Exception) {
        // ignore
      }
      conn.disconnect()
      return false
    } catch (_: Exception) {
      return false
    }
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
