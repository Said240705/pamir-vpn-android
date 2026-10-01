package com.v2ray.ang.pamir

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.BottomSheetDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldColors
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

// Stateless building blocks of the Pamir screens. They know nothing about the VPN or the API:
// the activity passes text, state and callbacks in.

enum class Tone { ACCENT, WARN, DANGER, NEUTRAL }

@Composable
fun Tone.color(): Color = when (this) {
    Tone.ACCENT -> Pamir.colors.accentText
    Tone.WARN -> Pamir.colors.warn
    Tone.DANGER -> Pamir.colors.danger
    Tone.NEUTRAL -> Pamir.colors.textDim
}

@Composable
fun Tone.soft(): Color = when (this) {
    Tone.ACCENT -> Pamir.colors.accentSoft
    Tone.WARN -> Pamir.colors.warnSoft
    Tone.DANGER -> Pamir.colors.dangerSoft
    Tone.NEUTRAL -> Pamir.colors.surfaceHigh
}

// ---------- surfaces ----------

@Composable
fun PamirCard(
    modifier: Modifier = Modifier,
    tone: Tone = Tone.NEUTRAL,
    onClick: (() -> Unit)? = null,
    contentPadding: Dp = Gap.l,
    content: @Composable ColumnScope.() -> Unit,
) {
    val c = Pamir.colors
    Column(
        modifier
            .fillMaxWidth()
            .clip(Radius.l)
            .background(c.surface)
            .background(if (tone == Tone.NEUTRAL) Color.Transparent else tone.soft())
            .border(1.dp, if (tone == Tone.NEUTRAL) c.line else tone.color().copy(alpha = 0.35f), Radius.l)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .padding(contentPadding),
        content = content
    )
}

@Composable
fun IconBadge(
    icon: ImageVector,
    tint: Color = Pamir.colors.accentText,
    background: Color = Pamir.colors.accentSoft,
    size: Dp = 36.dp,
    iconSize: Dp = 20.dp,
    shape: Shape = Radius.s,
) {
    Box(Modifier.size(size).clip(shape).background(background), contentAlignment = Alignment.Center) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(iconSize), tint = tint)
    }
}

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(), style = PamirType.overline, color = Pamir.colors.textDim,
        modifier = modifier.padding(start = Gap.xs, top = Gap.xl, bottom = Gap.s)
    )
}

@Composable
fun ScreenTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = PamirType.title, color = Pamir.colors.text, modifier = modifier.padding(top = Gap.l, bottom = Gap.xs).semantics { heading() })
}

@Composable
fun Chip(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Text(
        text, style = PamirType.label, color = tone.color(), maxLines = 1,
        modifier = modifier
            .clip(CircleShape)
            .background(tone.soft())
            .padding(horizontal = 10.dp, vertical = 5.dp)
    )
}

// ---------- buttons ----------
// Width comes from `modifier` (full width by default), so the same buttons also fit into rows.

@Composable
fun PrimaryButton(
    text: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    subtitle: String? = null,
    icon: ImageVector? = null,
    loading: Boolean = false,
    onClick: () -> Unit,
) {
    val c = Pamir.colors
    Box(
        modifier
            .heightIn(min = if (subtitle != null) 60.dp else 52.dp)
            .clip(Radius.m)
            .background(Brush.linearGradient(listOf(c.accent, c.accentDeep)))
            .clickable(enabled = !loading, role = Role.Button, onClick = onClick)
            .padding(horizontal = Gap.l, vertical = Gap.s),
        contentAlignment = Alignment.Center
    ) {
        if (loading) {
            CircularProgressIndicator(color = c.onAccent, strokeWidth = 2.5.dp, modifier = Modifier.size(22.dp))
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (icon != null) {
                    Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.onAccent)
                    Spacer(Modifier.width(Gap.s))
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(text, style = PamirType.button, color = c.onAccent, textAlign = TextAlign.Center)
                    if (subtitle != null) {
                        Text(subtitle, style = PamirType.caption.copy(fontWeight = FontWeight.SemiBold), color = c.onAccent.copy(alpha = 0.75f))
                    }
                }
            }
        }
    }
}

