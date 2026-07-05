package com.novaris.sdk.example

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import org.json.JSONObject
import java.io.File
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.security.MessageDigest

class DeviceMetadataCollector {

    enum class DevicePlatform {
        ANDROID,
        IOS,
        WEB_MOCK,
    }

    data class DeviceSignals(
        val brand: String = Build.BRAND,
        val manufacturer: String = Build.MANUFACTURER,
        val model: String = Build.MODEL,
        val device: String = Build.DEVICE,
        val product: String = Build.PRODUCT,
        val hardware: String = Build.HARDWARE,
        val fingerprint: String = Build.FINGERPRINT,
        val osName: String = "Android",
        val osVersion: String = Build.VERSION.RELEASE,
        val sdkInt: Int = Build.VERSION.SDK_INT,
    )

    fun isEmulator(): Boolean {
        val fingerprint = Build.FINGERPRINT.lowercase()
        val model = Build.MODEL.lowercase()
        val manufacturer = Build.MANUFACTURER.lowercase()
        val hardware = Build.HARDWARE.lowercase()
        val product = Build.PRODUCT.lowercase()

        return fingerprint.contains("generic") ||
            model.contains("google_sdk") ||
            model.contains("emulator") ||
            model.contains("android sdk built for x86") ||
            manufacturer.contains("genymotion") ||
            hardware.contains("goldfish") ||
            hardware.contains("ranchu") ||
            hardware.contains("qemu") ||
            product.contains("sdk") ||
            product.contains("google_sdk") ||
            product.contains("sdk_x86") ||
            product.contains("vbox86p")
    }

    fun isRooted(): Boolean {
        val paths = listOf(
            "/system/bin/su",
            "/system/xbin/su",
            "/sbin/su",
            "/system/app/Superuser.apk",
        )
        val hasSuBinary = paths.any { File(it).exists() }
        val testKeys = Build.TAGS?.contains("test-keys") == true
        return hasSuBinary || testKeys
    }

    fun isVpnActive(context: Context): Boolean {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return false
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
    }

    fun generateDeviceHash(): String {
        val signals = DeviceSignals()
        val raw = listOf(
            signals.brand,
            signals.model,
            signals.manufacturer,
            signals.device,
            signals.hardware,
            signals.osVersion,
        ).joinToString("|")

        val digest = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }

    fun buildPayload(
        context: Context,
        userId: String,
        deviceId: String,
        appVersion: String? = null,
        sdkVersion: String = "1.0.0",
        payloadVersion: String = "v1",
        platform: DevicePlatform = DevicePlatform.ANDROID,
        language: String = "fr",
    ): JSONObject {
        val signals = DeviceSignals()
        val deviceHash = generateDeviceHash()

        // IP et pays peuvent aussi être enrichis côté backend à partir de la requête.
        return JSONObject().apply {
            put("user_id", userId)
            put("device_id", deviceId)
            put("brand", signals.brand)
            put("model", signals.model)
            put("os_name", signals.osName)
            put("os_version", signals.osVersion)
            put("app_version", appVersion ?: JSONObject.NULL)
            put("sdk_version", sdkVersion)
            put("payload_version", payloadVersion)
            put("platform", platform.name)
            put("is_rooted", isRooted())
            put("is_emulator", isEmulator())
            put("is_vpn", isVpnActive(context))
            put("is_proxy", false)
            put("ip_address", JSONObject.NULL)
            put("country", JSONObject.NULL)
            put("city", JSONObject.NULL)
            put("latitude", JSONObject.NULL)
            put("longitude", JSONObject.NULL)
            put("language", language)
            put("device_hash", deviceHash)
        }
    }

    fun generateSignature(payloadJson: String, signatureSecret: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        val keySpec = SecretKeySpec(signatureSecret.toByteArray(Charsets.UTF_8), "HmacSHA256")
        mac.init(keySpec)
        val digest = mac.doFinal(payloadJson.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}
