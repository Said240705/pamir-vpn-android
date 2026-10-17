package com.v2ray.ang.pamir

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.pow
import kotlin.math.sin
import kotlin.random.Random

private val Lime = Color(0xFFC8FF2E)
private val LimeAsleep = Color(0xFFA6CF3A)
private val Gold = Color(0xFFFFC93C)
private val Ink = Color(0xFF14102A)
private val Drop = Color(0xFF7FD4FF)
private val StickerShadow = Color(0x73080418)

/** Mascot artboard (Mognu sticker mockup): 240 wide, 290 tall, y from -40 so the crown can rise above the tile. */
private const val ART_W = 240f
private const val ART_H = 290f
private const val ART_TOP = -40f

/**
 * The connect button of the home screen: the crowned «M» as a Telegram-style sticker that changes mood with the VPN.
 * Off — asleep (closed eyes, crown askew, dimmer lime); connecting — straining (brows, sweat drop, shaking);
 * on — sunglasses whose top edge reads as an «M», golden crown and sparkles. A tap squashes it like a pressed sticker.
 * Alive in every pose: it breathes while asleep, and with the glasses on the crown hops and a shine runs over the lenses
 * every few seconds (same behaviour as the mascot on mognu.app).
 */
@Composable
fun MognuMascot(
    state: PowerState, label: String, stateLabel: String, onClick: () -> Unit, modifier: Modifier = Modifier, width: Dp = 240.dp,
    nudge: Int = 0,   // bump it to make the crown hop once (the greeting on app start)
) {
    val c = Pamir.colors
    val haptic = LocalHapticFeedback.current
    val scope = rememberCoroutineScope()
    val press = remember { Animatable(1f) }
    val source = remember { MutableInteractionSource() }
    val focused by source.collectIsFocusedAsState()
    val text = rememberTextMeasurer()

    val off by animateFloatAsState(if (state == PowerState.OFF) 1f else 0f, tween(260), label = "off")
    val busy by animateFloatAsState(if (state == PowerState.CONNECTING) 1f else 0f, tween(260), label = "busy")
    val on by animateFloatAsState(if (state == PowerState.ON) 1f else 0f, tween(260), label = "on")
    val tilt by animateFloatAsState(
        when (state) { PowerState.OFF -> -5f; PowerState.CONNECTING -> -2f; PowerState.ON -> 4f },
        spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow), label = "tilt"
    )
    val loop = rememberInfiniteTransition(label = "mascot")
    // only the connecting pose moves on its own: a quick shake while it strains
    val shake = if (state == PowerState.CONNECTING) loop.animateFloat(-1.6f, 1.6f, infiniteRepeatable(tween(90, easing = LinearEasing), RepeatMode.Reverse), label = "shake").value else 0f
    val zDrift = if (state == PowerState.OFF) loop.animateFloat(0f, 1f, infiniteRepeatable(tween(2600, easing = LinearEasing)), label = "z").value else 0f
    val newYear = PamirSeason.newYear
    val pomSway = if (newYear) loop.animateFloat(-6f, 8f, infiniteRepeatable(tween(2400, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "pom").value else 0f
    // the garland's lights run on one clock: they doze while off, chase while connecting, twinkle when on
    val lights = if (newYear) loop.animateFloat(0f, 1f, infiniteRepeatable(tween(2400, easing = LinearEasing)), label = "lights").value else 0f
    val breathe = if (state == PowerState.OFF) loop.animateFloat(1f, 1.025f, infiniteRepeatable(tween(1600, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "breathe").value else 1f
    // with the glasses on: now and then the crown hops and a shine sweeps across the lenses
    val hop = remember { Animatable(0f) }
    val shine = remember { Animatable(0f) }
    LaunchedEffect(nudge) {
        if (nudge == 0) return@LaunchedEffect
        hop.animateTo(1f, tween(160))
        hop.animateTo(0f, spring(dampingRatio = 0.4f, stiffness = Spring.StiffnessMediumLow))
    }
    LaunchedEffect(state) {
        if (state != PowerState.ON) return@LaunchedEffect
        while (true) {
            delay(3500L + Random.nextLong(3500L))
            launch { shine.snapTo(0f); shine.animateTo(1f, tween(520, easing = FastOutSlowInEasing)); shine.snapTo(0f) }
            hop.animateTo(1f, tween(160))
            hop.animateTo(0f, spring(dampingRatio = 0.4f, stiffness = Spring.StiffnessMediumLow))
        }
    }

    Canvas(
        modifier
            .size(width, width * (ART_H / ART_W))
            .graphicsLayer { scaleX = press.value * breathe; scaleY = press.value * press.value * breathe; rotationZ = tilt; translationX = shake.dp.toPx() }
            .clickable(interactionSource = source, indication = null, role = Role.Button) {
                haptic.performHapticFeedback(if (state == PowerState.OFF) HapticFeedbackType.ToggleOn else HapticFeedbackType.ToggleOff)
                scope.launch {
                    press.animateTo(0.88f, tween(90))
                    press.animateTo(1f, spring(dampingRatio = 0.35f, stiffness = Spring.StiffnessMedium))
                }
                onClick()
            }
            .semantics {
                contentDescription = label
                stateDescription = stateLabel
            }
    ) {
        val s = size.width / ART_W
        fun p(x: Float, y: Float) = Offset(x * s, (y - ART_TOP) * s)
        fun path(vararg pts: Pair<Float, Float>) = Path().apply {
            pts.forEachIndexed { i, (x, y) -> if (i == 0) moveTo(p(x, y).x, p(x, y).y) else lineTo(p(x, y).x, p(x, y).y) }
            close()
        }

        // «z» and speed lines are white on the dark theme, violet on the light one
        val air = if (c.isDark) Color.White else c.accent
        // speed lines behind the sticker while connecting
        if (busy > 0.01f) {
            val w = air.copy(alpha = 0.55f * busy)
            listOf(110f to 26f, 140f to 34f, 170f to 22f).forEach { (y, len) ->
                drawLine(w, p(6f, y), p(6f - len, y), 6 * s, StrokeCap.Round)
                drawLine(w, p(234f, y), p(234f + len, y), 6 * s, StrokeCap.Round)
            }
        }
        // sparkles above while on
        if (on > 0.01f) {
            val g = Gold.copy(alpha = on)
            drawPath(path(40f to -20f, 46f to -6f, 60f to 0f, 46f to 6f, 40f to 20f, 34f to 6f, 20f to 0f, 34f to -6f), g)
            drawPath(path(206f to -6f, 210f to 4f, 220f to 8f, 210f to 12f, 206f to 22f, 202f to 12f, 192f to 8f, 202f to 4f), g)
        }

        // the sticker: hard shadow, white die-cut border, lime face
        drawRoundRect(StickerShadow, p(18f, 40f), Size(204 * s, 204 * s), CornerRadius(58 * s))
        drawRoundRect(Color.White, p(18f, 30f), Size(204 * s, 204 * s), CornerRadius(58 * s))
        if (!c.isDark) drawRoundRect(Color(0x1F000000), p(18f, 30f), Size(204 * s, 204 * s), CornerRadius(58 * s), style = Stroke(1.dp.toPx()))
        if (focused) drawRoundRect(c.accent, p(12f, 24f), Size(216 * s, 216 * s), CornerRadius(62 * s), style = Stroke(4.dp.toPx()))
        drawRoundRect(lerp(LimeAsleep, Lime, 1f - off), p(28f, 40f), Size(184 * s, 184 * s), CornerRadius(50 * s))

        // crown: askew while asleep, straight and lifted, golden when on (in the New Year a Santa hat sits on it, PamirSeason)
        val crown = path(84f to 44f, 80f to 2f, 104f to 22f, 120f to -10f, 136f to 22f, 160f to 2f, 156f to 44f)
        val pivot = p(120f, 30f)
        translate(-8 * s * off, (6 * off - 6 * on - 14 * hop.value) * s) {
            rotate(-16f * off - 6f * hop.value, pivot) {
                drawPath(crown, Color.White, style = Stroke(14 * s, join = StrokeJoin.Round))
                drawPath(crown, lerp(Ink, Gold, on))
                if (newYear) drawSantaHat(s, pomSway)
            }
        }

        val stroke = Stroke(8 * s, cap = StrokeCap.Round)
        fun quad(x0: Float, y0: Float, cx: Float, cy: Float, x1: Float, y1: Float) = Path().apply {
            moveTo(p(x0, y0).x, p(x0, y0).y); quadraticTo(p(cx, cy).x, p(cx, cy).y, p(x1, y1).x, p(x1, y1).y)
        }
        // asleep: closed eyes, small mouth, drifting «z»
        if (off > 0.01f) {
            val ink = Ink.copy(alpha = off)
            drawPath(quad(72f, 128f, 87f, 141f, 102f, 128f), ink, style = stroke)
            drawPath(quad(138f, 128f, 153f, 141f, 168f, 128f), ink, style = stroke)
            drawPath(quad(108f, 172f, 120f, 178f, 132f, 172f), ink, style = Stroke(7 * s, cap = StrokeCap.Round))
            drawZ(text, "z", p(186f, 12f - 10f * zDrift), 30 * s, air, off * (1f - zDrift * 0.6f))
            drawZ(text, "z", p(212f, -14f - 10f * zDrift), 20 * s, air, off * 0.7f * (1f - zDrift * 0.6f))
        }
        // connecting: frowning brows, eyes, flat mouth, sweat drop
        if (busy > 0.01f) {
            val ink = Ink.copy(alpha = busy)
            drawLine(ink, p(70f, 104f), p(104f, 116f), 8 * s, StrokeCap.Round)
            drawLine(ink, p(170f, 104f), p(136f, 116f), 8 * s, StrokeCap.Round)
            drawCircle(ink, 10 * s, p(88f, 134f))
            drawCircle(ink, 10 * s, p(152f, 134f))
            drawLine(ink, p(100f, 176f), p(140f, 176f), 8 * s, StrokeCap.Round)
            val drop = Path().apply {
                val a = p(190f, 74f); val b = p(190f, 98f)
                moveTo(a.x, a.y); quadraticTo(p(200f, 90f).x, p(200f, 90f).y, b.x, b.y); quadraticTo(p(180f, 90f).x, p(180f, 90f).y, a.x, a.y); close()
            }
            drawPath(drop, Drop.copy(alpha = busy))
            drawPath(drop, Color.White.copy(alpha = busy), style = Stroke(3 * s))
        }
        // on: «M» sunglasses and a smirk
        if (on > 0.01f) {
            val ink = Ink.copy(alpha = on)
            val glasses = Path().apply {
                fun m(x: Float, y: Float) = p(x, y).let { moveTo(it.x, it.y) }
                fun l(x: Float, y: Float) = p(x, y).let { lineTo(it.x, it.y) }
                fun q(cx: Float, cy: Float, x: Float, y: Float) { val k = p(cx, cy); val e = p(x, y); quadraticTo(k.x, k.y, e.x, e.y) }
                m(50f, 108f); l(112f, 108f); l(120f, 124f); l(128f, 108f); l(190f, 108f); l(186f, 120f); l(176f, 146f)
                q(170f, 152f, 160f, 152f); l(142f, 152f); q(132f, 152f, 130f, 142f); l(124f, 126f); l(116f, 126f); l(110f, 142f)
                q(108f, 152f, 98f, 152f); l(80f, 152f); q(70f, 152f, 64f, 146f); l(54f, 120f); close()
            }
            drawPath(glasses, ink)
            if (shine.value > 0f) clipPath(glasses) {
                val dx = -130f + 260f * shine.value
                val shineColor = Color.White.copy(alpha = 0.35f * on)
                drawPath(path(70f + dx to 108f, 84f + dx to 108f, 66f + dx to 152f, 52f + dx to 152f), shineColor)
                drawPath(path(92f + dx to 108f, 98f + dx to 108f, 80f + dx to 152f, 74f + dx to 152f), shineColor)
            }
            val glint = Color.White.copy(alpha = 0.6f * on)
            drawLine(glint, p(78f, 116f), p(96f, 116f), 5 * s, StrokeCap.Round)
            drawLine(glint, p(150f, 116f), p(166f, 116f), 5 * s, StrokeCap.Round)
            drawPath(quad(98f, 180f, 124f, 196f, 150f, 172f), ink, style = stroke)
        }
        if (newYear) drawGarland(s, lights, off, busy, on)
    }
}

private val BulbColors = listOf(Color(0xFFE5323F), Color(0xFFFFC83D), Color(0xFF7FD4FF), Color(0xFFB79CFF), Color(0xFFFF7BB8))

/**
 * The New Year garland (PamirSeason): a string of lights slung across the lower right corner of the sticker, like a ribbon on a gift, with the
 * light following the button's state — asleep the bulbs barely glow, connecting a light runs along the string, on they
 * all shine and twinkle. Drawn in artboard units, so it tilts and squashes with the sticker.
 */
private fun DrawScope.drawGarland(s: Float, t: Float, off: Float, busy: Float, on: Float) {
    fun o(x: Float, y: Float) = Offset(x * s, (y - ART_TOP) * s)
    val wire = Path().apply {
        fun m(x: Float, y: Float) = o(x, y).let { moveTo(it.x, it.y) }
        fun c(x1: Float, y1: Float, x2: Float, y2: Float, x: Float, y: Float) {
            val a = o(x1, y1); val b = o(x2, y2); val e = o(x, y); cubicTo(a.x, a.y, b.x, b.y, e.x, e.y)
        }
        m(40f, 232f); c(100f, 232f, 196f, 196f, 240f, 100f)
    }
    drawPath(wire, Color.White, style = Stroke(7 * s, cap = StrokeCap.Round))
    drawPath(wire, Ink, style = Stroke(3 * s, cap = StrokeCap.Round))
    val measure = PathMeasure().apply { setPath(wire, false) }
    val n = 8
    for (i in 0 until n) {
        val d = measure.length * (i + 0.5f) / n
        val at = measure.getPosition(d)
        val tan = measure.getTangent(d)
        val wave = sin(2 * PI.toFloat() * (t * 2 + i * 0.61f))
        val doze = 0.22f + 0.12f * (0.5f + 0.5f * sin(2 * PI.toFloat() * (t + i * 0.37f)))
        val chase = 0.25f + 0.75f * (1f - ((t * 2 - i.toFloat() / n) % 1f + 1f) % 1f).pow(3)
        val lit = (off * doze + busy * chase + on * (0.82f + 0.18f * wave)).coerceIn(0f, 1f)
        val color = BulbColors[i % BulbColors.size]
        // bulbs hang from the wire, leaning a little with it
        rotate(atan2(tan.y, tan.x) * 180f / PI.toFloat() * 0.35f, at) {
            val bulb = Offset(at.x, at.y + 12 * s)
            if (lit > 0.4f) drawCircle(
                Brush.radialGradient(listOf(color.copy(alpha = 0.6f * (lit - 0.4f) / 0.6f), Color.Transparent), bulb, 24 * s),
                24 * s, bulb
            )
            drawOval(Color.White, Offset(bulb.x - 10 * s, bulb.y - 11 * s), Size(20 * s, 26 * s))
            drawOval(lerp(lerp(color, Ink, 0.55f), color, lit), Offset(bulb.x - 7 * s, bulb.y - 8 * s), Size(14 * s, 20 * s))
            drawCircle(Color.White.copy(alpha = 0.25f + 0.5f * lit), 2.8f * s, Offset(bulb.x - 2.4f * s, bulb.y - 3 * s))
            drawRoundRect(Ink, Offset(at.x - 5 * s, at.y - 1 * s), Size(10 * s, 7 * s), CornerRadius(2 * s))
        }
    }
}

private val HatRed = Color(0xFFE5323F)
private val HatFold = Color(0xFFB8202D)
private val Fur = Color(0xFFF4F2FA)
private val FurDent = Color(0xFFD9D4EA)

/**
 * The New Year outfit (same drawing as mognu-season.js on the site): a red Santa hat worn askew over the left part of
 * the crown, the right part of the crown peeking out, white fur band and a swaying pompom on the tip flopped to the
 * left. The hat is drawn in artboard units with its tip to the right, then mirrored, shrunk and tilted onto the head;
 * it sits inside the crown's translate/rotate, so it hops and tilts exactly like the crown.
 */
private fun DrawScope.drawSantaHat(s: Float, pomSway: Float) {
    fun o(x: Float, y: Float) = Offset(x * s, y * s)
    fun Path.m(x: Float, y: Float) = o(x, y).let { moveTo(it.x, it.y) }
    fun Path.l(x: Float, y: Float) = o(x, y).let { lineTo(it.x, it.y) }
    fun Path.c(x1: Float, y1: Float, x2: Float, y2: Float, x: Float, y: Float) {
        val a = o(x1, y1); val b = o(x2, y2); val e = o(x, y); cubicTo(a.x, a.y, b.x, b.y, e.x, e.y)
    }
    val cone = Path().apply {
        m(66f, 32f); c(70f, -6f, 104f, -40f, 150f, -42f); c(182f, -43f, 204f, -26f, 214f, -2f)
        c(206f, -12f, 192f, -18f, 178f, -16f); c(164f, -14f, 158f, -2f, 160f, 14f); l(172f, 32f); close()
    }
    val fold = Path().apply {
        m(150f, -42f); c(182f, -43f, 204f, -26f, 214f, -2f); c(206f, -12f, 192f, -18f, 178f, -16f)
        c(170f, -15f, 164f, -10f, 161f, -2f); c(166f, -22f, 160f, -36f, 150f, -42f); close()
    }
    val gleam = Path().apply { m(86f, 10f); c(100f, -14f, 122f, -28f, 146f, -32f) }
    // svg: translate(74 26) rotate(-28) scale(.82) translate(-120 -34) mirror — the mirror folded into a negative scale
    withTransform({
        translate(74 * s, (26 - ART_TOP) * s)
        rotate(-28f, Offset.Zero)
        scale(-0.82f, 0.82f, Offset.Zero)
        translate(-120 * s, -34 * s)
    }) {
        drawPath(cone, Color.White, style = Stroke(20 * s, join = StrokeJoin.Round))
        drawPath(cone, HatRed)
        drawPath(fold, HatFold)
        drawPath(gleam, Color.White.copy(alpha = 0.28f), style = Stroke(7 * s, cap = StrokeCap.Round))
        // the fur band
        drawRoundRect(Color.White, o(54f, 18f), Size(132 * s, 32 * s), CornerRadius(16 * s), style = Stroke(10 * s))
        drawRoundRect(Fur, o(54f, 18f), Size(132 * s, 32 * s), CornerRadius(16 * s))
        listOf(70f to 30f, 92f to 38f, 114f to 28f, 136f to 38f, 158f to 30f).forEach { (x, y) ->
            drawLine(FurDent, o(x, y), o(x + 8f, y), 5 * s, StrokeCap.Round)
        }
        // the pompom sways on the tip
        rotate(pomSway, o(214f, -17f)) {
            drawCircle(Color.White, 22 * s, o(214f, 0f))
            drawCircle(Fur, 17 * s, o(214f, 0f))
            drawCircle(Color.White, 5 * s, o(219f, -5f))
        }
    }
}

private fun DrawScope.drawZ(text: TextMeasurer, z: String, at: Offset, px: Float, color: Color, alpha: Float) {
    if (alpha <= 0.01f) return
    val style = TextStyle(fontFamily = MognuDisplay, fontSize = (px / density / fontScale).sp, color = color.copy(alpha = alpha.coerceIn(0f, 1f)))
    val layout = text.measure(z, style)
    drawText(layout, topLeft = Offset(at.x, at.y - layout.size.height * 0.8f))
}