@Composable
fun SecondaryButton(
    text: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    icon: ImageVector? = null,
    loading: Boolean = false,
    onClick: () -> Unit,
) {
    val c = Pamir.colors
    Box(
        modifier
            .heightIn(min = 52.dp)
            .clip(Radius.m)
            .background(c.surface)
            .border(1.dp, c.line, Radius.m)
            .clickable(enabled = !loading, role = Role.Button, onClick = onClick)
            .padding(horizontal = Gap.m, vertical = Gap.s),
        contentAlignment = Alignment.Center
    ) {
        if (loading) {
            CircularProgressIndicator(color = c.accentText, strokeWidth = 2.5.dp, modifier = Modifier.size(20.dp))
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (icon != null) {
                    Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp), tint = c.accentText)
                    Spacer(Modifier.width(Gap.s))
                }
                Text(text, style = PamirType.button.copy(fontWeight = FontWeight.Bold), color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** Text-only action with a full 48dp touch target. */
@Composable
fun TextAction(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = Pamir.colors.textDim,
    icon: ImageVector? = null,
    onClick: () -> Unit,
) {
    Row(
        modifier
            .heightIn(min = 48.dp)
            .clip(Radius.s)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = Gap.m),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp), tint = color)
            Spacer(Modifier.width(6.dp))
        }
        Text(text, style = PamirType.label, color = color)
    }
}

/** Round icon-only button; [label] is read by TalkBack. */
@Composable
fun IconAction(icon: ImageVector, label: String, onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = Pamir.colors.text) {
    Box(
        modifier
            .size(48.dp)
            .clip(CircleShape)
            .clickable(role = Role.Button, onClickLabel = label, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center
    ) { Icon(icon, contentDescription = null, modifier = Modifier.size(24.dp), tint = tint) }
}

// ---------- rows ----------

@Composable
fun RowGroup(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = Pamir.colors
    Column(
        modifier
            .fillMaxWidth()
            .clip(Radius.l)
            .background(c.surface)
            .border(1.dp, c.line, Radius.l),
        content = content
    )
}

@Composable
fun RowDivider() {
    Box(Modifier.padding(start = 64.dp).fillMaxWidth().height(1.dp).background(Pamir.colors.line))
}

@Composable
private fun RowContent(
    leading: (@Composable () -> Unit)?,
    title: String,
    subtitle: String?,
    titleColor: Color,
    subtitleColor: Color,
    modifier: Modifier,
    trailing: @Composable RowScope.() -> Unit,
) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (leading != null) {
            leading()
            Spacer(Modifier.width(14.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, style = PamirType.body, color = titleColor, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!subtitle.isNullOrEmpty()) {
                Spacer(Modifier.height(2.dp))
                Text(subtitle, style = PamirType.support, color = subtitleColor, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.width(Gap.s))
        trailing()
    }
}

@Composable
fun pamirSwitchColors() = SwitchDefaults.colors(
    checkedTrackColor = Pamir.colors.accentDeep,
    checkedThumbColor = Color.White,
    checkedBorderColor = Color.Transparent,
    uncheckedTrackColor = Pamir.colors.track,
    uncheckedThumbColor = if (Pamir.colors.isDark) Color(0xFFB8C4D2) else Color.White,
    uncheckedBorderColor = Color.Transparent,
)

/** Whole row is one switch for touch and TalkBack. */
@Composable
fun ToggleRow(
    leading: (@Composable () -> Unit)?,
    title: String,
    subtitle: String?,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    subtitleColor: Color = Pamir.colors.textDim,
) {
    RowContent(
        leading = leading, title = title, subtitle = subtitle,
        titleColor = Pamir.colors.text, subtitleColor = subtitleColor,
        modifier = Modifier.toggleable(value = checked, role = Role.Switch, onValueChange = onCheckedChange)
    ) {
        Switch(checked = checked, onCheckedChange = null, colors = pamirSwitchColors())
    }
}

@Composable
fun ToggleRow(icon: ImageVector, title: String, subtitle: String?, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    ToggleRow({ IconBadge(icon) }, title, subtitle, checked, onCheckedChange)
}

@Composable
fun LinkRow(
    icon: ImageVector,
    title: String,
    subtitle: String?,
    tone: Tone = Tone.ACCENT,
    loading: Boolean = false,
    onClick: () -> Unit,
) {
    val c = Pamir.colors
    RowContent(
        leading = { IconBadge(icon, tint = tone.color(), background = tone.soft()) },
        title = title, subtitle = subtitle,
        titleColor = if (tone == Tone.DANGER) c.danger else c.text, subtitleColor = c.textDim,
        modifier = Modifier.clickable(role = Role.Button, onClick = onClick)
    ) {
        if (loading) CircularProgressIndicator(color = c.accentText, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
        else Icon(PamirIcons.ChevronRight, contentDescription = null, modifier = Modifier.size(22.dp), tint = c.textDim)
    }
}

// ---------- notices ----------

/** One-line notice on the home screen: subscription, update, white lists. */
@Composable
fun Banner(icon: ImageVector, text: String, action: String?, tone: Tone, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Pamir.colors
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = 52.dp)
            .clip(Radius.m)
            .background(c.surface)
            .background(tone.soft())
            .border(1.dp, tone.color().copy(alpha = 0.3f), Radius.m)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp), tint = tone.color())
        Spacer(Modifier.width(Gap.m))
        Text(
            text, style = PamirType.support.copy(fontWeight = FontWeight.SemiBold), color = c.text,
            maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f)
        )
        if (action != null) {
            Spacer(Modifier.width(Gap.s))
            Text(action, style = PamirType.label, color = tone.color(), maxLines = 1)
        }
    }
}

