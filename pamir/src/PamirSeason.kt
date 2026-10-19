package com.v2ray.ang.pamir

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
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
 * приложения). Наряд Могну — красная шапка набок поверх короны (PamirMascot.kt), на главном экране — снег (SnowLayer),
 * на рабочем столе — иконка с шапкой (applyIcon).
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

    private val LINES = listOf("С наступающим! 🎄 Я уже в шапке", "Хо-хо-хо! Могну на связи 🎅",
        "Ёлку нарядил, интернет разогнал ✨", "Мандарины есть, скорость есть 🍊", "В этом году ты был хорошим. Наверное 😏",
        "Снег идёт — интернет летит ❄️", "Корона под шапкой, но я всё ещё король 👑")

    private fun hours(n: Int) = when {
        n % 10 == 1 && n % 100 != 11 -> "час"
        n % 10 in 2..4 && n % 100 !in 12..14 -> "часа"
        else -> "часов"
    }

    /**
     * Праздничная фраза Могну на текущий момент, как MognuNY.line на mognu.app: 31 декабря — отсчёт, в полночь и
     * 1 января — поздравление, на каникулах — про сериалы, в остальные дни — случайная из списка.
     */
    fun line(now: Calendar = Calendar.getInstance()): String {
        val m = now.get(Calendar.MONTH); val d = now.get(Calendar.DAY_OF_MONTH); val h = now.get(Calendar.HOUR_OF_DAY)
        val happy = "С Новым годом! 🎉 Пусть ничего не тормозит"
        return when {
            m == Calendar.DECEMBER && d == 31 -> when {
                h >= 23 -> happy
                h >= 17 -> "До Нового года ${23 - h} ${hours(23 - h)}! Успеешь всех могнуть 🎆"
                else -> "Последний день года — давай без тормозов 🥂"
            }
            m == Calendar.JANUARY && d == 1 -> if (h < 3) happy else "С Новым годом! Как самочувствие? 😅"
            m == Calendar.JANUARY && d in 2..10 -> "Каникулы — время сериалов. Я готов 🍿"
            else -> LINES.random()
        }
    }

    /**
     * Новогодняя иконка на рабочем столе: в режиме — вход «.pamir.PamirNewYear» (Могну в шапке), иначе обычный
     * «.pamir.PamirActivity» (см. манифест в brand.py). Сначала включается нужный, потом выключается второй, чтобы
     * иконка была всегда. DONT_KILL_APP — приложение не закрывается; лаунчер обновляет значок через пару секунд.
     * Вызывается при уходе приложения в фон, из фоновой задачи и сразу после 7 нажатий. На ТВ не трогаем.
     */
    fun applyIcon(ctx: Context) {
        if (PamirTv.isTv(ctx)) return
        runCatching {
            val want = compute()
            val pkg = PamirHome::class.java.`package`?.name ?: "com.v2ray.ang.pamir"
            val regular = ComponentName(ctx, "$pkg.PamirActivity")
            val ny = ComponentName(ctx, "$pkg.PamirNewYear")
            val pm = ctx.packageManager
            fun on(c: ComponentName, byDefault: Boolean) = when (pm.getComponentEnabledSetting(c)) {
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED -> true
                PackageManager.COMPONENT_ENABLED_STATE_DEFAULT -> byDefault
                else -> false
            }
            if (on(ny, false) == want && on(regular, true) == !want) return
            val (enable, disable) = if (want) ny to regular else regular to ny
            pm.setComponentEnabledSetting(enable, PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP)
            pm.setComponentEnabledSetting(disable, PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP)
            Log.i("Pamir", "launcher icon: ${if (want) "new year" else "regular"}")
        }.onFailure { Log.w("Pamir", "launcher icon switch failed: ${it.message}") }
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
