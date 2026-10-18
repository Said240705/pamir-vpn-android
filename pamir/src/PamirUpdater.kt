package com.v2ray.ang.pamir

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Build
import android.util.Log
import androidx.core.content.FileProvider
import com.v2ray.ang.AppConfig
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.handler.SettingsManager
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import java.net.URL

/**
 * App updates in one tap: where the new build is (GitHub releases and the site mirror), downloading it — through the
 * running VPN first, because the app itself is outside the tunnel and under mobile «white lists» GitHub and our site
 * are reachable only through it — and, in the background worker, getting it ready on Wi-Fi or another unmetered
 * network and posting «Mognu <version> готов — нажми, чтобы установить». The person still confirms the system
 * installer: nothing is installed without them.
 */
object PamirUpdater {
    /** A published build: version and where its APK for this device can be downloaded. */
    class Source(val version: String, val url: String, val minVersion: String)

    const val EXTRA_INSTALL = "pamir_install_update"
    private const val NOTIFY_ID = 4712
    private const val K_NOTIFIED_VERSION = "pamir_upd_notified_version"
    private const val K_NOTIFIED_AT = "pamir_upd_notified_at"
    private const val K_NOTIFIED_COUNT = "pamir_upd_notified_count"
    /** A ready update is announced at most this many times, at least this far apart. */
    private const val MAX_REMINDERS = 3
    private const val REMIND_EVERY_MS = 2 * 86_400_000L

    private val GITHUB_LATEST = AppConfig.APP_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"

    fun prefersArm64() = Build.SUPPORTED_ABIS.contains("arm64-v8a")

    /** The local HTTP port of the running VPN core, or null when nothing listens there (VPN off). */
    fun livePort(): Int? {
        val port = runCatching { SettingsManager.getHttpPort() }.getOrNull()?.takeIf { it > 0 } ?: return null
        return runCatching { Socket().use { it.connect(InetSocketAddress("127.0.0.1", port), 300) }; port }.getOrNull()
    }

