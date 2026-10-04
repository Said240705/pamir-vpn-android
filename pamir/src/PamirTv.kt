package com.v2ray.ang.pamir

import android.app.UiModeManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import androidx.compose.foundation.Image
import androidx.compose.foundation.IndicationNodeFactory
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.FocusInteraction
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.ContentDrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.node.DelegatableNode
import androidx.compose.ui.node.DrawModifierNode
import androidx.compose.ui.node.invalidateDraw
import androidx.compose.ui.Modifier.Node
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.v2ray.ang.util.QRCodeDecoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.abs

/**
 * Android TV: the app is driven by a remote (D-pad) and there is usually no browser or Telegram,
 * so the focused control gets a clear highlight and links are shown as QR codes for the phone.
 */
object PamirTv {
    fun isTv(context: Context): Boolean {
        val ui = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        return ui?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION ||
            context.packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK)
    }
}

/** True inside the UI on Android TV; provided once by the activity. */
val LocalTv = staticCompositionLocalOf { false }

/** A link to open on the phone: shown on TV as a QR code; [onClose] runs when the user closes it. */
class QrLink(val title: String, val text: String, val url: String, val onClose: (() -> Unit)? = null)

/**
 * Indication for the remote: the focused control gets an accent tint and a contrasting outline [ring]
 * (the outline also stands out on accent-colored buttons). Square controls are round in this app
 * (power button, icon buttons), others use the common 16 dp corner; the control's clip trims the rest.
 */
class TvFocusIndication(private val tint: Color, private val ring: Color) : IndicationNodeFactory {
    override fun create(interactionSource: InteractionSource): DelegatableNode = TvFocusNode(interactionSource, tint, ring)
    override fun equals(other: Any?): Boolean = other is TvFocusIndication && other.tint == tint && other.ring == ring
    override fun hashCode(): Int = 31 * tint.hashCode() + ring.hashCode()
}

private class TvFocusNode(
    private val source: InteractionSource,
    private val tint: Color,
    private val ring: Color,
) : Node(), DrawModifierNode {
    private var focused = false
    private var pressed = false

    override fun onAttach() {
        coroutineScope.launch {
            var focusCount = 0
            var pressCount = 0
            source.interactions.collect { i ->
                when (i) {
                    is FocusInteraction.Focus -> focusCount++
                    is FocusInteraction.Unfocus -> focusCount--
                    is PressInteraction.Press -> pressCount++
                    is PressInteraction.Release, is PressInteraction.Cancel -> pressCount--
                }
                val f = focusCount > 0
                val p = pressCount > 0
                if (f != focused || p != pressed) {
                    focused = f; pressed = p
                    invalidateDraw()
                }
            }
        }
    }

    override fun ContentDrawScope.draw() {
        drawContent()
        if (!focused && !pressed) return
        drawRect(tint.copy(alpha = if (pressed) 0.30f else 0.18f))
        if (!focused) return
        val w = 3.dp.toPx()
        val round = abs(size.width - size.height) < 2f
        val r = if (round) size.minDimension / 2 - w / 2 else 16.dp.toPx() - w / 2
        drawRoundRect(
            ring, topLeft = Offset(w / 2, w / 2), size = Size(size.width - w, size.height - w),
            cornerRadius = CornerRadius(r, r), style = Stroke(w)
        )
    }
}

/** QR code of [link] with a hint to scan it with the phone; the bitmap is built off the main thread. */
@Composable
fun QrSheet(link: QrLink, onDismiss: () -> Unit, footer: @Composable () -> Unit = {}) {
    val c = Pamir.colors
    val qr by produceState<ImageBitmap?>(null, link.url) {
        value = withContext(Dispatchers.Default) { QRCodeDecoder.createQRCode(link.url, 600)?.asImageBitmap() }
    }
    PamirSheet(onDismiss = onDismiss, title = link.title, subtitle = link.text) {
        Spacer(Modifier.height(Gap.l))
        Box(
            Modifier
                .align(Alignment.CenterHorizontally)
                .size(260.dp)
                .clip(Radius.m)
                .background(Color.White)
                .padding(Gap.s),
            contentAlignment = Alignment.Center
        ) {
            val b = qr
            if (b != null) Image(b, contentDescription = "QR-код", modifier = Modifier.fillMaxWidth())
            else CircularProgressIndicator(color = c.accentDeep, strokeWidth = 2.dp, modifier = Modifier.size(28.dp))
        }
        Spacer(Modifier.height(Gap.m))
        Text(
            "Наведите камеру телефона на код", style = PamirType.support, color = c.textDim,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(Gap.l))
        footer()
    }
}
