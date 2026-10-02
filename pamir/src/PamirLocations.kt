package com.v2ray.ang.pamir

import com.v2ray.ang.handler.MmkvManager
import org.json.JSONArray
import org.json.JSONObject

/**
 * Состояние локаций со страницы статуса (GET /topup/public/server-status, без входа).
 * Хранится в общих настройках, чтобы его видел и экран серверов, и автосмена в процессе :daemon.
 * Локация в ответе называется так же, как подключение в панели, а сервер в подписке — так же
 * плюс, возможно, приписки (имя клиента, оставшиеся дни), поэтому сравниваем по буквам и цифрам
 * и берём самое длинное совпадение («LTE Обход 2», а не «LTE Обход»).
 */
object PamirLocations {
    private const val K_STATUS = "pamir_loc_status"
    private const val K_STATUS_AT = "pamir_loc_status_at"

    /** Статусу старше этого не верим: локация могла уже починиться. */
    private const val MAX_AGE_MS = 30 * 60 * 1000L

    /** Сохраняет ответ сервера: [{"name": "🇪🇸 Испания -1", "status": "up"}, ...]. */
    fun save(servers: JSONArray) {
        val map = JSONObject()
        for (i in 0 until servers.length()) {
            val s = servers.optJSONObject(i) ?: continue
            val key = norm(s.optString("name"))
            if (key.isNotEmpty()) map.put(key, s.optString("status", "unknown"))
        }
        MmkvManager.encodeSettings(K_STATUS, map.toString())
        MmkvManager.encodeSettings(K_STATUS_AT, System.currentTimeMillis())
    }

    /** "up" / "down" / "unknown" для сервера с такими remarks, или null, если данных нет. */
    fun statusFor(remarks: String?): String? {
        val at = MmkvManager.decodeSettingsLong(K_STATUS_AT, 0L)
        if (System.currentTimeMillis() - at > MAX_AGE_MS) return null
        val map = runCatching { JSONObject(MmkvManager.decodeSettingsString(K_STATUS, null) ?: return null) }.getOrNull() ?: return null
        val name = norm(remarks.orEmpty())
        if (name.isEmpty()) return null
        var best: String? = null
        for (key in map.keys()) {
            if (name.contains(key) && (best == null || key.length > best.length)) best = key
        }
        return best?.let { map.optString(it) }
    }

    fun isDown(remarks: String?): Boolean = statusFor(remarks) == "down"

    private fun norm(s: String): String = s.lowercase().filter { it.isLetterOrDigit() }
}
