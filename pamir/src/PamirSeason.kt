package com.v2ray.ang.pamir

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.v2ray.ang.handler.MmkvManager
import java.util.Calendar
import kotlin.math.sin
import kotlin.random.Random

/**
 * Новогодний режим, как на mognu.app: сам включается у всех с 20 декабря по 10 января. Раньше его видно только на
 * телефоне, где 7 раз быстро нажали «О приложении» в настройках (ещё 7 нажатий выключают; запоминается в настройках
 * приложения). Наряд Могну — красная шапка набок поверх короны (PamirMascot.kt), на главном экране — снег (SnowLayer).
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

private class Flake(val x: Float, val y: Float, val r: Float, val v: Float, val a: Float, val ph: Float, val sw: Float)

/**
 * Light snow behind the screen content, the same as on mognu.app: up to 70 flakes falling and swaying, white on the dark
 * theme and lilac on the light one. Positions are computed from the frame time, so only the drawing re-runs.
 * The caller skips it when the system animations are off.
 */
@Composable
fun SnowLayer(modifier: Modifier = Modifier) {
    val dark = Pamir.colors.isDark
    val flakes = remember {
        List(60) {
            val r = 1.2f + Random.nextFloat() * 2.8f
            Flake(Random.nextFloat(), Random.nextFloat(), r, 18f + r * 14f + Random.nextFloat() * 12f,
                0.35f + Random.nextFloat() * 0.5f, Random.nextFloat() * 6.28f, 8f + Random.nextFloat() * 18f)
        }
    }
    val time by produceState(0f) {
        val start = withFrameNanos { it }
        while (true) withFrameNanos { value = (it - start) / 1_000_000_000f }
    }
    Canvas(modifier.fillMaxSize()) {
        val t = time
        val k = 1.dp.toPx()
        val w = size.width; val h = size.height
        val n = (w * h / (k * k) / 14000f).toInt().coerceIn(24, flakes.size)
        val color = if (dark) Color.White else Color(0xFF9C86F2)
        for (i in 0 until n) {
            val f = flakes[i]
            val span = h + 20 * k
            val y = ((f.y * span + f.v * k * t) % span) - 10 * k
            val x = f.x * w + sin(f.ph + t * 0.9f) * f.sw * k
            drawCircle(color.copy(alpha = if (dark) f.a else f.a * 0.7f), f.r * k, Offset(x, y))
        }
    }
}
