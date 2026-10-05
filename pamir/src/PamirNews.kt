package com.v2ray.ang.pamir

import android.content.Context
import android.util.Log
import com.v2ray.ang.handler.MmkvManager
import org.json.JSONArray
import org.json.JSONObject

/**
 * News from the admin panel (bot → "Новости"; the same GET /news the web cabinet shows).
 * The app shows the newest unseen one as a banner on the home screen; the background worker
 * notifies about a new one. Stored in the shared settings, so the UI and the worker see the same state.
 */
object PamirNews {
    const val EXTRA_NEWS = "pamir_news"
    private const val K_CACHE = "pamir_news_cache"
    private const val K_SEEN = "pamir_news_seen"
    private const val K_NOTIFIED = "pamir_news_notified"
    private const val NOTIFY_ID = 7313

    /** Blocking: fetches the list (newest first) and caches it; null when the server is unreachable. */
    fun fetch(proxyPort: Int? = null): List<JSONObject>? = runCatching {
        val arr = PamirApi.call("/news", proxyPort = proxyPort).optJSONArray("news") ?: JSONArray()
        val list = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optString("text").isNotBlank() }
            .sortedByDescending { order(it) }
        MmkvManager.encodeSettings(K_CACHE, JSONArray(list).toString())
        list
    }.onFailure { Log.w("Pamir", "news: ${it.message}") }.getOrNull()

    fun cached(): List<JSONObject> = runCatching {
        val arr = JSONArray(MmkvManager.decodeSettingsString(K_CACHE, "[]") ?: "[]")
        (0 until arr.length()).map { arr.getJSONObject(it) }
    }.getOrDefault(emptyList())

    /** The newest news the user has not opened yet, or null. */
    fun unseen(list: List<JSONObject>): JSONObject? =
        list.firstOrNull()?.takeIf { order(it) > MmkvManager.decodeSettingsString(K_SEEN, "").orEmpty() }

    fun markSeen(list: List<JSONObject>) {
        list.firstOrNull()?.let { MmkvManager.encodeSettings(K_SEEN, order(it)) }
    }

    /** Worker: one notification about the newest news. On the first run only remembers it (no flood of old news). */
    fun notifyNew(ctx: Context) {
        val newest = fetch()?.firstOrNull() ?: return
        val key = order(newest)
        val last = MmkvManager.decodeSettingsString(K_NOTIFIED, "").orEmpty()
        MmkvManager.encodeSettings(K_NOTIFIED, key)
        if (last.isEmpty() || key <= last) return
        val text = newest.optString("text").trim()
        val title = text.lineSequence().first().take(60)
        PamirWatch.notify(
            ctx, title, text, EXTRA_NEWS, "Открыть", NOTIFY_ID,
            channel = "pamir_news", channelName = "Новости Pamir VPN", channelDesc = "Новые серверы, акции и важные сообщения"
        )
    }

    /** Sort key: creation time, then id (both as the server sends them, ISO time sorts as text). */
    private fun order(n: JSONObject): String = n.optString("created_at") + "#" + n.optString("id").padStart(10, '0')

    /** "12 окт" style date for the list. */
    fun date(n: JSONObject): String {
        val raw = n.optString("created_at")
        val m = Regex("""(\d{4})-(\d{2})-(\d{2})""").find(raw) ?: return ""
        val months = listOf("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
        val mon = m.groupValues[2].toIntOrNull()?.let { months.getOrNull(it - 1) } ?: return ""
        return "${m.groupValues[3].trimStart('0')} $mon"
    }
}
