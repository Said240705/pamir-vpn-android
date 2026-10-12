package com.v2ray.ang.pamir

import android.util.Log
import com.v2ray.ang.handler.MmkvManager
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Site/API mirrors, so one blocked domain never cuts the app off: the same site and API answer on every host.
 * Order: the host that worked last, then the built-in list, then hosts the server added later (hosts.json).
 * [PamirApi.call] walks the list on connection failures; links (cabinet, payment return, updates) use [web].
 */
object PamirHosts {
    /** Built-in mirrors; the first one is the brand domain. */
    val DEFAULT = listOf("https://mognu.app", "https://mognu.net", "https://app.pamirlink.ru")
    private const val K_GOOD = "pamir_host_good"
    private const val K_EXTRA = "pamir_hosts_extra"
    private const val MAX_EXTRA = 8

    /** Every known host, the last working one first. */
    fun ordered(): List<String> {
        val good = MmkvManager.decodeSettingsString(K_GOOD, "").orEmpty()
        val all = (DEFAULT + extra()).distinct()
        return if (good in all) listOf(good) + (all - good) else all
    }

    /** Preferred host for links shown to the user and pages opened in the browser. */
    fun current(): String = ordered().first()

    /** Absolute address on the preferred host, e.g. web("/pay-return.html"). */
    fun web(path: String): String = current() + path

    /** True for any of our hosts (payment return page, deep links back from the site). */
    fun isOurs(url: String): Boolean = ordered().any { url.startsWith(it) }

    fun markGood(host: String) {
        if (MmkvManager.decodeSettingsString(K_GOOD, "") != host) MmkvManager.encodeSettings(K_GOOD, host)
    }

    private fun extra(): List<String> = runCatching {
        val a = JSONArray(MmkvManager.decodeSettingsString(K_EXTRA, "[]") ?: "[]")
        (0 until a.length()).map { a.getString(it) }
    }.getOrDefault(emptyList())

    /** Only plain https origins: no paths, no credentials, nothing the server could turn into a redirect elsewhere. */
    private fun valid(h: String): Boolean = Regex("""^https://[a-z0-9.-]+\.[a-z]{2,}$""").matches(h)

    /**
     * Blocking: fetch hosts.json ({"hosts": ["https://…", …]}) from the first host that answers and keep the new ones.
     * Called by the 6-hour worker and on app start; failures keep the current list.
     */
    fun refresh(proxyPort: Int? = null) {
        for (h in ordered()) {
            val list = runCatching { fetch("$h/hosts.json", proxyPort) }
                .onFailure { Log.w("Pamir", "hosts $h: ${it.message}") }.getOrNull() ?: continue
            val fresh = list.filter(::valid).filter { it !in DEFAULT }.distinct().take(MAX_EXTRA)
            MmkvManager.encodeSettings(K_EXTRA, JSONArray(fresh).toString())
            markGood(h)
            return
        }
    }

    private fun fetch(url: String, proxyPort: Int?): List<String> {
        val u = URL(url)
        val c = (if (proxyPort != null) u.openConnection(java.net.Proxy(java.net.Proxy.Type.HTTP, java.net.InetSocketAddress("127.0.0.1", proxyPort)))
        else u.openConnection()) as HttpURLConnection
        c.connectTimeout = 6000; c.readTimeout = 6000
        c.setRequestProperty("Cache-Control", "no-cache")
        try {
            if (c.responseCode != 200) error("HTTP ${c.responseCode}")
            val a = JSONObject(c.inputStream.bufferedReader().use { it.readText() }).getJSONArray("hosts")
            return (0 until a.length()).map { a.getString(it).trim().trimEnd('/') }
        } finally {
            c.disconnect()
        }
    }
}
