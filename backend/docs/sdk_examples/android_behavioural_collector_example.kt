package com.novaris.sdk.example

import android.content.Context
import android.os.Build
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

class BehaviouralMetadataCollector {

    enum class Platform {
        ANDROID,
        IOS,
        WEB_MOCK,
    }

    fun buildMockPayload(
        context: Context,
        userId: String,
        sessionId: String,
        actionType: String,
        platform: Platform = Platform.ANDROID,
        sdkVersion: String = "1.0.0",
        payloadVersion: String = "v1",
    ): JSONObject {
        val nowIso = java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC).toString()
        val nonce = UUID.randomUUID().toString()
        val requestId = UUID.randomUUID().toString()

        return JSONObject().apply {
            put("user_id", userId)
            put("session_id", sessionId)
            put("action_type", actionType)
            put("request_id", requestId)
            put("timestamp", nowIso)
            put("nonce", nonce)
            put("sdk_version", sdkVersion)
            put("payload_version", payloadVersion)
            put("platform", platform.name)
            put("avg_key_interval_ms", 180.0)
            put("avg_touch_duration_ms", 120.0)
            put("typing_speed_cps", 4.2)
            put("tap_pressure_avg", 0.45)
            put("tap_pressure_std", 0.08)
            put("error_count", 1)
            put("correction_count", 0)
            put("hesitation_time_ms", 350.0)
            put("swipe_speed_avg", 1.8)
            put("touch_precision_score", 0.91)
            put("device_orientation_changes", 2)
            put("session_duration_ms", 42000.0)
            put("is_rooted", false)
            put("is_emulator", false)
            put("is_vpn", false)
            put("is_proxy", false)
            put("brand", Build.BRAND)
            put("model", Build.MODEL)
            put("os_name", "Android")
            put("os_version", Build.VERSION.RELEASE)
        }
    }

    fun generateBehaviouralHash(userId: String, sessionId: String): String {
        val raw = listOf(userId, sessionId, Build.BRAND, Build.MODEL, Build.VERSION.RELEASE).joinToString("|")
        val digest = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}

