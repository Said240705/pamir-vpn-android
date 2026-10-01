package com.v2ray.ang.pamir

import android.content.Context
import android.os.Build
import android.util.Log
import com.v2ray.ang.handler.MmkvManager
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

/** Small client for the cabinet API (https://app.pamirlink.ru/api). */
object PamirApi {
    const val BASE = "https://app.pamirlink.ru/api"
    private const val K_TOKEN = "pamir_api_token"

    class ApiError(val code: Int, message: String) : Exception(message)

    var token: String?
        get() = MmkvManager.decodeSettingsString(K_TOKEN, "")?.takeIf { it.isNotBlank() }
        set(v) {
            MmkvManager.encodeSettings(K_TOKEN, v ?: "")
        }

    /**
     * Blocking call, run on Dispatchers.IO.
     * [proxyPort] — local HTTP proxy of the running VPN core (the app itself is excluded from the tunnel,
     * so under "white lists" the server is reachable only through it). Falls back to a direct request.
     */
    fun call(path: String, method: String = "GET", body: JSONObject? = null, auth: Boolean = true, proxyPort: Int? = null): JSONObject {
        val ports: List<Int?> = if (proxyPort != null) listOf(proxyPort, null) else listOf(null)
        var last: Exception? = null
        for (port in ports) {
            try {
                return once(path, method, body, auth, port)
            } catch (e: ApiError) {
                throw e
            } catch (e: IOException) {
                last = e
                Log.w("Pamir", "api $path via ${port ?: "direct"}: ${e.message}")
            }
        }
        throw ApiError(0, "Нет связи с сервером. Проверьте интернет или включите VPN")
            .also { it.initCause(last) }
    }

    private fun once(path: String, method: String, body: JSONObject?, auth: Boolean, port: Int?): JSONObject {
        val url = URL(BASE + path)
        val conn = (if (port != null) url.openConnection(Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", port)))
        else url.openConnection()) as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 20_000
        conn.requestMethod = method
        conn.setRequestProperty("Accept", "application/json")
        conn.setRequestProperty("Cache-Control", "no-cache")
        conn.setRequestProperty("User-Agent", "PamirVPN-Android")
        if (auth) token?.let { conn.setRequestProperty("Authorization", "Bearer $it") }
        if (body != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.outputStream.use { it.write(body.toString().toByteArray()) }
        }
        val code = conn.responseCode
        val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
            ?.bufferedReader()?.use { it.readText() }.orEmpty()
        conn.disconnect()
        if (code !in 200..299) {
            val detail = runCatching { JSONObject(text).opt("detail") }.getOrNull()
            val msg = when (detail) {
                is String -> detail
                is JSONArray -> "Проверьте введённые данные"
                else -> "Ошибка сервера ($code)"
            }
            throw ApiError(code, msg)
        }
        return if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    fun deviceName(): String =
        listOfNotNull(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim()

    fun hwid(): String = MmkvManager.decodeSettingsString("pamir_hwid", "") ?: ""

    fun appVersion(ctx: Context): String =
        runCatching { ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName }.getOrNull() ?: ""

    fun report(ctx: Context, kind: String, text: String, log: String, proxyPort: Int? = null, contact: String = "") {
        call(
            "/app/report", "POST",
            JSONObject()
                .put("kind", kind).put("text", text.take(1500)).put("log", log.takeLast(150_000))
                .put("version", appVersion(ctx)).put("device", deviceName())
                .put("android", Build.VERSION.RELEASE ?: "").put("hwid", hwid().take(12))
                .put("contact", contact.take(80)),
            auth = true, proxyPort = proxyPort
        )
    }

    /** Recent log lines of this app (an app may read only its own logs). */
    fun recentLog(): String = runCatching {
        val p = Runtime.getRuntime().exec(arrayOf("logcat", "-d", "-t", "600", "-v", "time"))
        p.inputStream.bufferedReader().use { it.readText() }
    }.getOrDefault("")
}

/** Saves uncaught exceptions to files; they are sent the next time the app is opened. */
object PamirCrash {
    private const val DIR = "pamir_crash"

    fun install(ctx: Context) {
        val app = ctx.applicationContext
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, e ->
            runCatching {
                val dir = File(app.filesDir, DIR).apply { mkdirs() }
                val proc = runCatching { File("/proc/self/cmdline").readText().trim('\u0000', ' ') }.getOrDefault("?")
                val text = buildString {
                    append("process: ").append(proc).append('\n')
                    append("thread: ").append(thread.name).append('\n')
                    append("time: ").append(java.util.Date()).append('\n')
                    append("version: ").append(PamirApi.appVersion(app)).append("\n\n")
                    append(android.util.Log.getStackTraceString(e))
                }
                File(dir, "crash_${System.currentTimeMillis()}.txt").writeText(text)
            }
            prev?.uncaughtException(thread, e)
        }
    }

    /** Sends saved crash reports (max 3 per launch). Run on Dispatchers.IO. */
    fun sendPending(ctx: Context, proxyPort: Int?) {
        val dir = File(ctx.filesDir, DIR)
        val files = dir.listFiles()?.sortedBy { it.name } ?: return
        files.filter { System.currentTimeMillis() - it.lastModified() > 7L * 86_400_000 }.forEach { it.delete() }
        files.filter { it.exists() }.take(3).forEach { f ->
            runCatching {
                val log = f.readText()
                val title = log.lineSequence().dropWhile { !it.contains("Exception") && !it.contains("Error") }
                    .firstOrNull()?.take(200) ?: "Падение приложения"
                PamirApi.report(ctx, "crash", title, log, proxyPort)
                f.delete()
            }.onFailure { Log.w("Pamir", "crash report not sent: ${it.message}") }
        }
    }
}