    private fun open(url: String, proxyPort: Int?, connectMs: Int, readMs: Int): HttpURLConnection {
        val u = URL(url)
        val c = (if (proxyPort != null) u.openConnection(Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)))
        else u.openConnection()) as HttpURLConnection
        c.connectTimeout = connectMs; c.readTimeout = readMs
        c.setRequestProperty("Cache-Control", "no-cache")
        return c
    }

    /** GET through the VPN first, then directly. */
    private fun get(url: String, proxyPort: Int?, accept: String? = null): String {
        var last: Exception? = null
        for (port in listOfNotNull(proxyPort) + listOf<Int?>(null)) {
            try {
                val c = open(url, port, 6000, 8000)
                if (accept != null) c.setRequestProperty("Accept", accept)
                try {
                    if (c.responseCode != 200) throw IOException("HTTP ${c.responseCode}")
                    return c.inputStream.bufferedReader().use { it.readText() }
                } finally {
                    c.disconnect()
                }
            } catch (e: Exception) {
                last = e
            }
        }
        throw last ?: IOException("no route")
    }

    /** GitHub releases: fixed-name copies (pamir-vpn.apk, pamir-vpn-universal.apk) or the versioned APKs. */
    fun fromGithub(proxyPort: Int?): Source? {
        val o = JSONObject(get(GITHUB_LATEST, proxyPort, "application/vnd.github+json"))
        val v = o.optString("tag_name").removePrefix("v")
        val assets = o.optJSONArray("assets") ?: return null
        val urls = (0 until assets.length()).associate { assets.getJSONObject(it).let { a -> a.optString("name") to a.optString("browser_download_url") } }
        fun pick(fixed: String, suffix: String) = urls[fixed] ?: urls.entries.firstOrNull { it.key.endsWith(suffix) }?.value
        val url = (if (prefersArm64()) pick("pamir-vpn.apk", "_arm64-v8a.apk") else null) ?: pick("pamir-vpn-universal.apk", "_universal.apk")
        // The build workflow writes "<!-- pamir-min-version: 1.6.1 -->" into the release notes.
        val min = Regex("""pamir-min-version:\s*([\d.]+)""").find(o.optString("body"))?.groupValues?.get(1).orEmpty()
        return if (v.isNotBlank() && url != null) Source(v, url, min) else null
    }

    /** The site mirror (download/android.json) — the first host that answers, the Yandex CDN one included. */
    fun fromSite(proxyPort: Int?): Source? {
        for (h in PamirHosts.ordered()) {
            val o = runCatching { JSONObject(get("$h/download/android.json", proxyPort)) }.getOrNull() ?: continue
            val v = o.optString("version")
            val abi = if (prefersArm64() && o.has("arm64-v8a")) "arm64-v8a" else "universal"
            val file = o.optJSONObject(abi)?.optString("file") ?: "pamir-vpn-universal.apk"
            return if (v.isNotBlank()) Source(v, "$h/download/$file", o.optString("min_version")) else null
        }
        return null
    }

    private fun dir(ctx: Context) = File(ctx.cacheDir, "update").apply { mkdirs() }
    private fun apkFor(ctx: Context, version: String) = File(dir(ctx), "mognu-$version.apk")

    /**
     * Downloads [url] as the APK of [version]: through the VPN first, then directly; written to a temp file and moved
     * into place only when complete and checked (our package, that version). [onProgress] gets 0–100.
     */
    fun download(ctx: Context, url: String, version: String, proxyPort: Int?, onProgress: (Int) -> Unit = {}): File? {
        val target = apkFor(ctx, version)
        if (isValid(ctx, target, version)) return target
        for (port in listOfNotNull(proxyPort) + listOf<Int?>(null)) {
            val part = File(dir(ctx), "mognu-$version.part")
            try {
                val c = open(url, port, 10_000, 20_000)
                try {
                    if (c.responseCode != 200) throw IOException("HTTP ${c.responseCode}")
                    val total = c.contentLengthLong
                    var done = 0L
                    var shown = -1
                    c.inputStream.use { input ->
                        part.outputStream().use { out ->
                            val buf = ByteArray(64 * 1024)
                            while (true) {
                                val n = input.read(buf)
                                if (n < 0) break
                                out.write(buf, 0, n)
                                done += n
                                if (total > 0) {
                                    val pr = (done * 100 / total).toInt()
                                    if (pr != shown) { shown = pr; onProgress(pr) }
                                }
                            }
                        }
                    }
                    if (total > 0 && done != total) throw IOException("incomplete download: $done of $total")
                } finally {
                    c.disconnect()
                }
                if (!isValid(ctx, part, version)) throw IOException("not our APK $version")
                target.delete()
                if (!part.renameTo(target)) throw IOException("cannot keep the APK")
                return target
            } catch (e: Exception) {
                part.delete()
                Log.w("Pamir", "update $version via ${port ?: "direct"}: ${e.message}")
            }
        }
        return null
    }

    /**
     * The file is a complete APK of this app with [version]. The signature is checked by the system installer
     * itself: an update signed with another key is refused, so it cannot replace the app.
     */
    private fun isValid(ctx: Context, file: File, version: String): Boolean {
        if (!file.isFile || file.length() < 1_000_000) return false
        val info = archiveInfo(ctx.packageManager, file.path) ?: return false
        return info.packageName == ctx.packageName && info.versionName == version
    }

    // getPackageArchiveInfo(String, Int) is deprecated from API 33 (Android 13) in favour of the PackageInfoFlags
    // overload, which does not exist below it; minSdk is 24. Remove the old branch when minSdk reaches 33.
    @Suppress("DEPRECATION")
    private fun archiveInfo(pm: PackageManager, path: String): PackageInfo? = runCatching {
        if (Build.VERSION.SDK_INT >= 33) pm.getPackageArchiveInfo(path, PackageManager.PackageInfoFlags.of(0))
        else pm.getPackageArchiveInfo(path, 0)
    }.getOrNull()

    /** The checked APK of [version] if it is already downloaded. */
    fun ready(ctx: Context, version: String): File? = apkFor(ctx, version).takeIf { isValid(ctx, it, version) }

    /** Opens the system installer for [file]; false when the installer could not be opened. */
    fun install(ctx: Context, file: File): Boolean = runCatching {
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.cache", file)
        ctx.startActivity(
            Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        true
    }.onFailure { Log.w("Pamir", "update installer: ${it.message}") }.getOrDefault(false)

    private fun installedVersion(ctx: Context): String =
        runCatching { ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName }.getOrNull().orEmpty()

    /** Removes downloaded builds other than [keep] (an older ready one, a broken partial file). */
    private fun cleanup(ctx: Context, keep: String?) {
        dir(ctx).listFiles()?.forEach { f ->
            if (keep == null || f.name != "mognu-$keep.apk") f.delete()
        }
    }

    /**
     * Background worker step: find the newest build, download it on an unmetered network (Wi-Fi, or a VPN over
     * Wi-Fi — the VPN reports the network under it), and announce it once ready; reminders are rare.
     */
    fun background(ctx: Context) {
        val current = installedVersion(ctx)
        if (current.isBlank()) return
        val port = livePort()
        val found = listOfNotNull(
            runCatching { fromGithub(port) }.onFailure { Log.w("Pamir", "bg update github: ${it.message}") }.getOrNull(),
            runCatching { fromSite(port) }.onFailure { Log.w("Pamir", "bg update site: ${it.message}") }.getOrNull(),
        )
        val best = found.map { it.version }.fold(current) { acc, v -> if (PamirWatch.versionNewer(v, acc)) v else acc }
        if (!PamirWatch.versionNewer(best, current)) {
            cleanup(ctx, null)
            return
        }
        var file = ready(ctx, best)
        if (file == null) {
            val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            if (cm.isActiveNetworkMetered) return   // on mobile data the in-app banner downloads it on request
            cleanup(ctx, null)
            file = found.filter { it.version == best }.firstNotNullOfOrNull { download(ctx, it.url, best, port) } ?: return
        }
        announce(ctx, best)
    }

    private fun announce(ctx: Context, version: String) {
        val now = System.currentTimeMillis()
        val sameVersion = MmkvManager.decodeSettingsString(K_NOTIFIED_VERSION, "") == version
        val count = if (sameVersion) MmkvManager.decodeSettingsInt(K_NOTIFIED_COUNT, 0) else 0
        if (sameVersion && (count >= MAX_REMINDERS || now - MmkvManager.decodeSettingsLong(K_NOTIFIED_AT, 0L) < REMIND_EVERY_MS)) return
        PamirWatch.notify(
            ctx, "Mognu $version готов 👑", "Обновление уже скачано — нажми, чтобы установить. Это пара секунд.",
            EXTRA_INSTALL, "Установить", NOTIFY_ID,
            channel = "pamir_updates", channelName = "Обновления приложения", channelDesc = "Новая версия Mognu готова к установке",
        )
        MmkvManager.encodeSettings(K_NOTIFIED_VERSION, version)
        MmkvManager.encodeSettings(K_NOTIFIED_COUNT, count + 1)
        MmkvManager.encodeSettings(K_NOTIFIED_AT, now)
    }

    /** The version the last «готов» notification was about, if any. */
    fun announcedVersion(): String? = MmkvManager.decodeSettingsString(K_NOTIFIED_VERSION, "")?.takeIf { it.isNotBlank() }

    /** The person opened the update: the reminder is no longer needed. */
    fun dismiss(ctx: Context) {
        runCatching { (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).cancel(NOTIFY_ID) }
    }
}
