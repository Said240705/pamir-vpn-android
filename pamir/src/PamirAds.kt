package com.v2ray.ang.pamir

import android.content.Context
import android.util.Log
import com.v2ray.ang.AngApplication
import com.v2ray.ang.dto.V2rayConfig
import com.v2ray.ang.handler.MmkvManager
import java.io.File
import java.io.RandomAccessFile

/**
 * «Без рекламы»: рекламные и следящие адреса (geosite:category-ads-all, список уже лежит в geosite.dat ядра)
 * уходят в отдельный выход-«чёрную дыру» adblock, а не в общий block — так их можно сосчитать.
 *
 * Не через общий block нарочно: для block-правил v2rayNG подменяет DNS на 127.0.0.1, и такие запросы до ядра не
 * доходят — считать было бы нечего. Здесь имя резолвится как обычно, ядро узнаёт адрес по SNI/HTTP (sniffing) и
 * отбрасывает соединение.
 *
 * Счётчик: ядро пишет журнал соединений в файл приложения (только пока функция включена); сторож (PamirWatch,
 * процесс ядра) раз в минуту считает строки «… adblock]» и сразу очищает файл. Журнал не покидает телефон,
 * а копится не дольше минуты.
 */
object PamirAds {
    const val K_ENABLED = "pamir_adblock"
    private const val K_TOTAL = "pamir_ads_total"
    private const val K_WEEK = "pamir_ads_week"
    private const val K_WEEK_START = "pamir_ads_week_start"
    const val TAG = "adblock"
    private const val LIST = "geosite:category-ads-all"
    private const val WEEK_MS = 7 * 86_400_000L

    fun enabled(): Boolean = MmkvManager.decodeSettingsBool(K_ENABLED, false)

    fun setEnabled(on: Boolean) = MmkvManager.encodeSettings(K_ENABLED, on)

    private fun logFile(ctx: Context): File = File(ctx.filesDir, "pamir_access.log")

    /** Called by CoreConfigManager (patched in brand.py) for every core config it builds. */
    fun apply(config: V2rayConfig) {
        if (!enabled()) return
        runCatching {
            if (config.outbounds.none { it.tag == TAG }) {
                config.outbounds.add(V2rayConfig.OutboundBean(tag = TAG, protocol = "blackhole", mux = null))
            }
            val rules = config.routing.rules
            // after the core's own DNS rules (they carry an inboundTag), before every user rule
            val at = rules.indexOfFirst { it.inboundTag.isNullOrEmpty() }.let { if (it < 0) rules.size else it }
            rules.add(at, V2rayConfig.RoutingBean.RulesBean(domain = listOf(LIST), outboundTag = TAG))
            config.log.access = logFile(AngApplication.application).absolutePath
        }.onFailure { Log.w("Pamir", "adblock config: ${it.message}") }
    }

    /** Counts blocked connections written since the last call and empties the log. Daemon process. */
    fun collect(ctx: Context) {
        val f = logFile(ctx)
        if (!f.exists() || f.length() == 0L) return
        runCatching {
            var n = 0
            RandomAccessFile(f, "rw").use { raf ->
                f.forEachLine { if (it.contains("$TAG]")) n++ }
                raf.setLength(0)
            }
            if (n > 0) add(n)
        }.onFailure { Log.w("Pamir", "adblock count: ${it.message}") }
    }

    private fun add(n: Int, now: Long = System.currentTimeMillis()) {
        MmkvManager.encodeSettings(K_TOTAL, MmkvManager.decodeSettingsLong(K_TOTAL, 0L) + n)
        val start = MmkvManager.decodeSettingsLong(K_WEEK_START, 0L)
        if (now - start > WEEK_MS) {
            MmkvManager.encodeSettings(K_WEEK_START, now)
            MmkvManager.encodeSettings(K_WEEK, n.toLong())
        } else {
            MmkvManager.encodeSettings(K_WEEK, MmkvManager.decodeSettingsLong(K_WEEK, 0L) + n)
        }
    }

    fun total(): Long = MmkvManager.decodeSettingsLong(K_TOTAL, 0L)

    /** Blocked in the current 7-day window; 0 when the window has passed without new ones. */
    fun week(now: Long = System.currentTimeMillis()): Long =
        if (now - MmkvManager.decodeSettingsLong(K_WEEK_START, 0L) > WEEK_MS) 0L else MmkvManager.decodeSettingsLong(K_WEEK, 0L)

    /** «1 284 рекламы» — the number with a space between thousands and the right word form. */
    fun phrase(n: Long): String {
        val num = String.format(java.util.Locale("ru"), "%,d", n).replace(',', ' ').replace(' ', ' ')
        val m10 = n % 10; val m100 = n % 100
        val word = when {
            m10 == 1L && m100 != 11L -> "рекламу"
            m10 in 2..4 && m100 !in 12..14 -> "рекламы"
            else -> "реклам"
        }
        return "$num $word"
    }
}