@Composable
fun NoteCard(icon: ImageVector, title: String, text: String, tone: Tone, actions: @Composable ColumnScope.() -> Unit) {
    val c = Pamir.colors
    PamirCard(tone = tone) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconBadge(icon, tint = tone.color(), background = c.surface.copy(alpha = 0.6f), size = 40.dp, iconSize = 22.dp)
            Spacer(Modifier.width(Gap.m))
            Text(title, style = PamirType.subtitle, color = c.text)
        }
        Spacer(Modifier.height(Gap.s))
        Text(text, style = PamirType.support, color = c.textDim)
        Spacer(Modifier.height(Gap.l))
        actions()
    }
}

// ---------- server quality ----------

enum class PingQuality { UNKNOWN, GOOD, FAIR, POOR, DOWN }

/** Server response time (a full request through the core, or a TCP connect): < 350 ms good, < 800 ms fair, slower poor, <= 0 no answer. */
fun pingQuality(ms: Int?): PingQuality = when {
    ms == null -> PingQuality.UNKNOWN
    ms <= 0 -> PingQuality.DOWN
    ms < 350 -> PingQuality.GOOD
    ms < 800 -> PingQuality.FAIR
    else -> PingQuality.POOR
}

@Composable
fun PingQuality.color(): Color = when (this) {
    PingQuality.GOOD -> Pamir.colors.accentText
    PingQuality.FAIR -> Pamir.colors.warn
    PingQuality.POOR, PingQuality.DOWN -> Pamir.colors.danger
    PingQuality.UNKNOWN -> Pamir.colors.textDim
}

