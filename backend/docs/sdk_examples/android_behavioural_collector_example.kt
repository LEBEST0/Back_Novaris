package com.novaris.sdk.example

import android.content.Context
import android.os.Build
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class BehaviouralMetadataCollector {

    enum class Platform {
        ANDROID,
        IOS,
        WEB_MOCK,
    }

    private fun canonicalJson(payload: Map<String, Any?>): String {
        // Signature légère uniquement: ce JSON canonique sera remplacé plus tard par une attestation forte.
        return JSONObject(java.util.TreeMap(payload)).toString()
    }

    private fun hmacSha256Hex(secret: String, message: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val digest = mac.doFinal(message.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }

    fun buildMockPayload(
        context: Context,
        userId: String,
        sessionId: String,
        actionType: String,
        platform: Platform = Platform.ANDROID,
        sdkVersion: String = "1.0.0",
        payloadVersion: String = "v1",
    ): Map<String, Any?> {
        val nonce = UUID.randomUUID().toString()
        val requestId = UUID.randomUUID().toString()
        val timestamp = java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC).toString()

        return mapOf(
            "user_id" to userId,
            "session_id" to sessionId,
            "action_type" to actionType,
            "request_id" to requestId,
            "timestamp" to timestamp,
            "nonce" to nonce,
            "sdk_version" to sdkVersion,
            "payload_version" to payloadVersion,
            "platform" to platform.name,
            "avg_key_interval_ms" to 180.0,
            "avg_touch_duration_ms" to 120.0,
            "typing_speed_cps" to 4.2,
            "tap_pressure_avg" to 0.45,
            "tap_pressure_std" to 0.08,
            "error_count" to 1,
            "correction_count" to 0,
            "hesitation_time_ms" to 350.0,
            "swipe_speed_avg" to 1.8,
            "touch_precision_score" to 0.91,
            "device_orientation_changes" to 2,
            "session_duration_ms" to 42000.0,
            "is_rooted" to false,
            "is_emulator" to false,
            "is_vpn" to false,
            "is_proxy" to false,
            "brand" to Build.BRAND,
            "model" to Build.MODEL,
            "os_name" to "Android",
            "os_version" to Build.VERSION.RELEASE,
        )
    }

    fun buildHeaders(payload: Map<String, Any?>, signatureSecret: String): Map<String, String> {
        val canonicalPayload = canonicalJson(payload)
        val signature = hmacSha256Hex(signatureSecret, canonicalPayload)
        return mapOf(
            "X-Novaris-Signature" to signature,
            "X-Novaris-Client-Key" to "REPLACE_WITH_CLIENT_KEY",
        )
    }

    fun generateBehaviouralHash(userId: String, sessionId: String): String {
        val raw = listOf(userId, sessionId, Build.BRAND, Build.MODEL, Build.VERSION.RELEASE).joinToString("|")
        val digest = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}

