package com.v2ray.ang.pamir

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.v2ray.ang.handler.MmkvManager
import java.util.Calendar

/**
 * Новогодний режим, как на mognu.app: сам включается у всех с 20 декабря по 10 января. Раньше его видно только на
 * телефоне, где 7 раз быстро нажали «О приложении» в настройках (ещё 7 нажатий выключают; запоминается в настройках
 * приложения). Наряд Могну — красная шапка с помпоном и маленькой золотой короной (PamirMascot.kt).
 */
object PamirSeason {
    private const val K_NY = "pamir_ny"   // "1" — включён вручную, "0" — выключен вручную, нет — по дате

    var newYear by mutableStateOf(compute())
        private set

    private fun inSeason(): Boolean {
        val c = Calendar.getInstance()
        val m = c.get(Calendar.MONTH); val d = c.get(Calendar.DAY_OF_MONTH)
        return (m == Calendar.DECEMBER && d >= 20) || (m == Calendar.JANUARY && d <= 10)
    }

    private fun compute(): Boolean = when (runCatching { MmkvManager.decodeSettingsString(K_NY) }.getOrNull()) {
        "1" -> true
        "0" -> false
        else -> inSeason()
    }

    /** Переключает режим на этом телефоне и возвращает новое состояние. */
    fun toggle(): Boolean {
        val next = !newYear
        MmkvManager.encodeSettings(K_NY, if (next) "1" else "0")
        newYear = next
        return next
    }
}
