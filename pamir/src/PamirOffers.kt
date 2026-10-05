package com.v2ray.ang.pamir

import android.content.Context
import android.util.Log
import com.v2ray.ang.handler.MmkvManager
import org.json.JSONObject

/**
 * Comeback offer for an expired subscription ("последний шанс", GET /topup/last-chance-offer — the same
 * offer the web cabinet shows: a discount code with a deadline) and the card-binding prompt state.
 */
object PamirOffers {
    const val EXTRA_OFFER = "pamir_offer"
    private const val K_NOTIFIED = "pamir_offer_notified"
    private const val K_PROMO = "pamir_active_promo"
    private const val K_CARD_NEVER = "pamir_card_prompt_never"
    private const val NOTIFY_ID = 7314

    /** Blocking: the current offer, or null (none, not signed in, or no connection). */
    fun fetch(proxyPort: Int? = null): JSONObject? {
        if (PamirApi.token == null) return null
        return runCatching { PamirApi.call("/topup/last-chance-offer", proxyPort = proxyPort) }
            .onFailure { Log.w("Pamir", "offer: ${it.message}") }.getOrNull()
            ?.takeIf { it.optBoolean("available") && it.optString("code").isNotBlank() }
    }

    /** Worker: one notification per offer code. */
    fun notifyNew(ctx: Context) {
        val o = fetch() ?: return
        val code = o.optString("code")
        if (MmkvManager.decodeSettingsString(K_NOTIFIED, "") == code) return
        MmkvManager.encodeSettings(K_NOTIFIED, code)
        val pct = o.optInt("discount_percent")
        PamirWatch.notify(
            ctx, "Скидка $pct% на продление Pamir VPN",
            "Подписка закончилась — вернитесь со скидкой $pct%. Предложение действует недолго.",
            EXTRA_OFFER, "Забрать скидку", NOTIFY_ID
        )
    }

    /** Discount remembered after applying an offer code: percent while it lasts (server applies it at checkout). */
    fun activePromoPercent(): Int? = runCatching {
        val o = JSONObject(MmkvManager.decodeSettingsString(K_PROMO, "") ?: return null)
        o.optInt("percent").takeIf { it > 0 && System.currentTimeMillis() < o.optLong("until") }
    }.getOrNull()

    fun rememberPromo(percent: Int, until: Long) {
        MmkvManager.encodeSettings(K_PROMO, JSONObject().put("percent", percent).put("until", until).toString())
    }

    fun clearPromo() = MmkvManager.encodeSettings(K_PROMO, "")

    /** "2026-10-06 18:00:00" (UTC, as the server sends it) → epoch millis, 0 if unknown. */
    fun parseUtc(raw: String): Long = runCatching {
        val f = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US)
        f.timeZone = java.util.TimeZone.getTimeZone("UTC")
        f.parse(raw.replace('T', ' ').take(19))!!.time
    }.getOrDefault(0L)

    var cardPromptNever: Boolean
        get() = MmkvManager.decodeSettingsBool(K_CARD_NEVER, false)
        set(v) { MmkvManager.encodeSettings(K_CARD_NEVER, v) }
}
