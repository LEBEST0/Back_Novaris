package com.novaris.sdk.example

import android.view.MotionEvent
import android.os.SystemClock
import org.json.JSONObject
import java.util.TreeMap
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class BehaviouralMetricsCollector {

    private val keyPressTimesMs = mutableListOf<Long>()
    private val touchDurationsMs = mutableListOf<Long>()
    private val touchPressures = mutableListOf<Float>()
    private val actionDurationsMs = mutableListOf<Long>()

    private var sessionStartedAtMs: Long? = null
    private var sessionEndedAtMs: Long? = null
    private var currentActionType: String? = null
    private var currentActionStartedAtMs: Long? = null
    private var currentTouchDownAtMs: Long? = null
    private var currentTouchPressure: Float? = null

    private var errorCount = 0
    private var correctionCount = 0
    private var deviceOrientationChanges = 0

    fun startSession() {
        sessionStartedAtMs = SystemClock.elapsedRealtime()
        sessionEndedAtMs = null
    }

    fun endSession(): Long {
        val endAtMs = SystemClock.elapsedRealtime()
        sessionEndedAtMs = endAtMs
        val startAtMs = sessionStartedAtMs ?: endAtMs
        return (endAtMs - startAtMs).coerceAtLeast(0L)
    }

    fun startAction(actionType: String) {
        currentActionType = actionType
        currentActionStartedAtMs = SystemClock.elapsedRealtime()
    }

    fun endAction(actionType: String): Long {
        val endAtMs = SystemClock.elapsedRealtime()
        if (currentActionType != actionType || currentActionStartedAtMs == null) {
            return 0L
        }
        val duration = (endAtMs - currentActionStartedAtMs!!).coerceAtLeast(0L)
        actionDurationsMs.add(duration)
        currentActionType = null
        currentActionStartedAtMs = null
        return duration
    }

    fun recordTouchDown(event: MotionEvent) {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) {
            currentTouchDownAtMs = event.eventTime
            currentTouchPressure = event.pressure
        }
    }

    fun recordTouchUp(event: MotionEvent) {
        if (event.actionMasked == MotionEvent.ACTION_UP) {
            val downAtMs = currentTouchDownAtMs ?: event.downTime
            val duration = (event.eventTime - downAtMs).coerceAtLeast(0L)
            touchDurationsMs.add(duration)
            currentTouchDownAtMs = null
            currentTouchPressure?.let { touchPressures.add(it) }
            touchPressures.add(event.pressure)
            currentTouchPressure = null
        }
    }

    fun recordKeyPress() {
        keyPressTimesMs.add(SystemClock.elapsedRealtime())
    }

    fun recordError() {
        errorCount += 1
    }

    fun recordCorrection() {
        correctionCount += 1
    }

    fun buildPayload(userId: String, sessionId: String, actionType: String): Map<String, Any?> {
        val timestamp = java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC).toString()
        return mapOf(
            "user_id" to userId,
            "session_id" to sessionId,
            "action_type" to actionType,
            "request_id" to UUID.randomUUID().toString(),
            "timestamp" to timestamp,
            "nonce" to UUID.randomUUID().toString(),
            "sdk_version" to "1.0.0",
            "payload_version" to "v1",
            "platform" to "ANDROID",
            "avg_key_interval_ms" to averageKeyIntervalMs(),
            "avg_touch_duration_ms" to averageTouchDurationMs(),
            "typing_speed_cps" to typingSpeedCps(),
            "tap_pressure_avg" to pressureAverage(),
            "tap_pressure_std" to pressureStdDev(),
            "error_count" to errorCount,
            "correction_count" to correctionCount,
            "hesitation_time_ms" to hesitationTimeMs(),
            "swipe_speed_avg" to swipeSpeedAvg(),
            "touch_precision_score" to touchPrecisionScore(),
            "device_orientation_changes" to deviceOrientationChanges,
            "session_duration_ms" to sessionDurationMs(),
        )
    }

    fun buildHeaders(payload: Map<String, Any?>, clientKey: String, signatureSecret: String): Map<String, String> {
        val canonicalPayload = canonicalJson(payload)
        val signature = hmacSha256Hex(signatureSecret, canonicalPayload)
        return mapOf(
            "X-Novaris-Client-Key" to clientKey,
            "X-Novaris-Signature" to signature,
        )
    }

    fun reset() {
        keyPressTimesMs.clear()
        touchDurationsMs.clear()
        touchPressures.clear()
        actionDurationsMs.clear()
        sessionStartedAtMs = null
        sessionEndedAtMs = null
        currentActionType = null
        currentActionStartedAtMs = null
        currentTouchDownAtMs = null
        currentTouchPressure = null
        errorCount = 0
        correctionCount = 0
        deviceOrientationChanges = 0
    }

    private fun averageKeyIntervalMs(): Double? {
        if (keyPressTimesMs.size < 2) return null
        val intervals = keyPressTimesMs.zipWithNext { previous, current -> (current - previous).toDouble() }
        return intervals.average()
    }

    private fun averageTouchDurationMs(): Double? {
        if (touchDurationsMs.isEmpty()) return null
        return touchDurationsMs.map { it.toDouble() }.average()
    }

    private fun typingSpeedCps(): Double {
        val interval = averageKeyIntervalMs() ?: return 0.0
        return if (interval <= 0.0) 0.0 else 1000.0 / interval
    }

    private fun pressureAverage(): Double? {
        if (touchPressures.isEmpty()) return null
        return touchPressures.map { it.toDouble() }.average()
    }

    private fun pressureStdDev(): Double? {
        if (touchPressures.size < 2) return if (touchPressures.isEmpty()) null else 0.0
        val average = pressureAverage() ?: return null
        val variance = touchPressures.fold(0.0) { acc, pressure ->
            val delta = pressure - average
            acc + delta * delta
        } / touchPressures.size
        return kotlin.math.sqrt(variance)
    }

    private fun hesitationTimeMs(): Double {
        if (actionDurationsMs.isEmpty()) return 0.0
        return actionDurationsMs.map { it.toDouble() }.average()
    }

    private fun swipeSpeedAvg(): Double {
        val sessionDuration = sessionDurationMs()
        if (sessionDuration <= 0.0) return 0.0
        return actionDurationsMs.size * 1000.0 / sessionDuration
    }

    private fun touchPrecisionScore(): Double {
        val pressureStd = pressureStdDev() ?: 0.0
        val penalty = (errorCount * 0.05) + (correctionCount * 0.02) + minOf(0.2, pressureStd * 0.1)
        return (1.0 - penalty).coerceIn(0.0, 1.0)
    }

    private fun sessionDurationMs(): Double {
        val startAtMs = sessionStartedAtMs ?: return 0.0
        val endAtMs = sessionEndedAtMs ?: SystemClock.elapsedRealtime()
        return (endAtMs - startAtMs).coerceAtLeast(0L).toDouble()
    }

    private fun canonicalJson(payload: Map<String, Any?>): String {
        // Signature légère uniquement: ce JSON canonique sera remplacé plus tard par une attestation forte.
        return JSONObject(TreeMap(payload)).toString()
    }

    private fun hmacSha256Hex(secret: String, message: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val digest = mac.doFinal(message.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}

