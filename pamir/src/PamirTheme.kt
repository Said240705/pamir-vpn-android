package com.v2ray.ang.pamir

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Design tokens of the Pamir UI. Screens never use raw colors, sizes or text styles:
// everything goes through Pamir.colors, PamirType, Gap and Radius.

/** Palette of one theme. `accent` is the brand lime (violet in the light theme) used for fills; `accentText` is the same hue tuned for text/icons on surfaces. */
@Immutable
data class PamirColors(
    val isDark: Boolean,
    val bg: Color,
    val surface: Color,
    val surfaceHigh: Color,
    val sheet: Color,
    val line: Color,
    val track: Color,
    val accent: Color,
    val accentDeep: Color,
    val accentText: Color,
    val onAccent: Color,
    val accentSoft: Color,
    val text: Color,
    val textDim: Color,
    val warn: Color,
    val warnSoft: Color,
    val danger: Color,
    val dangerSoft: Color,
    val info: Color,
)

val PamirDark = PamirColors(
    isDark = true,
    bg = Color(0xFF1E1640),
    surface = Color(0xFF2A2058),
    surfaceHigh = Color(0xFF352A68),
    sheet = Color(0xFF241B4C),
    line = Color(0x1AFFFFFF),
    track = Color(0xFF453A80),
    accent = Color(0xFFC8FF2E),
    accentDeep = Color(0xFFA3E000),
    accentText = Color(0xFFC8FF2E),
    onAccent = Color(0xFF0A0A10),
    accentSoft = Color(0x1FC8FF2E),
    text = Color(0xFFFFFFFF),
    textDim = Color(0xFFB9B2D9),
    warn = Color(0xFFFFC93C),
    warnSoft = Color(0xFF3A2C3A),
    danger = Color(0xFFFF7A7A),
    dangerSoft = Color(0xFF3D1F3C),
    info = Color(0xFFA98BFF),
)

/** Light theme: violet carries the accent — lime text is unreadable on white. */
val PamirLight = PamirColors(
    isDark = false,
    bg = Color(0xFFF4F3F8),
    surface = Color(0xFFFFFFFF),
    surfaceHigh = Color(0xFFECEAF4),
    sheet = Color(0xFFFFFFFF),
    line = Color(0x14000000),
    track = Color(0xFFDDDAE8),
    accent = Color(0xFF6A3DF5),
    accentDeep = Color(0xFF5428E0),
    accentText = Color(0xFF5A2EE6),
    onAccent = Color(0xFFFFFFFF),
    accentSoft = Color(0x1F6A3DF5),
    text = Color(0xFF12111A),
    textDim = Color(0xFF5F5C72),
    warn = Color(0xFFB8700F),
    warnSoft = Color(0xFFFFF3E0),
    danger = Color(0xFFD23B3B),
    dangerSoft = Color(0xFFFDECEA),
    info = Color(0xFF6A3DF5),
)

/** Type scale. Nothing smaller than 12sp, row titles 15sp, secondary lines 13sp. */
object PamirType {
    val hero = TextStyle(fontFamily = MognuDisplay, fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Black)
    val title = TextStyle(fontFamily = MognuDisplay, fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.ExtraBold)
    /** Brand name and the word on the power button. */
    val brand = TextStyle(fontFamily = MognuDisplay, fontSize = 18.sp, lineHeight = 22.sp, fontWeight = FontWeight.Black)
    val headline = TextStyle(fontFamily = MognuText, fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.ExtraBold)
    val subtitle = TextStyle(fontFamily = MognuText, fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.ExtraBold)
    val body = TextStyle(fontFamily = MognuText, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold)
    val bodyRegular = TextStyle(fontFamily = MognuText, fontSize = 15.sp, lineHeight = 21.sp)
    val support = TextStyle(fontFamily = MognuText, fontSize = 13.sp, lineHeight = 18.sp)
    val label = TextStyle(fontFamily = MognuText, fontSize = 13.sp, lineHeight = 16.sp, fontWeight = FontWeight.Bold)
    val caption = TextStyle(fontFamily = MognuText, fontSize = 12.sp, lineHeight = 16.sp)
    val overline = TextStyle(fontFamily = MognuText, fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 0.9.sp)
    val button = TextStyle(fontFamily = MognuText, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.ExtraBold)
    val number = TextStyle(fontFamily = MognuText, fontSize = 22.sp, lineHeight = 26.sp, fontWeight = FontWeight.ExtraBold)
}

/** Spacing grid. */
object Gap {
    val xs = 4.dp
    val s = 8.dp
    val m = 12.dp
    val l = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
}

/** Corner shapes: s for chips and small buttons, m for buttons and rows, l for cards and sheets. */
object Radius {
    val s = RoundedCornerShape(12.dp)
    val m = RoundedCornerShape(16.dp)
    val l = RoundedCornerShape(22.dp)
}

/** User choice in Settings. Stored by [key] in MMKV; dark is the brand default. */
enum class PamirThemeMode(val key: String, val label: String) {
    DARK("dark", "Тёмная"),
    LIGHT("light", "Светлая"),
    SYSTEM("system", "Авто");

    companion object {
        fun from(key: String?): PamirThemeMode = entries.firstOrNull { it.key == key } ?: DARK
    }
}

private val LocalPamirColors = staticCompositionLocalOf { PamirDark }

object Pamir {
    val colors: PamirColors
        @Composable @ReadOnlyComposable get() = LocalPamirColors.current
}

@Composable
fun PamirTheme(mode: PamirThemeMode, content: @Composable () -> Unit) {
    val dark = when (mode) {
        PamirThemeMode.DARK -> true
        PamirThemeMode.LIGHT -> false
        PamirThemeMode.SYSTEM -> isSystemInDarkTheme()
    }
    val c = if (dark) PamirDark else PamirLight
    // Material components (switches, text fields, sheets, ripples) take their colors from this scheme.
    val scheme = if (dark) {
        darkColorScheme(
            primary = c.accent, onPrimary = c.onAccent, secondary = c.accent, onSecondary = c.onAccent,
            background = c.bg, onBackground = c.text, surface = c.bg, onSurface = c.text,
            surfaceVariant = c.surface, onSurfaceVariant = c.textDim, outline = c.track, outlineVariant = c.line,
            surfaceContainerLow = c.surface, surfaceContainer = c.surface, surfaceContainerHigh = c.surfaceHigh,
            error = c.danger,
        )
    } else {
        lightColorScheme(
            primary = c.accentDeep, onPrimary = Color.White, secondary = c.accentDeep, onSecondary = Color.White,
            background = c.bg, onBackground = c.text, surface = c.bg, onSurface = c.text,
            surfaceVariant = c.surfaceHigh, onSurfaceVariant = c.textDim, outline = c.track, outlineVariant = c.line,
            surfaceContainerLow = c.surface, surfaceContainer = c.surface, surfaceContainerHigh = c.surfaceHigh,
            error = c.danger,
        )
    }
    MaterialTheme(colorScheme = scheme) {
        CompositionLocalProvider(
            LocalPamirColors provides c, LocalContentColor provides c.text,
            LocalTextStyle provides LocalTextStyle.current.copy(fontFamily = MognuText), content = content
        )
    }
}