@Composable
fun PingBars(quality: PingQuality, modifier: Modifier = Modifier) {
    val c = Pamir.colors
    val active = when (quality) {
        PingQuality.GOOD -> 3
        PingQuality.FAIR -> 2
        PingQuality.POOR -> 1
        else -> 0
    }
    val col = quality.color()
    Row(modifier.height(16.dp), horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.Bottom) {
        for (i in 1..3) {
            Box(
                Modifier
                    .width(4.dp)
                    .height((6 + (i - 1) * 5).dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(if (i <= active) col else c.track)
            )
        }
    }
}

// ---------- power button ----------

enum class PowerState { OFF, CONNECTING, ON }

/**
 * The main connect button. Colors cross-fade between states, a spinning arc shows connecting,
 * the glow breathes while protected; every press gives haptic feedback.
 * Infinite animations run only in the states that show them.
 */
@Composable
fun PowerButton(state: PowerState, label: String, stateLabel: String, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 172.dp) {
    val c = Pamir.colors
    val haptic = LocalHapticFeedback.current
    val on by animateFloatAsState(if (state == PowerState.ON) 1f else 0f, tween(600), label = "on")
    val busy by animateFloatAsState(if (state == PowerState.CONNECTING) 1f else 0f, tween(300), label = "busy")
    val spin = if (state == PowerState.CONNECTING) {
        rememberInfiniteTransition(label = "spin")
            .animateFloat(0f, 360f, infiniteRepeatable(tween(1100, easing = LinearEasing)), label = "spinAngle").value
    } else 0f
    val breathe = if (state == PowerState.ON) {
        rememberInfiniteTransition(label = "breathe")
            .animateFloat(0.55f, 1f, infiniteRepeatable(tween(2200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "glow").value
    } else 1f
    Box(modifier.size(size * 1.45f), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val glow = 0.32f * on * breathe + 0.16f * busy
            if (glow > 0.01f) {
                val r = this.size.minDimension / 2
                drawCircle(Brush.radialGradient(listOf(c.accent.copy(alpha = glow), Color.Transparent), center, r), r)
            }
        }
        Box(
            Modifier
                .size(size)
                .shadow(if (c.isDark) 0.dp else 14.dp, CircleShape, spotColor = c.accentDeep.copy(alpha = 0.35f))
                .clip(CircleShape)
                .clickable(role = Role.Button) {
                    haptic.performHapticFeedback(if (state == PowerState.OFF) HapticFeedbackType.ToggleOn else HapticFeedbackType.ToggleOff)
                    onClick()
                }
                .semantics {
                    contentDescription = label
                    stateDescription = stateLabel
                },
            contentAlignment = Alignment.Center
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val r = this.size.minDimension / 2
                drawCircle(Brush.verticalGradient(listOf(lerp(c.powerOff[0], c.powerOn[0], on), lerp(c.powerOff[1], c.powerOn[1], on))), r)
                val stroke = 3.dp.toPx()
                val inset = stroke / 2
                val ringSize = Size(this.size.width - stroke, this.size.height - stroke)
                drawCircle(lerp(c.line, c.accent, on), r - inset, style = Stroke(stroke))
                if (busy > 0.01f) {
                    drawArc(
                        c.accent.copy(alpha = busy), startAngle = spin - 90f, sweepAngle = 110f, useCenter = false,
                        topLeft = Offset(inset, inset), size = ringSize, style = Stroke(stroke, cap = StrokeCap.Round)
                    )
                }
                val ic = lerp(c.powerIconOff, c.accentText, maxOf(on, busy * 0.6f))
                val ir = r * 0.30f
                val w = r * 0.075f
                drawArc(
                    ic, startAngle = -60f, sweepAngle = 300f, useCenter = false,
                    topLeft = Offset(center.x - ir, center.y - ir + ir * 0.12f), size = Size(ir * 2, ir * 2),
                    style = Stroke(width = w, cap = StrokeCap.Round)
                )
                drawLine(ic, Offset(center.x, center.y - ir * 1.15f), Offset(center.x, center.y - ir * 0.05f), strokeWidth = w, cap = StrokeCap.Round)
            }
        }
    }
}

@Composable
fun Sparkline(values: List<Float>, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        if (values.size < 2) return@Canvas
        val max = (values.maxOrNull() ?: 0f).coerceAtLeast(16f * 1024f)
        val n = 40
        val step = size.width / (n - 1)
        val x0 = size.width - step * (values.size - 1)
        val pts = values.mapIndexed { i, v ->
            Offset(x0 + step * i, size.height - 2.dp.toPx() - (v / max) * (size.height - 6.dp.toPx()))
        }
        val line = Path().apply { moveTo(pts[0].x, pts[0].y); pts.drop(1).forEach { lineTo(it.x, it.y) } }
        val fill = Path().apply {
            addPath(line)
            lineTo(pts.last().x, size.height); lineTo(pts[0].x, size.height); close()
        }
        drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.25f), Color.Transparent)))
        drawPath(line, color, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round))
    }
}

