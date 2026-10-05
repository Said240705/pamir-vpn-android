package com.v2ray.ang.pamir

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.util.Log
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/**
 * Payment inside the app. The provider's page (YooKassa etc.) opens in a WebView; when it sends the user
 * back to [RETURN_PAGE] the screen closes and the app checks the payment itself. Without this the browser
 * landed on the site's return page, which knows only Telegram and the web cabinet and sent the user to the bot.
 * SBP and bank links leave the WebView: the system opens the bank app, as a browser would.
 */
object PamirPay {
    const val RETURN_PAGE = "https://app.pamirlink.ru/pay-return.html"

    /** The provider's return: our return page, or a hop to the Telegram bot that page would make. */
    fun isReturn(url: String): Boolean {
        if (url.startsWith(RETURN_PAGE)) return true
        val host = Uri.parse(url).host?.lowercase().orEmpty()
        return host == "t.me" || host == "telegram.me"
    }

    /** Links that must go to another app: non-web schemes (intent:, bank apps) and the SBP bank chooser. */
    fun isExternal(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase().orEmpty()
        if (scheme != "http" && scheme != "https") return true
        val host = uri.host?.lowercase().orEmpty()
        return host == "qr.nspk.ru" || host.endsWith(".nspk.ru")
    }

    /** Opens [url] in another app; intent: links fall back to their browser_fallback_url. */
    fun openExternal(context: Context, url: String): Boolean {
        val intent = runCatching {
            if (url.startsWith("intent:")) Intent.parseUri(url, Intent.URI_INTENT_SCHEME).addCategory(Intent.CATEGORY_BROWSABLE)
            else Intent(Intent.ACTION_VIEW, Uri.parse(url))
        }.getOrNull() ?: return false
        if (runCatching { context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }.isSuccess) return true
        val fallback = intent.getStringExtra("browser_fallback_url") ?: return false
        return runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(fallback)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }.isSuccess
    }
}

/**
 * Full-screen payment page. [onReturn] — the provider sent the user back (paid or not, the app checks);
 * [onClose] — closed by the user; [onBrowser] — open the same page in the browser instead.
 */
@Composable
fun PayWebDialog(url: String, onReturn: () -> Unit, onClose: () -> Unit, onBrowser: () -> Unit) {
    val c = Pamir.colors
    var loading by remember { mutableStateOf(true) }
    var web by remember { mutableStateOf<WebView?>(null) }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        BackHandler { web?.takeIf { it.canGoBack() }?.goBack() ?: onClose() }
        Column(
            Modifier
                .fillMaxSize()
                .background(c.bg)
                .statusBarsPadding()
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = Gap.s, vertical = Gap.xs),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconAction(PamirIcons.Back, "Закрыть", onClose)
                Spacer(Modifier.width(Gap.xs))
                Text("Оплата", style = PamirType.subtitle, color = c.text, modifier = Modifier.weight(1f))
                if (loading) CircularProgressIndicator(color = c.accentText, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(Gap.s))
                TextAction("В браузере", color = c.accentText) { onBrowser() }
            }
            Box(Modifier.weight(1f)) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx -> paymentWebView(ctx, onReturn, { loading = it }).also { web = it; it.loadUrl(url) } },
                    onRelease = { it.stopLoading(); it.destroy() }
                )
            }
            Text(
                "Оплата идёт на защищённой странице платёжной системы",
                style = PamirType.support, color = c.textDim,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(Gap.s)
            )
            Spacer(Modifier.height(Gap.xs))
        }
    }
}

// JavaScript is required by the payment pages; no JS interface is exposed to them.
@SuppressLint("SetJavaScriptEnabled")
private fun paymentWebView(ctx: Context, onReturn: () -> Unit, onLoading: (Boolean) -> Unit): WebView =
    WebView(ctx).apply {
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        var returned = false
        fun handle(url: String): Boolean {
            if (PamirPay.isReturn(url)) {
                if (!returned) { returned = true; onReturn() }
                return true
            }
            val uri = Uri.parse(url)
            if (PamirPay.isExternal(uri)) {
                if (!PamirPay.openExternal(ctx, url)) Log.w("Pamir", "pay: no app for ${uri.scheme}://${uri.host}")
                return true
            }
            return false
        }
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                request.isForMainFrame && handle(request.url.toString())

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                onLoading(true)
                if (PamirPay.isReturn(url)) { view.stopLoading(); handle(url) }
            }

            override fun onPageFinished(view: WebView, url: String) = onLoading(false)
        }
    }