/** Ring with the number of days left; [fraction] fills it (a month = full). */
@Composable
fun DaysRing(days: Int, unit: String, tone: Tone, modifier: Modifier = Modifier, size: Dp = 68.dp) {
    val c = Pamir.colors
    val col = tone.color()
    val target = (days.coerceAtLeast(0) / 30f).coerceIn(0f, 1f)
    val f by animateFloatAsState(target, tween(900, easing = FastOutSlowInEasing), label = "days")
    Box(modifier.size(size).clearAndSetSemantics { contentDescription = "$days $unit" }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val s = 5.dp.toPx()
            val tl = Offset(s / 2, s / 2)
            val sz = Size(this.size.width - s, this.size.height - s)
            drawArc(c.track, -90f, 360f, false, topLeft = tl, size = sz, style = Stroke(s))
            if (f > 0f) drawArc(col, -90f, 360f * f, false, topLeft = tl, size = sz, style = Stroke(s, cap = StrokeCap.Round))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("$days", style = PamirType.subtitle, color = c.text)
            Text(unit, style = PamirType.caption, color = c.textDim)
        }
    }
}

@Composable
fun ProgressLine(fraction: Float, color: Color, modifier: Modifier = Modifier) {
    val f by animateFloatAsState(fraction.coerceIn(0f, 1f), tween(700), label = "progress")
    Box(modifier.fillMaxWidth().height(6.dp).clip(CircleShape).background(Pamir.colors.track)) {
        Box(Modifier.fillMaxWidth(f).fillMaxHeight().clip(CircleShape).background(color))
    }
}

// ---------- navigation ----------

class NavEntry(val label: String, val icon: ImageVector)

/** Floating bottom bar; the pill under the active icon grows and fades in. */
@Composable
fun BottomNav(items: List<NavEntry>, selected: Int, onSelect: (Int) -> Unit, modifier: Modifier = Modifier) {
    val c = Pamir.colors
    Row(
        modifier
            .padding(horizontal = Gap.l, vertical = Gap.s)
            .fillMaxWidth()
            .height(68.dp)
            .shadow(if (c.isDark) 0.dp else 10.dp, Radius.l, ambientColor = Color.Black.copy(alpha = 0.08f), spotColor = Color.Black.copy(alpha = 0.12f))
            .clip(Radius.l)
            .background(if (c.isDark) c.surfaceHigh else c.surface)
            .border(1.dp, c.line, Radius.l)
            .selectableGroup(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        items.forEachIndexed { i, item ->
            val active = i == selected
            val pillW by animateDpAsState(if (active) 60.dp else 32.dp, spring(dampingRatio = Spring.DampingRatioMediumBouncy), label = "pillW")
            val pill by animateColorAsState(if (active) c.accentSoft else Color.Transparent, tween(250), label = "pill")
            val tint by animateColorAsState(if (active) c.accentText else c.textDim, tween(250), label = "tint")
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .selectable(selected = active, role = Role.Tab, onClick = { onSelect(i) }),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Box(Modifier.width(pillW).height(32.dp).clip(CircleShape).background(pill), contentAlignment = Alignment.Center) {
                    Icon(item.icon, contentDescription = null, modifier = Modifier.size(22.dp), tint = tint)
                }
                Spacer(Modifier.height(3.dp))
                Text(item.label, style = PamirType.caption.copy(fontWeight = if (active) FontWeight.ExtraBold else FontWeight.SemiBold), color = tint)
            }
        }
    }
}

/** Three-way switch, e.g. the theme choice. */
@Composable
fun SegmentedControl(options: List<String>, selected: Int, onSelect: (Int) -> Unit, modifier: Modifier = Modifier) {
    val c = Pamir.colors
    Row(
        modifier
            .fillMaxWidth()
            .height(48.dp)
            .clip(Radius.s)
            .background(if (c.isDark) c.bg else c.surfaceHigh)
            .padding(4.dp)
            .selectableGroup()
    ) {
        options.forEachIndexed { i, o ->
            val active = i == selected
            val bg by animateColorAsState(if (active) (if (c.isDark) c.track else c.surface) else Color.Transparent, tween(200), label = "seg")
            Box(
                Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(9.dp))
                    .background(bg)
                    .selectable(selected = active, role = Role.RadioButton, onClick = { onSelect(i) }),
                contentAlignment = Alignment.Center
            ) {
                Text(o, style = PamirType.label, color = if (active) c.text else c.textDim, maxLines = 1)
            }
        }
    }
}

// ---------- loading ----------

@Composable
fun Skeleton(modifier: Modifier, shape: Shape = RoundedCornerShape(8.dp)) {
    val a by rememberInfiniteTransition(label = "skeleton")
        .animateFloat(0.35f, 0.9f, infiniteRepeatable(tween(850), RepeatMode.Reverse), label = "skeletonAlpha")
    Box(modifier.graphicsLayer { alpha = a }.clip(shape).background(Pamir.colors.surfaceHigh))
}

@Composable
fun SkeletonCard(loadingLabel: String) {
    PamirCard(Modifier.semantics { contentDescription = loadingLabel }) {
        Skeleton(Modifier.width(110.dp).height(12.dp))
        Spacer(Modifier.height(Gap.m))
        Skeleton(Modifier.fillMaxWidth(0.6f).height(24.dp))
        Spacer(Modifier.height(Gap.m))
        Skeleton(Modifier.fillMaxWidth().height(10.dp))
    }
}

// ---------- sheets, fields, snackbars ----------

/**
 * Bottom sheet with a title row and a scrollable body that stays above the keyboard
 * (imePadding on the scroll container), so forms inside remain reachable.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PamirSheet(
    onDismiss: () -> Unit,
    title: String,
    subtitle: String? = null,
    headerAction: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val c = Pamir.colors
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = state,
        containerColor = c.sheet,
        contentColor = c.text,
        dragHandle = { BottomSheetDefaults.DragHandle(color = c.track) },
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.l)
                .padding(bottom = Gap.xl)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(title, style = PamirType.headline, color = c.text, modifier = Modifier.semantics { heading() })
                    if (subtitle != null) {
                        Spacer(Modifier.height(Gap.xs))
                        Text(subtitle, style = PamirType.support, color = c.textDim)
                    }
                }
                headerAction?.invoke()
            }
            Spacer(Modifier.height(Gap.l))
            content()
        }
    }
}

@Composable
fun pamirFieldColors(): TextFieldColors {
    val c = Pamir.colors
    return OutlinedTextFieldDefaults.colors(
        focusedBorderColor = c.accentDeep, unfocusedBorderColor = c.track, cursorColor = c.accentDeep,
        focusedContainerColor = c.surface, unfocusedContainerColor = c.surface,
        focusedTextColor = c.text, unfocusedTextColor = c.text,
        focusedPlaceholderColor = c.textDim, unfocusedPlaceholderColor = c.textDim,
    )
}

@Composable
fun PamirSnackbarHost(state: SnackbarHostState, modifier: Modifier = Modifier) {
    val c = Pamir.colors
    SnackbarHost(state, modifier) { data ->
        val bg = if (c.isDark) c.surfaceHigh else Color(0xFF1B2636)
        val fg = if (c.isDark) c.text else Color.White
        Row(
            Modifier
                .padding(horizontal = Gap.l, vertical = Gap.s)
                .fillMaxWidth()
                .heightIn(min = 52.dp)
                .shadow(12.dp, Radius.m)
                .clip(Radius.m)
                .background(bg)
                .border(1.dp, c.line, Radius.m)
                .padding(start = Gap.l, end = Gap.xs, top = Gap.xs, bottom = Gap.xs),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                data.visuals.message, style = PamirType.support.copy(fontWeight = FontWeight.SemiBold), color = fg,
                modifier = Modifier.weight(1f).padding(vertical = 10.dp)
            )
            data.visuals.actionLabel?.let { TextAction(it, color = c.accent) { data.performAction() } }
        }
    }
}
