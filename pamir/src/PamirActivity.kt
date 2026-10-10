package com.v2ray.ang.pamir

import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.TrafficStats
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import android.os.Process
import android.text.Html
import android.util.Log
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.LocalIndication
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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.graphics.drawable.toBitmap
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import com.v2ray.ang.AppConfig
import com.v2ray.ang.R
import com.v2ray.ang.core.LauncherManager
import com.v2ray.ang.dto.RealPingResult
import com.v2ray.ang.dto.TestServiceMessage
import com.v2ray.ang.enums.RoutingType
import com.v2ray.ang.extension.serializable
import com.v2ray.ang.extension.toast
import com.v2ray.ang.handler.AngConfigManager
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.handler.SettingsManager
import com.v2ray.ang.helper.MessageHelper
import com.v2ray.ang.ui.main.MainActivity
import com.v2ray.ang.ui.perappproxy.PerAppProxyActivity
import com.v2ray.ang.util.Utils
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL

private const val CABINET_URL = "https://app.pamirlink.ru/?from=android"
private const val BOT_URL = "https://t.me/pamirlink_bot"
private const val PREF_RU_DIRECT = "pamir_ru_direct"
private const val PREF_ROUTING_INIT = "pamir_routing_init"
private const val PREF_AUTO_BEST = "pamir_auto_best"
private const val PREF_LAST_SUB_UPDATE = "pamir_last_sub_update"
private const val PREF_USER_CHOSE = "pamir_user_chose"
private const val PREF_SMART_LTE = "pamir_smart_lte"
private const val PREF_TV_BOOT_INIT = "pamir_tv_boot_init"
private const val PREF_AUTO_LTE_ACTIVE = "pamir_auto_lte_active"
private const val PREF_PREFERRED = "pamir_preferred"
private const val UPDATE_JSON = "https://app.pamirlink.ru/download/android.json"
private const val DOWNLOAD_BASE = "https://app.pamirlink.ru/download/"
/** Latest non-prerelease build; AppConfig.APP_URL is github.com/<owner>/pamir-vpn-android after branding. */
private val GITHUB_LATEST = AppConfig.APP_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
private const val PREF_THEME = "pamir_theme"
/** Id of the account key whose subscription this phone uses (an account can hold keys for several people). */
private const val PREF_DEVICE_KEY = "pamir_device_key"
/** Favorite servers by display name: subscription updates recreate server GUIDs, names stay. */
private const val PREF_FAVORITES = "pamir_favorites"
// Navigation bar scrims for 3-button navigation, the androidx defaults.
private val NAV_SCRIM_LIGHT = android.graphics.Color.argb(0xe6, 0xFF, 0xFF, 0xFF)
private val NAV_SCRIM_DARK = android.graphics.Color.argb(0x80, 0x1b, 0x1b, 0x1b)

/** Popular apps that often refuse to work through a VPN. Only installed ones are shown. */
private val POPULAR_APPS = listOf(
    "Банки" to listOf(
        "ru.sberbankmobile", "com.idamob.tinkoff.android", "ru.vtb24.mobilebanking.android",
        "ru.alfabank.mobile.android", "ru.raiffeisennews", "ru.gazprombank.android.mobilebank.app",
        "ru.letobank.Prometheus", "ru.sovcomcard.halva.v1", "ru.psbank.mobile", "ru.mkb.mobile",
        "ru.rosbank.android", "ru.uralsib.mobile", "com.openbank", "ru.ozon.fintech.finance",
    ),
    "Госуслуги и налоги" to listOf(
        "ru.rostel", "ru.altarix.mos.pgu", "com.gnivts.selfemployed", "ru.fns.lkfl", "ru.gosuslugi.auto",
    ),
    "Покупки и доставка" to listOf(
        "ru.ozon.app.android", "com.wildberries.ru", "ru.beru.android", "com.avito.android",
        "ru.foodfox.client", "ru.sbcs.store", "ru.megamarket.marketplace", "ru.vkusvill",
    ),
    "Сервисы" to listOf(
        "ru.yandex.taxi", "ru.yandex.yandexmaps", "ru.yandex.searchplugin", "ru.yandex.music",
        "ru.kinopoisk", "ru.dublgis.dgismobile", "com.vkontakte.android", "ru.oneme.app", "ru.ok.android",
        "ru.rutube.app", "ru.mts.mymts", "ru.beeline.services", "ru.megafon.mlk", "ru.tele2.mytele2",
    ),
)

private data class PApp(val pkg: String, val label: String, val group: String, val icon: ImageBitmap?)

data class PServer(
    val guid: String,
    val flag: String,
    val name: String,
    val host: String,
    val port: Int,
    val isLte: Boolean,
    val isStub: Boolean,
    val rawRemarks: String,
)

private enum class Tab { HOME, SETTINGS, APPS, CABINET }

/** Reasons the server gives for a rejected promo code (same texts as the web cabinet). */
private val PROMO_ERRORS = mapOf(
    "not_found" to "Такого промокода не существует",
    "inactive" to "Этот промокод сейчас не активен",
    "expired" to "Срок действия промокода истёк",
    "exhausted" to "Промокод уже использован максимальное количество раз",
    "already_used" to "Вы уже использовали этот промокод",
    "already_reserved" to "Этот промокод закреплён за другим аккаунтом",
)

class PamirActivity : AppCompatActivity() {

    private var running by mutableStateOf(false)
    private var connecting by mutableStateOf(false)
    private var servers by mutableStateOf<List<PServer>>(emptyList())
    private var selected by mutableStateOf<String?>(null)
    private val pings = mutableStateMapOf<String, Int>()
    private var pingBusy by mutableStateOf(false)
    /** Servers measured through the core in this session; the quick TCP check does not overwrite them. */
    private val realPinged = mutableSetOf<String>()
    private var pingRequest: String? = null
    private var pingDone: CompletableDeferred<Unit>? = null
    private var updating by mutableStateOf(false)
    private var connectedAt by mutableLongStateOf(0L)
    private var ipInfo by mutableStateOf("")
    private var daysLeft by mutableStateOf<Int?>(null)
    private var lastUpdate by mutableLongStateOf(0L)
    private var whitelist by mutableStateOf(false)
    private var autoSwitched = false
    private var lastPrecheck = 0L
    private var newVersion by mutableStateOf<String?>(null)
    /** Download URLs of [newVersion], tried in order: GitHub first, the site as a fallback. */
    private var newVersionUrls = emptyList<String>()
    private var updProgress by mutableStateOf(-1)
    /** A release marked as required is out: only the update screen is shown and the VPN does not start. */
    private var updateRequired by mutableStateOf(PamirWatch.updateRequired())
    /** Android TV: remote control, no browser or Telegram — links are shown as QR codes. */
    private val tv by lazy { PamirTv.isTv(this) }
    private var qrLink by mutableStateOf<QrLink?>(null)
    private var assetsJob: kotlinx.coroutines.Job? = null
    private var sheetOpen by mutableStateOf(false)
    private var rxSpeed by mutableLongStateOf(0L)
    private var txSpeed by mutableLongStateOf(0L)
    private var rxTotal by mutableLongStateOf(0L)
    private var txTotal by mutableLongStateOf(0L)
    private val speedHist = mutableStateListOf<Float>()
    private var pendingReconnect = false
    private var tab by mutableStateOf(Tab.HOME)
    private var appList by mutableStateOf<List<PApp>?>(null)
    private val bypassSel = mutableStateMapOf<String, Boolean>()
    private var appsChanged = false

    // account / renewal
    private var loggedIn by mutableStateOf(PamirApi.token != null)
    private var loginBusy by mutableStateOf(false)
    private var loginJob: kotlinx.coroutines.Job? = null
    private var balanceMinor by mutableStateOf<Long?>(null)
    private var renewOpen by mutableStateOf(false)
    private var renewLoading by mutableStateOf(false)
    private var renewKeys by mutableStateOf<List<JSONObject>>(emptyList())
    private var renewKeyId by mutableStateOf<Int?>(null)
    private var tariffs by mutableStateOf<List<JSONObject>>(emptyList())
    private var payBusy by mutableStateOf<String?>(null)
    private var payState by mutableStateOf<String?>(null)   // waiting | paid | failed
    private var payUrl = ""
    private var payOrder: String? = null
    /** Payment page shown inside the app (see PamirPay); null = closed. */
    private var payWebUrl by mutableStateOf<String?>(null)
    private var payBuy = false
    /** Account keys before a purchase: the new key is the one not in this set. */
    private var payKeysBefore = emptySet<Int>()
    private var payJob: kotlinx.coroutines.Job? = null
    private var reportOpen by mutableStateOf(false)
    private var supportOpen by mutableStateOf(false)
    /** Manual update check from Settings: checking / latest / new / error; null = no dialog. */
    private var updCheck by mutableStateOf<String?>(null)
    // in-app cabinet
    private var cabLoading by mutableStateOf(false)
    private var cabLoaded by mutableStateOf(false)
    private var cabDevices by mutableStateOf<Map<Int, Pair<List<JSONObject>, Int>>>(emptyMap())
    private var cabReferral by mutableStateOf<JSONObject?>(null)
    private var cabPayments by mutableStateOf<List<JSONObject>>(emptyList())
    private var cabSupport by mutableStateOf<List<JSONObject>>(emptyList())
    private var cabTopupOpen by mutableStateOf(false)
    private var cabBusy by mutableStateOf<String?>(null)
    private var emailLoginOpen by mutableStateOf(false)
    private var news by mutableStateOf(PamirNews.cached())
    private var newsOpen by mutableStateOf(false)
    /** GET /topup/payment-method: has_card, card_type, card_last4 (card for auto-renewal). */
    private var cardInfo by mutableStateOf<JSONObject?>(null)
    private var cardBusy by mutableStateOf(false)
    private var cardUnlinkOpen by mutableStateOf(false)
    /** The card offer after a payment was answered in this session ("Не сейчас"). */
    private var cardPromptSkipped by mutableStateOf(false)
    /** Comeback discount for an expired subscription (GET /topup/last-chance-offer). */
    private var lastChance by mutableStateOf<JSONObject?>(null)
    private var activePromo by mutableStateOf(PamirOffers.activePromoPercent())
    /** The e-mail sheet opens on registration instead of sign-in. */
    private var emailRegister by mutableStateOf(false)
    private var emailBusy by mutableStateOf(false)
    /** Address that waits for the 6-digit code from the e-mail (new accounts sign in only after it). */
    private var emailCodeFor by mutableStateOf<String?>(null)
    private var emailCodeSentAt by mutableStateOf(0L)
    // which key of the account this phone uses
    private var deviceKeyId by mutableStateOf(MmkvManager.decodeSettingsString(PREF_DEVICE_KEY, "")?.toIntOrNull())
    private var keyPickerOpen by mutableStateOf(false)
    private var keyPickerMigrate by mutableStateOf(false)
    private var keyPickerLoading by mutableStateOf(false)
    /** Free trial from /topup/trial-offer: {available, offer_id, name, duration_days}; null when not offered. */
    private var trialOffer by mutableStateOf<JSONObject?>(null)
    /** The free trial is for new accounts only: once any key was bought (or a trial used) it is not offered. */
    private val trialShown get() = trialOffer != null && renewKeys.isEmpty()
    private var trialBusy by mutableStateOf(false)
    private var renameTarget by mutableStateOf<JSONObject?>(null)
    private var promoBusy by mutableStateOf(false)
    /** Result of the last promo code: true to message on success, false to the reason otherwise. */
    private var promoResult by mutableStateOf<Pair<Boolean, String>?>(null)
    /** Bumped after the location status is refreshed so the server list recomposes. */
    private var locTick by mutableStateOf(0)
    private var locLoadedAt = 0L
    private var reportBusy by mutableStateOf(false)
    // look and feel
    private var themeMode by mutableStateOf(PamirThemeMode.from(MmkvManager.decodeSettingsString(PREF_THEME, PamirThemeMode.DARK.key)))
    private var favorites by mutableStateOf(MmkvManager.decodeSettingsStringSet(PREF_FAVORITES)?.toSet() ?: emptySet())
    private val snackbar = SnackbarHostState()

    private val notifPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            if (it.resultCode == RESULT_OK) startVpn() else connecting = false
        }

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            Log.w("Pamir", "state msg ${intent?.getIntExtra("key", 0)} ${intent?.getStringExtra("content") ?: ""}")
            when (intent?.getIntExtra("key", 0)) {
                AppConfig.MSG_STATE_RUNNING, AppConfig.MSG_STATE_START_SUCCESS -> {
                    reloadServers() // the watchdog may have switched the server in the background
                    onRunning(true)
                }
                AppConfig.MSG_STATE_NOT_RUNNING, AppConfig.MSG_STATE_STOP_SUCCESS -> onRunning(false)
                AppConfig.MSG_MEASURE_CONFIG_SUCCESS -> if (intent.getStringExtra(MessageHelper.EXTRA_REQUEST_ID) == pingRequest) {
                    intent.serializable<RealPingResult>("content")?.let {
                        realPinged += it.guid
                        pings[it.guid] = if (it.delayMillis > 0) it.delayMillis.toInt() else -1
                    }
                }
                AppConfig.MSG_MEASURE_CONFIG_FINISH, AppConfig.MSG_MEASURE_CONFIG_CANCEL ->
                    if (intent.getStringExtra(MessageHelper.EXTRA_REQUEST_ID) == pingRequest) pingDone?.complete(Unit)
                AppConfig.MSG_STATE_START_FAILURE -> {
                    onRunning(false)
                    toast("Не удалось подключиться. Попробуйте другой сервер", action = "Сменить") { sheetOpen = true }
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        ContextCompat.registerReceiver(
            this, stateReceiver, IntentFilter(AppConfig.BROADCAST_ACTION_ACTIVITY), Utils.receiverFlags()
        )
        assetsJob = lifecycleScope.launch(Dispatchers.IO) {
            runCatching { SettingsManager.initAssets(applicationContext, assets) }
        }
        initRouting()
        reloadServers()
        if (tv) enableTvBootOnce()
        // TV: always dark — a light screen glares in a dark room, and the theme switch is not shown there.
        setContent { PamirTheme(if (tv) PamirThemeMode.DARK else themeMode) { Root() } }
        if (servers.isNotEmpty() && System.currentTimeMillis() - lastUpdate > 60 * 60 * 1000L) {
            updateSubscription(silent = true)
        }
        checkAppUpdate()
        PamirReminderWorker.schedule(this)
        lifecycleScope.launch(Dispatchers.IO) {
            delay(4000)
            runCatching { PamirCrash.sendPending(applicationContext, proxyPort()) }
            runCatching { PamirApi.pingInstall(applicationContext, proxyPort()) }
        }
        if (loggedIn) {
            refreshAccount()
            lifecycleScope.launch { checkDeviceKeys() }
        }
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    /** Buttons from our notifications, quick settings tile and widget. */
    private fun handleIntent(i: Intent?) {
        if (i == null) return
        if (i.getBooleanExtra(PamirWatch.EXTRA_SERVERS, false)) {
            i.removeExtra(PamirWatch.EXTRA_SERVERS)
            PamirWatch.cancelAlert(this)
            sheetOpen = true
        }
        if (i.getBooleanExtra(PamirOffers.EXTRA_OFFER, false)) {
            i.removeExtra(PamirOffers.EXTRA_OFFER)
            lifecycleScope.launch { loadLastChance(); if (lastChance != null) applyLastChance() else openRenew() }
        }
        if (i.getBooleanExtra(PamirNews.EXTRA_NEWS, false)) {
            i.removeExtra(PamirNews.EXTRA_NEWS)
            openNews()
        }
        if (i.getBooleanExtra(PamirWatch.EXTRA_RENEW, false)) {
            i.removeExtra(PamirWatch.EXTRA_RENEW)
            openRenew()
        }
        if (i.getBooleanExtra(PamirWatch.EXTRA_RECONNECT, false)) {
            i.removeExtra(PamirWatch.EXTRA_RECONNECT)
            PamirWatch.cancelAlert(this)
            pendingReconnect = true
            lifecycleScope.launch {
                delay(900) // wait for the service state answer
                if (pendingReconnect && !running && !connecting && servers.isNotEmpty()) toggle()
                pendingReconnect = false
            }
        }
    }

    override fun onResume() {
        super.onResume()
        reloadServers()
        MessageHelper.sendMsg2Service(this, AppConfig.MSG_REGISTER_CLIENT, "")
        PamirWatch.cancelAlert(this)
        if (tab == Tab.APPS) loadApps()
        if (payState == "waiting") lifecycleScope.launch { checkPayment() }
        lifecycleScope.launch { delay(1200); precheck() }
        lifecycleScope.launch { loadLocations() }
        lifecycleScope.launch { loadNews() }
        if (loggedIn) lifecycleScope.launch { loadLastChance(); if (cardInfo == null) loadPaymentMethod() }
    }

    private suspend fun loadNews() {
        val port = proxyPort()
        withContext(Dispatchers.IO) { PamirNews.fetch(port) }?.let { news = it }
    }

    private suspend fun loadPaymentMethod() {
        if (!loggedIn) return
        api(quiet = true) { p -> PamirApi.call("/topup/payment-method", proxyPort = p) }?.let { cardInfo = it }
    }

    private suspend fun loadLastChance() {
        if (!loggedIn) return
        val port = proxyPort()
        lastChance = withContext(Dispatchers.IO) { PamirOffers.fetch(port) }
    }

    private fun hasCard() = cardInfo?.optBoolean("has_card") == true

    /** Card for auto-renewal: 1 ₽ check payment (returned at once), then the card renews keys by itself. */
    private fun bindCard() {
        if (cardBusy) return
        cardBusy = true
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/topup/card-bind/start", "POST", proxyPort = p) }
            if (r == null) { cardBusy = false; return@launch }
            if (r.optBoolean("already_has_card")) {
                cardBusy = false; toast("Карта уже привязана"); loadPaymentMethod(); return@launch
            }
            val url = r.optString("payment_url"); val order = r.optString("order_id")
            if (!url.startsWith("http") || order.isBlank()) { cardBusy = false; toast("Не удалось начать привязку карты"); return@launch }
            openPayment(url, "Привязка карты", "Отсканируйте код телефоном: спишем 1 ₽ для проверки и сразу вернём")
            repeat(60) {
                delay(3000)
                val c = api(quiet = true) { p -> PamirApi.call("/topup/card-bind/check", "POST", JSONObject().put("order_id", order), proxyPort = p) }
                if (c?.optBoolean("has_card") == true) {
                    cardBusy = false
                    if (payWebUrl == url) payWebUrl = null
                    if (qrLink?.url == url) qrLink = null
                    cardPromptSkipped = true
                    toast("Карта привязана — подписка будет продлеваться сама", true)
                    loadPaymentMethod(); loadCabinet(silent = true)
                    return@launch
                }
                if (c != null && !c.optBoolean("ok") && !c.optBoolean("pending")) {
                    cardBusy = false
                    if (c.optString("reason") != "canceled") toast("Не удалось привязать карту, попробуйте ещё раз")
                    return@launch
                }
            }
            cardBusy = false
        }
    }

    private fun unlinkCard() {
        lifecycleScope.launch {
            if (api { p -> PamirApi.call("/topup/payment-method/unlink", "POST", proxyPort = p) } != null) {
                cardUnlinkOpen = false
                toast("Карта отвязана, автопродление выключено")
                loadPaymentMethod(); loadCabinet(silent = true)
            }
        }
    }

    private fun toggleAutoRenew(k: JSONObject, enabled: Boolean) {
        val id = k.optInt("id")
        renewKeys = renewKeys.map { if (it.optInt("id") == id) JSONObject(it.toString()).put("auto_renew", enabled) else it }
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/topup/keys/auto-renew", "POST", JSONObject().put("key_id", id).put("enabled", enabled), proxyPort = p) }
            if (r == null) loadCabinet(silent = true) else toast(if (enabled) "Автопродление включено" else "Автопродление выключено")
        }
    }

    /** Comeback offer: apply its code and open renewal with the discounted prices. */
    private fun applyLastChance() {
        val o = lastChance ?: return
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/topup/promo", "POST", JSONObject().put("code", o.optString("code")), proxyPort = p) } ?: return@launch
            val pct = o.optInt("discount_percent").takeIf { it > 0 } ?: 10
            val until = PamirOffers.parseUtc(o.optString("expires_at")).takeIf { it > 0 } ?: (System.currentTimeMillis() + 86_400_000L)
            PamirOffers.rememberPromo(pct, until)
            activePromo = pct
            lastChance = null
            toast(r.optString("message").ifBlank { "Скидка $pct% применится при оплате" })
            openRenew()
        }
    }

    private fun openNews() {
        PamirNews.markSeen(news)
        newsOpen = true
    }

    override fun onDestroy() {
        runCatching { MessageHelper.sendMsg2Service(this, AppConfig.MSG_UNREGISTER_CLIENT, "") }
        runCatching { unregisterReceiver(stateReceiver) }
        super.onDestroy()
    }

    // ---------- logic ----------

    private fun onRunning(value: Boolean) {
        connecting = false
        if (value && !running) {
            val at = MmkvManager.decodeSettingsLong(PamirWatch.K_CONN_AT, 0L)
            connectedAt = if (at > 0 && at <= System.currentTimeMillis()) at else System.currentTimeMillis()
            pendingReconnect = false
            fetchIp()
            askNotifications()
        }
        if (!value) {
            connectedAt = 0L
            speedHist.clear()
            rxSpeed = 0L; txSpeed = 0L
            ipInfo = ""
            autoSwitched = false
        }
        running = value
    }

    private fun askNotifications(fromSettings: Boolean = false) {
        if (android.os.Build.VERSION.SDK_INT < 33) return
        if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == android.content.pm.PackageManager.PERMISSION_GRANTED) return
        if (MmkvManager.decodeSettingsBool("pamir_notif_asked", false)) {
            if (fromSettings) {
                toast("Разрешите уведомления для Pamir VPN", true)
                runCatching {
                    startActivity(
                        Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                            .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, packageName)
                    )
                }
            }
            return
        }
        MmkvManager.encodeSettings("pamir_notif_asked", true)
        runCatching { notifPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS) }
    }

    /** Traffic of the app = everything that goes through the tunnel (the core runs under our uid). */
    private suspend fun speedLoop() {
        val uid = Process.myUid()
        var prevRx = TrafficStats.getUidRxBytes(uid)
        var prevTx = TrafficStats.getUidTxBytes(uid)
        if (prevRx < 0 || prevTx < 0) return
        var baseRx = MmkvManager.decodeSettingsLong(PamirWatch.K_BASE_RX, -1L)
        var baseTx = MmkvManager.decodeSettingsLong(PamirWatch.K_BASE_TX, -1L)
        if (baseRx < 0 || baseRx > prevRx || baseTx < 0 || baseTx > prevTx) { baseRx = prevRx; baseTx = prevTx }
        var prevT = System.nanoTime()
        rxTotal = prevRx - baseRx; txTotal = prevTx - baseTx
        while (running) {
            delay(1000)
            val rx = TrafficStats.getUidRxBytes(uid)
            val tx = TrafficStats.getUidTxBytes(uid)
            val t = System.nanoTime()
            val dt = ((t - prevT) / 1e9).coerceAtLeast(0.2)
            rxSpeed = ((rx - prevRx).coerceAtLeast(0) / dt).toLong()
            txSpeed = ((tx - prevTx).coerceAtLeast(0) / dt).toLong()
            rxTotal = (rx - baseRx).coerceAtLeast(0); txTotal = (tx - baseTx).coerceAtLeast(0)
            prevRx = rx; prevTx = tx; prevT = t
            speedHist.add(rxSpeed.toFloat())
            while (speedHist.size > 40) speedHist.removeAt(0)
        }
    }

    private fun fmtBytes(b: Long): String = when {
        b < 1024 -> "$b Б"
        b < 1024 * 1024 -> String.format("%.0f КБ", b / 1024.0)
        b < 1024L * 1024 * 1024 -> String.format(if (b < 100L * 1024 * 1024) "%.1f МБ" else "%.0f МБ", b / 1048576.0)
        else -> String.format("%.2f ГБ", b / 1073741824.0)
    }

    // ---------- account: login via Telegram, renewal, reports ----------

    private fun proxyPort(): Int? = if (running) runCatching { SettingsManager.getHttpPort() }.getOrNull()?.takeIf { it > 0 } else null

    /** Runs an API call on IO; on error shows a toast (401 = log out) and returns null. */
    private suspend fun <T> api(quiet: Boolean = false, block: (Int?) -> T): T? {
        val port = proxyPort()
        val r = withContext(Dispatchers.IO) { runCatching { block(port) } }
        r.exceptionOrNull()?.let { e ->
            Log.w("Pamir", "api error: ${e.message}")
            if (e is PamirApi.ApiError && e.code == 401) {
                logout(); if (!quiet) toast("Сессия истекла — войдите в аккаунт заново", true)
            } else if (!quiet) toast(e.message ?: "Нет связи с сервером", true)
        }
        return r.getOrNull()
    }

    private fun loginTelegram() {
        if (loginBusy) return
        loginBusy = true
        loginJob = lifecycleScope.launch {
            val start = api { p -> PamirApi.call("/auth/telegram/start", "POST", auth = false, proxyPort = p) }
            if (start == null) { loginBusy = false; return@launch }
            val token = start.optString("token")
            val link = start.optString("deep_link").replace("start=weblogin_", "start=applogin_")
            openUrl(link, "Вход через Telegram", "Отсканируйте код телефоном и подтвердите вход в Telegram", onClose = { cancelLogin() })
            val enc = Uri.encode(token)
            repeat(150) {
                delay(2000)
                val r = api(quiet = true) { p -> PamirApi.call("/auth/telegram/poll?token=$enc", auth = false, proxyPort = p) }
                if (r?.optString("status") == "approved") {
                    if (qrLink?.url == link) qrLink = null
                    PamirApi.token = r.optString("access_token")
                    loggedIn = true
                    loginBusy = false
                    Log.w("Pamir", "login ok")
                    onLoggedIn()
                    return@launch
                }
            }
            loginBusy = false
            toast("Не дождались подтверждения. Попробуйте ещё раз")
        }
    }

    private fun cancelLogin() {
        loginJob?.cancel(); loginJob = null; loginBusy = false
    }

    private fun loginEmail(email: String, password: String) {
        if (emailBusy) return
        if (!email.contains("@") || password.isBlank()) { toast("Введите почту и пароль"); return }
        emailBusy = true
        lifecycleScope.launch {
            val port = proxyPort()
            val r = withContext(Dispatchers.IO) {
                runCatching { PamirApi.call("/auth/email/login", "POST", JSONObject().put("email", email.trim()).put("password", password), auth = false, proxyPort = port) }
            }
            emailBusy = false
            r.exceptionOrNull()?.let { e ->
                Log.w("Pamir", "email login: ${e.message}")
                if (e is PamirApi.ApiError && e.code == 403 && e.message == "email_not_verified") {
                    emailCodeFor = email.trim()
                    emailCodeSentAt = System.currentTimeMillis()
                    toast("Подтвердите почту — мы отправили код на ${email.trim()}", true)
                } else toast(e.message ?: "Нет связи с сервером", true)
                return@launch
            }
            finishEmailLogin(r.getOrNull()?.optString("access_token").orEmpty(), created = false)
        }
    }

    private suspend fun finishEmailLogin(t: String, created: Boolean) {
        if (t.isBlank()) return
        PamirApi.token = t
        loggedIn = true
        emailLoginOpen = false
        emailCodeFor = null
        Log.w("Pamir", "email sign-in ok created=$created")
        if (created) toast("Аккаунт создан")
        onLoggedIn()
    }

    /** The 6-digit code from the e-mail: confirms the address and signs in. */
    private fun verifyEmailCode(code: String) {
        val email = emailCodeFor ?: return
        if (emailBusy) return
        if (code.filter { it.isDigit() }.length != 6) { toast("Введите 6 цифр из письма"); return }
        emailBusy = true
        lifecycleScope.launch {
            val r = api { p ->
                PamirApi.call("/auth/email/verify-code", "POST", JSONObject().put("email", email).put("code", code.filter { it.isDigit() }), auth = false, proxyPort = p)
            }
            emailBusy = false
            finishEmailLogin(r?.optString("access_token").orEmpty(), created = true)
        }
    }

    private fun resendEmailCode() {
        val email = emailCodeFor ?: return
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/auth/email/send-code", "POST", JSONObject().put("email", email), auth = false, proxyPort = p) }
            if (r != null) {
                emailCodeSentAt = System.currentTimeMillis()
                toast("Отправили новый код на $email")
            }
        }
    }

    /** New account by e-mail right in the app (the same /auth/email/register as the site); then like a sign-in. */
    private fun registerEmail(email: String, password: String, repeat: String) {
        if (emailBusy) return
        val e = email.trim()
        when {
            !Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$").matches(e) -> { toast("Проверьте почту — например, name@mail.ru"); return }
            password.length < 6 -> { toast("Пароль — не короче 6 символов"); return }
            password != repeat -> { toast("Пароли не совпадают"); return }
        }
        emailBusy = true
        lifecycleScope.launch {
            val r = api { p ->
                PamirApi.call("/auth/email/register", "POST", JSONObject().put("email", e).put("password", password), auth = false, proxyPort = p)
            }
            emailBusy = false
            if (r?.optString("status") == "code_sent") {
                emailCodeFor = e
                emailCodeSentAt = System.currentTimeMillis()
                return@launch
            }
            finishEmailLogin(r?.optString("access_token").orEmpty(), created = true)
        }
    }

    private fun forgotPassword(email: String) {
        if (!email.contains("@")) { toast("Сначала введите почту"); return }
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/auth/email/forgot-password", "POST", JSONObject().put("email", email.trim()), auth = false, proxyPort = p) }
            if (r != null) toast("Если почта зарегистрирована, мы отправили ссылку для сброса пароля", true)
        }
    }

    /**
     * Runs [block] on the IO pool and gives up waiting after [ms]: a subscription download that hangs (bad network,
     * blocked host) must not keep the "Обновляем…" spinner forever. Null on failure or timeout.
     */
    private suspend fun <T> ioTimeout(ms: Long, block: () -> T): T? {
        val job = lifecycleScope.async(Dispatchers.IO) { runCatching(block).onFailure { Log.w("Pamir", "io: ${it.message}") }.getOrNull() }
        return withTimeoutOrNull(ms) { job.await() } ?: run { if (job.isActive) Log.w("Pamir", "io: timed out after $ms ms"); null }
    }

    /** "Выйти из аккаунта": the VPN stops and the account's keys leave this phone; keys added by hand stay. */
    private fun signOut() {
        lifecycleScope.launch {
            if (running || connecting) LauncherManager.stopService(this@PamirActivity)
            val keys = renewKeys.ifEmpty {
                api(quiet = true) { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys")
                    ?.let { ka -> (0 until ka.length()).map { ka.getJSONObject(it) } }.orEmpty()
            }
            val urls = keys.map { subKey(it.optString("subscription_url")) }.filter { it.startsWith("http") }.toSet()
            ioTimeout(15_000) {
                deviceSubs().filter { subKey(it.subscription.url) in urls }
                    .forEach { sub -> runCatching { SettingsManager.removeSubscriptionWithDefault(sub.guid) }.onFailure { Log.w("Pamir", "sign out: remove sub: ${it.message}") } }
            }
            logout()
            reloadServers()
            toast("Вы вышли из аккаунта. VPN отключён")
        }
    }

    private fun logout() {
        PamirApi.token = null
        loggedIn = false
        // Everything below belongs to the account: after the next sign-in (maybe another account)
        // the cabinet, banners and renewal must not show the previous one.
        balanceMinor = null
        renewKeys = emptyList()
        renewKeyId = null
        tariffs = emptyList()
        cabLoaded = false
        cabDevices = emptyMap()
        cabReferral = null
        cabPayments = emptyList()
        cabSupport = emptyList()
        cardInfo = null
        lastChance = null
        trialOffer = null
        promoResult = null
        deviceKeyId = null
        MmkvManager.encodeSettings(PREF_DEVICE_KEY, "")
        PamirOffers.clearPromo(); activePromo = null
    }

    private fun refreshAccount() {
        lifecycleScope.launch {
            val me = api(quiet = true) { p -> PamirApi.call("/auth/me", proxyPort = p) } ?: return@launch
            balanceMinor = if (me.isNull("balance")) null else me.optLong("balance")
        }
    }

    /**
     * After login: put one key on this phone. A single active key (or the one already installed here) is used
     * right away; with several keys the user picks theirs, the others can be sent to family from the cabinet.
     * Then the cabinet opens (subscription, trial, tariffs), unless the login started in the renewal sheet.
     */
    private suspend fun onLoggedIn() {
        val fromRenew = renewOpen
        if (!fromRenew && !tv) tab = Tab.CABINET
        refreshAccount()
        val keys = api { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys") ?: return
        val list = (0 until keys.length()).map { keys.getJSONObject(it) }
        renewKeys = list
        val active = activeKeys(list)
        if (active.isEmpty()) {
            toast(if (list.isEmpty()) "Вы вошли. Подписки пока нет — выберите тариф" else "Вы вошли. Подписка закончилась — продлите её", true)
            if (fromRenew || tv) openRenew()
            return
        }
        val onDevice = keysOnDevice(active)
        when {
            active.size == 1 -> applyDeviceKey(active[0])
            onDevice.size == 1 -> {
                rememberDeviceKey(onDevice[0])
                toast("Вы вошли в аккаунт")
            }
            else -> openKeyPicker(migrate = onDevice.size > 1)
        }
        if (renewOpen && payState != "paid") openRenew()
    }

    /**
     * After buying a subscription: the server creates the key a few seconds after the payment, so wait for it
     * (up to ~30 s) and put it on this phone. The renewal sheet keeps showing "Оплата прошла" meanwhile.
     */
    private suspend fun afterPurchase() {
        repeat(10) {
            val ka = api(quiet = true) { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys")
            val list = if (ka == null) emptyList() else (0 until ka.length()).map { ka.getJSONObject(it) }
            if (list.isNotEmpty()) renewKeys = list
            val active = activeKeys(list)
            val fresh = active.firstOrNull { it.optInt("id") !in payKeysBefore }
            val key = fresh ?: active.firstOrNull().takeIf { keysOnDevice(active).isEmpty() }
            if (key != null) {
                applyDeviceKey(key)
                loadCabinet(silent = true)
                return
            }
            if (active.isNotEmpty()) { updateSubscription(silent = true); return }
            delay(3000)
        }
        toast("Оплата прошла. Ключ появится через минуту — загляните в кабинет", true)
    }

    // ---------- keys on this phone ----------

    private fun subKey(url: String) = url.trim().trimEnd('/')

    private fun keyName(k: JSONObject) = k.optString("display_name").takeIf { it.isNotBlank() && it != "null" } ?: "Ключ #${k.optInt("id")}"

    private fun activeKeys(list: List<JSONObject>) =
        list.filter { it.optBoolean("is_active") && it.optString("subscription_url").startsWith("http") }

    private fun deviceSubs() = runCatching { MmkvManager.decodeSubscriptions() }.getOrDefault(emptyList())

    /** Account keys whose subscription is installed on this phone. */
    private fun keysOnDevice(keys: List<JSONObject>): List<JSONObject> {
        val mine = deviceSubs().map { subKey(it.subscription.url) }.toSet()
        return keys.filter { subKey(it.optString("subscription_url")) in mine }
    }

    private fun rememberDeviceKey(k: JSONObject) {
        deviceKeyId = k.optInt("id")
        MmkvManager.encodeSettings(PREF_DEVICE_KEY, k.optInt("id").toString())
    }

    /** Start: an older login may have installed every key of the account here; then ask which one to keep. */
    private suspend fun checkDeviceKeys() {
        val keys = api(quiet = true) { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys") ?: return
        val list = (0 until keys.length()).map { keys.getJSONObject(it) }
        renewKeys = list
        val onDevice = keysOnDevice(list)
        when {
            onDevice.size > 1 -> openKeyPicker(migrate = true)
            onDevice.size == 1 && deviceKeyId != onDevice[0].optInt("id") -> rememberDeviceKey(onDevice[0])
        }
    }

    private fun openKeyPicker(migrate: Boolean = false) {
        keyPickerMigrate = migrate
        keyPickerOpen = true
        if (renewKeys.isEmpty() && loggedIn) lifecycleScope.launch {
            keyPickerLoading = true
            api { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys")?.let { ka -> renewKeys = (0 until ka.length()).map { ka.getJSONObject(it) } }
            keyPickerLoading = false
        }
    }

    /**
     * Makes [key] the only key of this account on the phone: removes the subscriptions of the account's other keys
     * (subscriptions added by hand from elsewhere stay), imports this one if missing and reconnects if needed.
     */
    private suspend fun applyDeviceKey(key: JSONObject) {
        val url = key.optString("subscription_url")
        val accountUrls = renewKeys.map { subKey(it.optString("subscription_url")) }.toSet()
        updating = true
        val ok = ioTimeout(60_000) {
            deviceSubs().filter { subKey(it.subscription.url) in accountUrls && subKey(it.subscription.url) != subKey(url) }
                .forEach { sub -> runCatching { SettingsManager.removeSubscriptionWithDefault(sub.guid) }.onFailure { Log.w("Pamir", "remove sub: ${it.message}") } }
            if (deviceSubs().any { subKey(it.subscription.url) == subKey(url) }) true
            else runCatching { AngConfigManager.importBatchConfig(url, "", false) }
                .onFailure { Log.w("Pamir", "import key: ${it.message}") }.getOrNull()?.let { it.first + it.second > 0 } ?: false
        } ?: false
        updating = false
        if (!ok) {
            toast("Не удалось подключить ключ. Проверьте интернет", action = "Повторить") { lifecycleScope.launch { applyDeviceKey(key) } }
            return
        }
        rememberDeviceKey(key)
        keyPickerOpen = false
        MmkvManager.encodeSettings(PREF_USER_CHOSE, false) // servers changed: start from the first server of this key
        MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, System.currentTimeMillis())
        reloadServers()
        if (running) LauncherManager.restartService(this)
        toast("Готово! На этом телефоне: ${keyName(key)}")
    }

    private suspend fun loadTrialOffer() {
        val o = api(quiet = true) { p -> PamirApi.call("/topup/trial-offer", proxyPort = p) }
        trialOffer = o?.takeIf { it.optBoolean("available") && it.has("offer_id") }
    }

    /** Activates the free trial; the new key goes straight onto this phone. */
    private fun activateTrial() {
        val offer = trialOffer ?: return
        if (trialBusy) return
        trialBusy = true
        lifecycleScope.launch {
            val before = renewKeys.map { it.optInt("id") }.toSet()
            val r = api { p -> PamirApi.call("/topup/trial-activate", "POST", JSONObject().put("offer_id", offer.optInt("offer_id")), proxyPort = p) }
            if (r == null) { trialBusy = false; return@launch }
            trialOffer = null
            val ka = api { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys")
            val list = if (ka == null) emptyList() else (0 until ka.length()).map { ka.getJSONObject(it) }
            if (list.isNotEmpty()) renewKeys = list
            val key = activeKeys(list).firstOrNull { it.optInt("id") !in before } ?: activeKeys(list).firstOrNull()
            trialBusy = false
            if (key != null) {
                renewOpen = false
                applyDeviceKey(key)
            } else {
                toast("Пробный период активирован. Ключ появится в кабинете через минуту", true)
            }
            loadCabinet(silent = true)
        }
    }

    private fun renameKey(k: JSONObject, name: String) {
        val n = name.trim()
        if (n.isEmpty() || cabBusy != null) return
        cabBusy = "rename"
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/auth/keys/rename", "POST", JSONObject().put("key_id", k.optInt("id")).put("new_name", n), proxyPort = p) }
            cabBusy = null
            if (r == null) return@launch
            renewKeys = renewKeys.map { if (it.optInt("id") == k.optInt("id")) JSONObject(it.toString()).put("display_name", n) else it }
            renameTarget = null
            toast("Ключ переименован: $n")
        }
    }

    /** Same promo codes as in the web cabinet: the discount applies to the next payment. */
    private fun applyPromo(code: String) {
        val value = code.trim()
        if (value.isEmpty() || promoBusy) return
        promoBusy = true
        promoResult = null
        lifecycleScope.launch {
            val port = proxyPort()
            val r = withContext(Dispatchers.IO) {
                runCatching { PamirApi.call("/topup/promo", "POST", JSONObject().put("code", value), proxyPort = port) }
            }
            promoBusy = false
            r.onSuccess {
                val msg = it.optString("message").ifBlank { "Промокод применён — скидка учтётся при оплате" }
                promoResult = true to msg
                // the server answers with text only; the percent in it lets the tariffs show discounted prices
                Regex("(\\d{1,2})\\s*%").find(msg)?.groupValues?.get(1)?.toIntOrNull()?.takeIf { p -> p in 1..99 }?.let { p ->
                    PamirOffers.rememberPromo(p, System.currentTimeMillis() + 86_400_000L)
                    activePromo = p
                }
            }.onFailure { e ->
                Log.w("Pamir", "promo: ${e.message}")
                if (e is PamirApi.ApiError && e.code == 401) {
                    logout(); toast("Сессия истекла — войдите в аккаунт заново", true)
                    return@onFailure
                }
                promoResult = false to (PROMO_ERRORS[e.message] ?: e.message ?: "Не удалось применить промокод")
            }
        }
    }

    /** Location status for the server list and auto switch (public, no login). At most once a minute. */
    private suspend fun loadLocations(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - locLoadedAt < 60_000L) return
        locLoadedAt = now
        val r = api(quiet = true) { p -> PamirApi.call("/topup/public/server-status", auth = false, proxyPort = p) } ?: return
        r.optJSONArray("servers")?.let { PamirLocations.save(it); locTick++ }
    }

    /** Message for WhatsApp/Telegram: how to install the app and connect this key on another phone. */
    private fun shareKey(k: JSONObject) {
        // open-app.html opens Pamir VPN with the key on Android and offers Incy/Happ on iPhone
        val link = "https://app.pamirlink.ru/open-app.html?url=" + Uri.encode(k.optString("subscription_url"))
        val text = "Pamir VPN — ключ «${keyName(k)}»\n\n" +
            "Откройте ссылку на телефоне — VPN подключится в один клик:\n$link\n\n" +
            "Если приложения ещё нет, ссылка предложит его скачать."
        runCatching {
            startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text), "Отправить ключ"))
        }
    }

    private fun mySubUrls(): Set<String> = deviceSubs().map { subKey(it.subscription.url) }.toSet()

    /** Renewal inside the app (tariffs + payment); without login — offer to log in. */
    private fun openRenew(forceKeyId: Int? = null) {
        renewOpen = true
        if (payState == "paid" || payState == "failed") payState = null
        if (!loggedIn) return
        renewLoading = true
        lifecycleScope.launch {
            refreshAccount()
            val keysJ = api { p -> PamirApi.call("/auth/keys", proxyPort = p) }
            val tarJ = api(quiet = true) { p -> PamirApi.call("/topup/tariffs", proxyPort = p) }
            loadTrialOffer()
            renewLoading = false
            if (keysJ == null) return@launch
            val ka = keysJ.optJSONArray("keys")
            val list = if (ka == null) emptyList() else (0 until ka.length()).map { ka.getJSONObject(it) }
            renewKeys = list
            val mine = mySubUrls()
            renewKeyId = forceKeyId ?: (list.firstOrNull { it.optInt("id") == deviceKeyId }
                ?: list.firstOrNull { subKey(it.optString("subscription_url")) in mine }
                ?: list.firstOrNull { it.optBoolean("is_active") } ?: list.firstOrNull())?.optInt("id")
            val ta = tarJ?.optJSONArray("tariffs")
            tariffs = if (ta == null) emptyList() else (0 until ta.length()).map { ta.getJSONObject(it) }
        }
    }

    private fun pay(tariffId: Int, method: String) {
        if (payBusy != null) return
        payBusy = "$tariffId:$method"
        lifecycleScope.launch {
            val keyId = renewKeyId
            val buy = keyId == null
            val body = JSONObject().put("tariff_id", tariffId).put("method", method)
            if (!buy) body.put("key_id", keyId)
            val r = api { p -> PamirApi.call(if (buy) "/topup/purchase" else "/topup/renew", "POST", body, proxyPort = p) }
            payBusy = null
            if (r == null) return@launch
            payBuy = buy
            payKeysBefore = renewKeys.map { it.optInt("id") }.toSet()
            when {
                r.optString("payment_url").startsWith("http") -> {
                    payUrl = r.optString("payment_url")
                    payOrder = r.optString("order_id").takeIf { it.isNotBlank() }
                    payState = "waiting"
                    openPayment(payUrl, "Оплата", "Отсканируйте код телефоном и оплатите — подписка продлится сама")
                    watchPayment()
                }
                r.optBoolean("completed") || r.optBoolean("ok") -> onPaid()
            }
        }
    }

    private fun watchPayment() {
        payJob?.cancel()
        payJob = lifecycleScope.launch {
            repeat(200) {
                delay(4000)
                if (checkPayment()) return@launch
            }
            // ~13 minutes without an answer: stop the spinner instead of waiting forever.
            if (payState == "waiting") {
                payState = null
                toast("Не дождались подтверждения оплаты. Если деньги списались — напишите в поддержку", true)
            }
        }
    }

    /** Payment page: inside the app on a phone, as a QR code on a TV. */
    private fun openPayment(url: String, title: String, text: String) {
        if (tv) openUrl(url, title, text) else payWebUrl = url
    }

    /** The payment page closed (by the user or after the provider's return): check right away. */
    private fun onPaymentPageClosed() {
        payWebUrl = null
        if (payState == "waiting") lifecycleScope.launch { checkPayment() }
    }

    /** true = finished (paid or failed). */
    private suspend fun checkPayment(): Boolean {
        val order = payOrder ?: return false
        if (payState != "waiting") return true
        val r = api(quiet = true) { p -> PamirApi.call("/topup/payment-status?order_id=${Uri.encode(order)}", proxyPort = p) } ?: return false
        val st = r.optString("status")
        return when {
            st == "paid" -> { onPaid(); true }
            Regex("cancel|fail|expire|reject|declin").containsMatchIn(st) -> { payState = "failed"; true }
            else -> false
        }
    }

    private fun onPaid() {
        payState = "paid"
        payWebUrl = null
        PamirOffers.clearPromo(); activePromo = null
        lifecycleScope.launch { loadPaymentMethod() }
        if (qrLink?.url == payUrl) qrLink = null
        payJob?.cancel()
        Log.w("Pamir", "payment ok buy=$payBuy")
        lifecycleScope.launch {
            delay(1500)
            refreshAccount()
            if (payBuy) afterPurchase() else updateSubscription(silent = true)
        }
    }

    private fun sendReport(text: String, withLog: Boolean) {
        if (reportBusy) return
        reportBusy = true
        lifecycleScope.launch {
            val ok = api { p ->
                val log = if (withLog) PamirApi.recentLog() else ""
                PamirApi.report(applicationContext, "feedback", text, log, p)
            } != null
            reportBusy = false
            if (ok) {
                reportOpen = false
                toast("Спасибо! Сообщение отправлено, разберёмся", true)
            }
        }
    }


    // ---------- in-app cabinet ----------

    private fun loadCabinet(silent: Boolean = false) {
        if (!loggedIn || cabLoading) return
        cabLoading = !silent || !cabLoaded
        lifecycleScope.launch {
            val me = api(quiet = true) { p -> PamirApi.call("/auth/me", proxyPort = p) }
            if (me != null) balanceMinor = if (me.isNull("balance")) null else me.optLong("balance")
            val keysJ = api(quiet = true) { p -> PamirApi.call("/auth/keys", proxyPort = p) }
            keysJ?.optJSONArray("keys")?.let { ka -> renewKeys = (0 until ka.length()).map { ka.getJSONObject(it) } }
            val dev = mutableMapOf<Int, Pair<List<JSONObject>, Int>>()
            renewKeys.filter { it.optBoolean("is_active") }.take(4).forEach { k ->
                val id = k.optInt("id")
                val d = api(quiet = true) { p -> PamirApi.call("/topup/devices?key_id=$id", proxyPort = p) }
                val arr = d?.optJSONArray("devices")
                if (d != null) dev[id] = Pair(if (arr == null) emptyList() else (0 until arr.length()).map { arr.getJSONObject(it) }, d.optInt("limit"))
            }
            cabDevices = dev
            cabReferral = api(quiet = true) { p -> PamirApi.call("/topup/referral", proxyPort = p) }
            loadPaymentMethod()
            loadLastChance()
            loadTrialOffer()
            val from = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date(System.currentTimeMillis() - 365L * 86_400_000))
            val pj = api(quiet = true) { p -> PamirApi.call("/topup/payments?date_from=$from", proxyPort = p) }
            pj?.optJSONArray("payments")?.let { a -> cabPayments = (0 until a.length()).map { a.getJSONObject(it) } }
            loadSupport()
            cabLoading = false
            cabLoaded = true
        }
    }

    private suspend fun loadSupport() {
        val sj = api(quiet = true) { p -> PamirApi.call("/topup/support/messages", proxyPort = p) } ?: return
        sj.optJSONArray("messages")?.let { a -> cabSupport = (0 until a.length()).map { a.getJSONObject(it) } }
    }

    private fun removeDevice(keyId: Int, deviceId: Int) {
        if (cabBusy != null) return
        cabBusy = "dev$deviceId"
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/topup/device-remove", "POST", JSONObject().put("key_id", keyId).put("device_id", deviceId), proxyPort = p) }
            cabBusy = null
            if (r != null) {
                toast("Устройство отключено")
                loadCabinet(silent = true)
            }
        }
    }

    private fun topUp(amount: Int) {
        if (cabBusy != null) return
        cabBusy = "topup"
        lifecycleScope.launch {
            val before = balanceMinor ?: 0L
            val r = api { p -> PamirApi.call("/topup", "POST", JSONObject().put("amount", amount), proxyPort = p) }
            cabBusy = null
            val url = r?.optString("payment_url").orEmpty()
            if (!url.startsWith("http")) return@launch
            cabTopupOpen = false
            openPayment(url, "Пополнение баланса", "Отсканируйте код телефоном и оплатите — баланс обновится сам")
            payJob?.cancel()
            payJob = lifecycleScope.launch {
                repeat(60) {
                    delay(5000)
                    refreshAccount()
                    delay(300)
                    if ((balanceMinor ?: 0L) > before) {
                        if (qrLink?.url == url) qrLink = null
                        if (payWebUrl == url) payWebUrl = null
                        toast("Баланс пополнен: ${rub(balanceMinor ?: 0L)}", true)
                        loadCabinet(silent = true)
                        return@launch
                    }
                }
            }
        }
    }

    private fun sendSupport(text: String) {
        val t = text.trim()
        if (t.isEmpty() || cabBusy != null) return
        cabBusy = "support"
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/topup/support/send", "POST", JSONObject().put("text", t), proxyPort = p) }
            cabBusy = null
            if (r != null) { loadSupport(); toast("Отправлено. Ответ придёт сюда и в Telegram") }
        }
    }

    private fun copyText(label: String, text: String) {
        runCatching {
            (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
            toast("Скопировано")
        }
    }

    private fun fmtDate(raw: String?): String {
        val d = (raw ?: "").take(10).split("-")
        return if (d.size == 3) "${d[2]}.${d[1]}.${d[0]}" else ""
    }

    private fun daysUntil(raw: String?): Int? = runCatching {
        val d = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).parse((raw ?: "").take(10)) ?: return null
        Math.ceil((d.time - System.currentTimeMillis()) / 86_400_000.0).toInt()
    }.getOrNull()

    private fun rub(minor: Long): String {
        val v = minor / 100.0
        return (if (v % 1.0 == 0.0) String.format("%,.0f", v) else String.format("%,.2f", v)).replace(',', ' ') + " ₽"
    }

    // ---------- apps without VPN ----------

    private fun bypassSet(): MutableSet<String> {
        val on = MmkvManager.decodeSettingsBool(AppConfig.PREF_PER_APP_PROXY, false) &&
            MmkvManager.decodeSettingsBool(AppConfig.PREF_BYPASS_APPS, false)
        return if (on) MmkvManager.decodeSettingsStringSet(AppConfig.PREF_PER_APP_PROXY_SET)?.toMutableSet() ?: mutableSetOf()
        else mutableSetOf()
    }

    private fun bypassCount(): Int = bypassSet().count { it != packageName }

    private fun loadApps() {
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) {
                POPULAR_APPS.flatMap { (group, pkgs) ->
                    pkgs.mapNotNull { pkg ->
                        runCatching {
                            val ai = packageManager.getApplicationInfo(pkg, 0)
                            val icon = runCatching { packageManager.getApplicationIcon(ai).toBitmap(96, 96).asImageBitmap() }.getOrNull()
                            PApp(pkg, packageManager.getApplicationLabel(ai).toString(), group, icon)
                        }.getOrNull()
                    }
                }
            }
            val set = bypassSet()
            bypassSel.clear()
            list.forEach { bypassSel[it.pkg] = it.pkg in set }
            appList = list
        }
    }

    private fun setBypass(pkgs: List<String>, on: Boolean) {
        val set = bypassSet()
        if (on) set.addAll(pkgs) else set.removeAll(pkgs.toSet())
        set.remove(packageName)
        MmkvManager.encodeSettings(AppConfig.PREF_PER_APP_PROXY_SET, set)
        MmkvManager.encodeSettings(AppConfig.PREF_BYPASS_APPS, true)
        MmkvManager.encodeSettings(AppConfig.PREF_PER_APP_PROXY, set.isNotEmpty())
        pkgs.forEach { bypassSel[it] = on }
        appsChanged = true
    }

    private fun applyAppsIfChanged() {
        if (!appsChanged) return
        appsChanged = false
        if (running) {
            LauncherManager.restartService(this)
            toast("Исключения применены — переподключаемся")
        }
    }

    private fun initRouting() {
        if (!MmkvManager.decodeSettingsBool(PREF_ROUTING_INIT, false)) {
            runCatching { SettingsManager.resetRoutingRulesetsFromPresets(this, RoutingType.WHITE_RUSSIA) }
            MmkvManager.encodeSettings(PREF_RU_DIRECT, true)
            MmkvManager.encodeSettings(PREF_ROUTING_INIT, true)
        }
        if (!MmkvManager.decodeSettingsBool("pamir_speed_init", false)) {
            MmkvManager.encodeSettings(AppConfig.PREF_SPEED_ENABLED, true)
            MmkvManager.encodeSettings("pamir_speed_init", true)
        }
    }

    private fun reloadServers() {
        val list = MmkvManager.decodeAllServerList().mapNotNull { guid ->
            val p = MmkvManager.decodeServerConfig(guid) ?: return@mapNotNull null
            val (flag, name) = cleanName(p.remarks)
            val host = p.server.orEmpty()
            PServer(
                guid = guid,
                flag = flag,
                name = name,
                host = host,
                port = p.serverPort?.toIntOrNull() ?: 443,
                isLte = name.contains("LTE", true) || p.network == "xhttp",
                isStub = host.startsWith("127.") || host == "localhost",
                rawRemarks = p.remarks,
            )
        }
        servers = list
        daysLeft = PamirWatch.daysLeft()
        lastUpdate = MmkvManager.decodeSettingsLong(PREF_LAST_SUB_UPDATE, 0L)
        if (lastUpdate == 0L && list.isNotEmpty()) {
            lastUpdate = System.currentTimeMillis()
            MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, lastUpdate)
        }
        var sel = MmkvManager.getSelectServer()
        if (!MmkvManager.decodeSettingsBool(PREF_USER_CHOSE, false)) {
            list.firstOrNull { !it.isStub && !it.isLte }?.let { sel = it.guid; MmkvManager.setSelectServer(it.guid) }
        }
        if (sel == null || list.none { it.guid == sel }) {
            sel = list.firstOrNull { !it.isStub && !it.isLte }?.guid ?: list.firstOrNull()?.guid
            sel?.let { MmkvManager.setSelectServer(it) }
        }
        selected = sel
    }

    private fun cleanName(remarks: String): Pair<String, String> = PamirWatch.cleanName(remarks)

    private fun toggle() {
        Log.w("Pamir", "toggle running=$running connecting=$connecting selected=$selected")
        if (connecting) return
        if (updateRequired && !running) return
        if (running) {
            LauncherManager.stopService(this)
            return
        }
        val sel = selected ?: run { toast("Нет доступных серверов"); return }
        if (servers.firstOrNull { it.guid == sel }?.isStub == true) {
            toast("Подписка не активна или исчерпан лимит устройств")
            return
        }
        val cur = servers.firstOrNull { it.guid == sel }
        if (cur != null && !cur.isLte && whitelist && smartLte()) {
            lteServer()?.let {
                useLte(it)
                toast("Обычные серверы недоступны — подключаем LTE Обход")
            }
        }
        connecting = true
        val intent = VpnService.prepare(this)
        Log.w("Pamir", "vpn prepare needed=${intent != null}")
        if (intent == null) startVpn() else vpnPermission.launch(intent)
    }

    private fun startVpn() {
        val sel = selected ?: return
        Log.w("Pamir", "startService $sel")
        lifecycleScope.launch {
            assetsJob?.join()
            LauncherManager.startService(this@PamirActivity, sel)
        }
        lifecycleScope.launch {
            delay(12000)
            if (connecting) connecting = false
        }
    }

    private fun selectServer(guid: String) {
        selected = guid
        MmkvManager.setSelectServer(guid)
        MmkvManager.encodeSettings(PREF_AUTO_BEST, false)
        MmkvManager.encodeSettings(PREF_USER_CHOSE, true)
        if (running) {
            connecting = true
            LauncherManager.restartService(this)
            lifecycleScope.launch { delay(3000); connecting = false; fetchIp() }
        }
    }

    private fun pickBest() {
        lifecycleScope.launch {
            runPing()
            val best = servers.filter { !it.isStub && !it.isLte && (pings[it.guid] ?: -1) > 0 && !PamirLocations.isDown(it.rawRemarks) }
                .minByOrNull { pings[it.guid] ?: Int.MAX_VALUE }
            if (best != null) {
                selectServer(best.guid)
                MmkvManager.encodeSettings(PREF_AUTO_BEST, true)
                toast("Выбран ${best.name}")
            } else toast("Не удалось проверить серверы")
        }
    }

    /**
     * Server check. [real] measures a request through each server with the core (v2rayNG CoreTestService,
     * separate process, results arrive in [stateReceiver]); otherwise a quick TCP connect, used for the
     * silent background check. When the core test gives nothing in time, the TCP check is used instead.
     */
    private suspend fun runPing(real: Boolean = true) {
        if (pingBusy) return
        pingBusy = true
        val targets = servers.filter { !it.isStub }
        var measured = false
        if (real && targets.isNotEmpty()) {
            val id = java.util.UUID.randomUUID().toString()
            val done = CompletableDeferred<Unit>()
            pingRequest = id
            pingDone = done
            targets.forEach { realPinged -= it.guid }
            MessageHelper.sendMsg2TestService(this, TestServiceMessage(AppConfig.MSG_MEASURE_CONFIG_START, serverGuids = targets.map { it.guid }), id)
            withTimeoutOrNull(45_000) { done.await() }
            pingRequest = null
            pingDone = null
            measured = targets.any { it.guid in realPinged }
            if (measured) targets.filter { it.guid !in realPinged }.forEach { pings[it.guid] = -1 }
            Log.w("Pamir", "real ping: ${targets.count { it.guid in realPinged }}/${targets.size} answered")
        }
        if (!measured) {
            withContext(Dispatchers.IO) {
                targets.map { s ->
                    async {
                        val ms = runCatching {
                            val t0 = System.nanoTime()
                            Socket().use { it.connect(InetSocketAddress(s.host, s.port), 3000) }
                            ((System.nanoTime() - t0) / 1_000_000).toInt()
                        }.getOrDefault(-1)
                        s.guid to ms
                    }
                }.awaitAll()
            }.forEach { (g, ms) -> if (g !in realPinged) pings[g] = ms }
        }
        pingBusy = false
    }

    private fun fetchIp() {
        lifecycleScope.launch {
            delay(2000)
            var info: com.v2ray.ang.handler.SpeedtestManager.RemoteEndpointInfo? = null
            for (i in 0 until 2) {
                if (!running) return@launch
                info = withContext(Dispatchers.IO) { runCatching { com.v2ray.ang.handler.SpeedtestManager.getRemoteIPInfo() }.getOrNull() }
                if (info?.ipAddress != null) break
                delay(2500)
            }
            if (!running) return@launch
            val ip = info?.ipAddress
            if (ip != null) {
                ipInfo = if (info?.country.isNullOrBlank()) ip else "$ip (${info?.country})"
                Log.w("Pamir", "ip ok $ipInfo")
                return@launch
            }
            Log.w("Pamir", "ip check failed")
            val cur = servers.firstOrNull { it.guid == selected }
            val lte = lteServer()
            if (cur != null && !cur.isLte && lte != null && smartLte() && !autoSwitched) {
                autoSwitched = true
                useLte(lte)
                toast("Сервер не отвечает — переключили на LTE Обход", true)
                connecting = true
                LauncherManager.restartService(this@PamirActivity)
                delay(3000); connecting = false
                fetchIp()
            } else {
                ipInfo = "нет ответа"
                toast("Нет соединения через VPN. Попробуйте другой сервер", true, action = "Сменить") { sheetOpen = true }
            }
        }
    }

    /** Not on TV: it is on Wi-Fi or cable, and the LTE settings are not shown there. */
    private fun smartLte() = !tv && MmkvManager.decodeSettingsBool(PREF_SMART_LTE, true)

    private fun lteServer(): PServer? = servers.firstOrNull { it.isLte && !it.isStub }

    private fun useLte(lte: PServer) {
        val prev = selected
        if (prev != null && servers.firstOrNull { it.guid == prev }?.isLte == false) {
            MmkvManager.encodeSettings(PREF_PREFERRED, prev)
        }
        MmkvManager.encodeSettings(PREF_AUTO_LTE_ACTIVE, true)
        selected = lte.guid
        MmkvManager.setSelectServer(lte.guid)
    }

    /** Checks whether regular servers are reachable (white lists) and restores the preferred server. */
    private suspend fun precheck() {
        if (running || connecting || servers.isEmpty()) return
        if (System.currentTimeMillis() - lastPrecheck < 60_000) return
        lastPrecheck = System.currentTimeMillis()
        runPing(real = false)
        val normal = servers.filter { !it.isStub && !it.isLte }
        val reachable = normal.any { (pings[it.guid] ?: -1) > 0 }
        whitelist = normal.isNotEmpty() && !reachable && lteServer() != null
        Log.w("Pamir", "precheck reachable=$reachable whitelist=$whitelist")
        if (reachable && MmkvManager.decodeSettingsBool(PREF_AUTO_LTE_ACTIVE, false)) {
            val pref = MmkvManager.decodeSettingsString(PREF_PREFERRED, "") ?: ""
            val back = normal.firstOrNull { it.guid == pref } ?: normal.firstOrNull()
            if (back != null) {
                selected = back.guid
                MmkvManager.setSelectServer(back.guid)
            }
            MmkvManager.encodeSettings(PREF_AUTO_LTE_ACTIVE, false)
        }
    }

    /** A published app build: version and where its APK for this device can be downloaded. */
    private class UpdateSource(val version: String, val url: String, val minVersion: String)

    private fun httpGet(url: String, accept: String? = null): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 6000; c.readTimeout = 6000
        c.setRequestProperty("Cache-Control", "no-cache")
        if (accept != null) c.setRequestProperty("Accept", accept)
        return c.inputStream.bufferedReader().use { it.readText() }
    }

    private fun prefersArm64() = android.os.Build.SUPPORTED_ABIS.contains("arm64-v8a")

    /** GitHub releases: fixed-name copies (pamir-vpn.apk, pamir-vpn-universal.apk) or the versioned APKs. */
    private fun updateFromGithub(): UpdateSource? {
        val o = JSONObject(httpGet(GITHUB_LATEST, "application/vnd.github+json"))
        val v = o.optString("tag_name").removePrefix("v")
        val assets = o.optJSONArray("assets") ?: return null
        val urls = (0 until assets.length()).associate { assets.getJSONObject(it).let { a -> a.optString("name") to a.optString("browser_download_url") } }
        fun pick(fixed: String, suffix: String) = urls[fixed] ?: urls.entries.firstOrNull { it.key.endsWith(suffix) }?.value
        val url = (if (prefersArm64()) pick("pamir-vpn.apk", "_arm64-v8a.apk") else null) ?: pick("pamir-vpn-universal.apk", "_universal.apk")
        // The build workflow writes "<!-- pamir-min-version: 1.6.1 -->" into the release notes.
        val min = Regex("""pamir-min-version:\s*([\d.]+)""").find(o.optString("body"))?.groupValues?.get(1).orEmpty()
        return if (v.isNotBlank() && url != null) UpdateSource(v, url, min) else null
    }

    /** The site mirror (download/android.json), kept for when GitHub is slow or blocked. */
    private fun updateFromSite(): UpdateSource? {
        val o = JSONObject(httpGet(UPDATE_JSON))
        val v = o.optString("version")
        val abi = if (prefersArm64() && o.has("arm64-v8a")) "arm64-v8a" else "universal"
        val file = o.optJSONObject(abi)?.optString("file") ?: "pamir-vpn-universal.apk"
        return if (v.isNotBlank()) UpdateSource(v, DOWNLOAD_BASE + file, o.optString("min_version")) else null
    }

    /** Asks GitHub and the site in parallel; offers the newest version and every source that has it. */
    private fun checkAppUpdate(manual: Boolean = false) {
        lifecycleScope.launch {
            val found = withContext(Dispatchers.IO) {
                val gh = async { runCatching { updateFromGithub() }.onFailure { Log.w("Pamir", "update github: ${it.message}") }.getOrNull() }
                val site = async { runCatching { updateFromSite() }.onFailure { Log.w("Pamir", "update site: ${it.message}") }.getOrNull() }
                listOfNotNull(gh.await(), site.await())
            }
            if (found.isNotEmpty()) {
                // The highest minimum any source reports; the site mirror can lag behind GitHub by a few minutes.
                val min = found.map { it.minVersion }.filter { it.isNotBlank() }.fold("") { acc, v -> if (acc.isEmpty() || isNewer(v, acc)) v else acc }
                PamirWatch.setMinVersion(min)
                // The update screen covers the app until the user updates; a running VPN keeps working meanwhile.
                updateRequired = PamirWatch.updateRequired()
            }
            val best = found.map { it.version }.fold(appVersion()) { acc, v -> if (isNewer(v, acc)) v else acc }
            if (!isNewer(best, appVersion())) {
                if (manual && updCheck == "checking") updCheck = if (found.isEmpty()) "error" else "latest"
                return@launch
            }
            newVersionUrls = found.filter { it.version == best }.map { it.url }
            newVersion = best
            if (manual && updCheck == "checking") updCheck = "new"
        }
    }

    private fun isNewer(remote: String, local: String): Boolean = PamirWatch.versionNewer(remote, local)

    private fun installUpdate() {
        if (updProgress >= 0) return
        if (android.os.Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            toast("Разрешите установку обновлений и нажмите «Обновить» ещё раз", true)
            runCatching {
                startActivity(Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            }
            return
        }
        updProgress = 0
        lifecycleScope.launch {
            val file = withContext(Dispatchers.IO) {
                newVersionUrls.firstNotNullOfOrNull { url -> downloadApk(url) }
            }
            updProgress = -1
            if (file == null) {
                toast("Не удалось скачать обновление")
                return@launch
            }
            runCatching {
                val uri = androidx.core.content.FileProvider.getUriForFile(this@PamirActivity, "$packageName.cache", file)
                startActivity(
                    Intent(Intent.ACTION_VIEW)
                        .setDataAndType(uri, "application/vnd.android.package-archive")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }.onFailure { toast("Не удалось открыть установщик") }
        }
    }

    /** Downloads one source into the cache; null (and logged) when it fails or arrives incomplete. */
    private suspend fun downloadApk(url: String): java.io.File? = runCatching {
        withContext(Dispatchers.Main) { updProgress = 0 }
        val dir = java.io.File(cacheDir, "update").apply { mkdirs() }
        val f = java.io.File(dir, "pamir-vpn.apk")
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 10000; c.readTimeout = 20000
        val total = c.contentLengthLong
        var done = 0L
        c.inputStream.use { input ->
            f.outputStream().use { out ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    done += n
                    if (total > 0) {
                        val pr = (done * 100 / total).toInt()
                        withContext(Dispatchers.Main) { updProgress = pr }
                    }
                }
            }
        }
        if (total > 0 && done != total) throw java.io.IOException("incomplete download: $done of $total")
        f
    }.onFailure { Log.w("Pamir", "update download failed: ${it.message}") }.getOrNull()

    private fun updateSubscription(silent: Boolean = false) {
        if (updating) return
        updating = true
        lifecycleScope.launch {
            val res = ioTimeout(60_000) { AngConfigManager.updateConfigViaSubAll() }
            updating = false
            if (res != null && res.successCount > 0) {
                MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, System.currentTimeMillis())
            }
            reloadServers()
            if (!silent) {
                if (res != null && res.successCount > 0) toast("Серверы обновлены")
                else toast("Не удалось обновить. Проверьте интернет", action = "Повторить") { updateSubscription() }
            }
        }
    }

    private fun importFromClipboard() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        val text = cm?.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString()?.trim().orEmpty()
        if (!text.startsWith("http")) {
            toast("Скопируйте ссылку подписки в кабинете и нажмите ещё раз", true)
            return
        }
        updating = true
        lifecycleScope.launch {
            val (count, subs) = ioTimeout(45_000) { AngConfigManager.importBatchConfig(text, "", false) } ?: (0 to 0)
            updating = false
            if (count + subs > 0) {
                MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, System.currentTimeMillis())
                reloadServers()
                toast("Подписка добавлена")
            } else toast("Не удалось добавить подписку")
        }
    }

    private fun setRuDirect(on: Boolean) {
        runCatching {
            SettingsManager.resetRoutingRulesetsFromPresets(this, if (on) RoutingType.WHITE_RUSSIA else RoutingType.GLOBAL)
        }
        MmkvManager.encodeSettings(PREF_RU_DIRECT, on)
        if (running) LauncherManager.restartService(this)
    }

    /**
     * Opens [url] in the browser or Telegram. On a TV (and on a phone without an app for the link) it is
     * shown as a QR code for the phone instead; [onClose] runs when that QR sheet is closed.
     */
    private fun openUrl(
        url: String,
        title: String = "Откройте на телефоне",
        text: String = "Отсканируйте код телефоном — ссылка откроется на нём",
        onClose: (() -> Unit)? = null,
    ) {
        if (!tv && runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }.isSuccess) return
        qrLink = QrLink(title, text, url, onClose)
    }

    /**
     * Messages of this screen. Shadows the Context.toast extension: while the screen is visible and no
     * bottom sheet covers it, the message goes to the in-app snackbar (optionally with an action);
     * otherwise a system toast is used, because a sheet window would hide the snackbar.
     */
    private fun toast(message: CharSequence, long: Boolean = false, action: String? = null, onAction: (() -> Unit)? = null) {
        val sheetShown = sheetOpen || renewOpen || reportOpen || cabTopupOpen || emailLoginOpen || newsOpen || cardUnlinkOpen || keyPickerOpen || renameTarget != null || qrLink != null || payWebUrl != null
        if (sheetShown || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            applicationContext.toast(message, long)
            return
        }
        lifecycleScope.launch {
            snackbar.currentSnackbarData?.dismiss()
            val duration = when {
                action != null -> SnackbarDuration.Long
                long -> SnackbarDuration.Long
                else -> SnackbarDuration.Short
            }
            val result = snackbar.showSnackbar(message.toString(), actionLabel = action, duration = duration)
            if (result == SnackbarResult.ActionPerformed) onAction?.invoke()
        }
    }

    private fun setTheme(mode: PamirThemeMode) {
        themeMode = mode
        MmkvManager.encodeSettings(PREF_THEME, mode.key)
    }

    private fun toggleFavorite(name: String) {
        favorites = if (name in favorites) favorites - name else favorites + name
        MmkvManager.encodeSettings(PREF_FAVORITES, favorites.toMutableSet())
    }

    // ---------- UI ----------

    private val navTabs = listOf(Tab.HOME, Tab.CABINET, Tab.SETTINGS)
    private val navEntries = listOf(
        NavEntry("VPN", PamirIcons.Shield),
        NavEntry("Кабинет", PamirIcons.Person),
        NavEntry("Настройки", PamirIcons.Settings),
    )

    @Composable
    private fun Root() {
        val c = Pamir.colors
        val dark = c.isDark
        // System bar icons follow the app theme, not the phone theme.
        LaunchedEffect(dark) {
            enableEdgeToEdge(
                statusBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT) { dark },
                navigationBarStyle = SystemBarStyle.auto(NAV_SCRIM_LIGHT, NAV_SCRIM_DARK) { dark },
            )
        }
        BackHandler(enabled = tab != Tab.HOME) { tab = if (tab == Tab.APPS) Tab.SETTINGS else Tab.HOME }
        LaunchedEffect(tab) { if (tab != Tab.APPS) applyAppsIfChanged() }
        LaunchedEffect(tab, loggedIn) { if (tab == Tab.CABINET && loggedIn) loadCabinet(silent = true) }
        val indication = if (tv) remember(c.accent, c.text) { TvFocusIndication(c.accent, c.text) } else LocalIndication.current
        // On a TV the phone layout stays a centered column instead of stretching across the screen.
        val tvColumn = if (tv) Modifier.widthIn(max = 600.dp) else Modifier
        CompositionLocalProvider(LocalIndication provides indication, LocalTv provides tv) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(c.bg)
            ) {
                // The start screen (sign-in) only before login; signed in, the tabs stay even without a subscription.
                // TV has no tabs, so it keeps the start screen until a key is on it.
                val startScreen = servers.isEmpty() && (!loggedIn || tv)
                val onHome = servers.isEmpty() || tab == Tab.HOME
                val glow by animateFloatAsState(
                    when {
                        !onHome -> 0.3f
                        running -> 1f
                        else -> 0.55f
                    },
                    tween(700), label = "bgGlow"
                )
                Box(
                    Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .height(400.dp)
                        .graphicsLayer { alpha = glow }
                        .background(Brush.radialGradient(listOf(c.accent.copy(alpha = if (dark) 0.15f else 0.22f), Color.Transparent)))
                )
                if (startScreen) {
                    Box(Modifier.align(Alignment.TopCenter).then(if (tv) Modifier.widthIn(max = 960.dp) else Modifier)) { Onboarding() }
                } else {
                    Column(
                        Modifier
                            .align(Alignment.TopCenter)
                            .then(tvColumn)
                            .fillMaxSize()
                            .statusBarsPadding()
                            .navigationBarsPadding()
                    ) {
                        Box(Modifier.weight(1f)) {
                            AnimatedContent(
                                targetState = tab,
                                transitionSpec = {
                                    (fadeIn(tween(220)) + slideInVertically(tween(260)) { it / 30 }) togetherWith fadeOut(tween(140))
                                },
                                label = "tab"
                            ) { t ->
                                when (t) {
                                    Tab.HOME -> if (servers.isEmpty()) NoKeyHome() else Home(onPick = { sheetOpen = true })
                                    Tab.SETTINGS -> Settings()
                                    Tab.APPS -> AppsScreen()
                                    Tab.CABINET -> CabinetScreen()
                                }
                            }
                        }
                        // TV has one screen (power, server, subscription, autostart, support) — no tabs.
                        if (!tv) {
                            val navTab = if (tab == Tab.APPS) Tab.SETTINGS else tab
                            BottomNav(navEntries, selected = navTabs.indexOf(navTab), onSelect = { tab = navTabs[it] })
                        }
                    }
                }
                PamirSnackbarHost(
                    snackbar,
                    Modifier
                        .align(Alignment.BottomCenter)
                        .navigationBarsPadding()
                        .padding(bottom = if (startScreen) 0.dp else 84.dp)
                )
                if (sheetOpen) ServerSheet(onDismiss = { sheetOpen = false })
                if (renewOpen) RenewSheet(onDismiss = { renewOpen = false })
                if (reportOpen) ReportSheet(onDismiss = { reportOpen = false })
                if (supportOpen) SupportSheet(onDismiss = { supportOpen = false })
                updCheck?.let { UpdateSheet(it, onDismiss = { updCheck = null }) }
                if (cabTopupOpen) TopupSheet(onDismiss = { cabTopupOpen = false })
                if (emailLoginOpen) EmailLoginSheet(onDismiss = { emailLoginOpen = false })
                if (newsOpen) NewsSheet(onDismiss = { newsOpen = false })
                if (cardUnlinkOpen) CardUnlinkSheet(onDismiss = { cardUnlinkOpen = false })
                if (keyPickerOpen) KeyPickerSheet(onDismiss = { keyPickerOpen = false })
                renameTarget?.let { RenameKeySheet(it, onDismiss = { renameTarget = null }) }
                qrLink?.let { q -> QrSheet(q, onDismiss = { qrLink = null; q.onClose?.invoke() }) }
                payWebUrl?.let { u ->
                    PayWebDialog(
                        u, onReturn = { onPaymentPageClosed() }, onClose = { onPaymentPageClosed() },
                        onBrowser = { payWebUrl = null; openUrl(u) }
                    )
                }
                if (updateRequired) RequiredUpdate()
            }
        }
    }

    /** Covers the whole app while a required update is not installed; only updating (or support) is possible. */
    @Composable
    private fun RequiredUpdate() {
        val c = Pamir.colors
        BackHandler { finish() }
        LaunchedEffect(Unit) { if (newVersion == null) checkAppUpdate() }
        Box(
            Modifier
                .fillMaxSize()
                .background(c.bg)
                .pointerInput(Unit) { detectTapGestures { } }
                .statusBarsPadding()
                .navigationBarsPadding(),
            contentAlignment = Alignment.Center
        ) {
            Column(
                Modifier
                    .then(if (tv) Modifier.widthIn(max = 560.dp) else Modifier.fillMaxWidth())
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = Gap.xl, vertical = Gap.xl),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                LogoHero()
                Spacer(Modifier.height(Gap.l))
                Text("Важное обновление", style = PamirType.title, color = c.text, textAlign = TextAlign.Center)
                Spacer(Modifier.height(Gap.s))
                Text(
                    "Вышла новая версия Pamir VPN — без неё приложение дальше не откроется. " +
                        "Обновление займёт минуту, подписка и настройки сохранятся.",
                    style = PamirType.body, color = c.textDim, textAlign = TextAlign.Center
                )
                Spacer(Modifier.height(Gap.xl))
                val v = newVersion
                PrimaryButton(
                    when {
                        updProgress >= 0 -> "Загрузка $updProgress%"
                        v != null -> "Обновить до $v"
                        else -> "Проверить обновление"
                    },
                    icon = PamirIcons.Download,
                    loading = updProgress == 0
                ) { if (v != null) installUpdate() else { toast("Проверяем обновления…"); checkAppUpdate() } }
                Spacer(Modifier.height(Gap.s))
                TextAction("Скачать с сайта", color = c.accentText) {
                    openUrl(
                        DOWNLOAD_BASE + if (prefersArm64()) "pamir-vpn.apk" else "pamir-vpn-universal.apk",
                        "Скачать Pamir VPN", "Откройте ссылку на телефоне и установите файл"
                    )
                }
                TextAction("Поддержка", icon = PamirIcons.Chat) { openUrl(BOT_URL, "Поддержка", "Отсканируйте код телефоном — ответим в Telegram") }
            }
        }
    }

    // ---------- onboarding ----------

    @Composable
    private fun Onboarding() {
        LaunchedEffect(Unit) {
            while (true) { delay(1500); reloadServers() }
        }
        if (tv) {
            // A TV screen is wide and low: greeting on the left, steps and sign-in on the right.
            Row(
                Modifier
                    .fillMaxSize()
                    .padding(horizontal = Gap.xl),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(48.dp)
            ) {
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) { OnboardingIntro() }
                Column(
                    Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(vertical = Gap.xl),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) { OnboardingActions() }
            }
            return
        }
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.xl),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(Modifier.height(40.dp))
            OnboardingIntro()
            Spacer(Modifier.height(Gap.xl))
            OnboardingActions()
        }
    }

    /** VPN tab when signed in but no key is on this phone yet: trial, tariffs, or a key to pick. */
    @Composable
    private fun NoKeyHome() {
        val c = Pamir.colors
        LaunchedEffect(Unit) {
            loadTrialOffer()
            while (true) { delay(1500); reloadServers() }
        }
        val active = activeKeys(renewKeys)
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.xl),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(Modifier.height(40.dp))
            LogoHero()
            Spacer(Modifier.height(Gap.l))
            Text(
                if (active.isEmpty()) "Подписки пока нет" else "Ключ ещё не на телефоне",
                style = PamirType.title, color = c.text, textAlign = TextAlign.Center,
                modifier = Modifier.semantics { heading() }
            )
            Spacer(Modifier.height(Gap.s))
            Text(
                if (active.isEmpty()) "Выберите тариф — серверы появятся здесь сами, и подключение будет в одно касание."
                else "Подключите ключ — серверы загрузятся сами.",
                style = PamirType.bodyRegular, color = c.textDim, textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(Gap.xl))
            when {
                active.size > 1 -> PrimaryButton("Выбрать ключ для этого телефона", icon = PamirIcons.Key, loading = updating) { openKeyPicker() }
                active.size == 1 -> PrimaryButton("Подключить ключ", icon = PamirIcons.Key, loading = updating) { lifecycleScope.launch { applyDeviceKey(active[0]) } }
                else -> {
                    if (trialShown) {
                        TrialCard()
                        Spacer(Modifier.height(Gap.m))
                    }
                    PrimaryButton("Выбрать тариф", icon = PamirIcons.Star) { openRenew() }
                }
            }
            Spacer(Modifier.height(Gap.s))
            TextAction("Вставить ссылку подписки", icon = PamirIcons.Link) { importFromClipboard() }
            Spacer(Modifier.height(Gap.l))
        }
    }

    @Composable
    private fun OnboardingIntro() {
        val c = Pamir.colors
        LogoHero()
        Spacer(Modifier.height(Gap.l))
        Text(
            "Добро пожаловать\nв Pamir VPN", style = PamirType.hero, color = c.text, textAlign = TextAlign.Center,
            modifier = Modifier.semantics { heading() }
        )
        Spacer(Modifier.height(Gap.s))
        Text("Три шага — и интернет под защитой", style = PamirType.bodyRegular, color = c.textDim, textAlign = TextAlign.Center)
    }

    @Composable
    private fun OnboardingActions() {
        val c = Pamir.colors
        OnboardingStep(1, "Войдите через Telegram", "или по почте и паролю от кабинета")
        OnboardingStep(2, "Подписка подключится сама", "Серверы загрузятся автоматически")
        OnboardingStep(3, "Нажмите большую кнопку", if (tv) "Подключение одним нажатием на пульте" else "Подключение в одно касание")
        Spacer(Modifier.height(Gap.xl))
        if (loggedIn) {
            // Signed in but no key here yet (TV keeps this screen; phones show NoKeyHome in the VPN tab).
            LaunchedEffect(Unit) { loadTrialOffer() }
            val active = activeKeys(renewKeys)
            when {
                active.size > 1 -> PrimaryButton(if (tv) "Выбрать ключ для телевизора" else "Выбрать ключ для этого телефона", icon = PamirIcons.Key, loading = updating) { openKeyPicker() }
                active.size == 1 -> PrimaryButton("Подключить ключ", icon = PamirIcons.Key, loading = updating) { lifecycleScope.launch { applyDeviceKey(active[0]) } }
                else -> {
                    if (trialShown) { TrialCard(); Spacer(Modifier.height(Gap.m)) }
                    PrimaryButton("Выбрать тариф", icon = PamirIcons.Star) { openRenew() }
                }
            }
            Spacer(Modifier.height(Gap.m))
            TextAction("Выйти из аккаунта", icon = PamirIcons.Logout) { signOut() }
            Spacer(Modifier.height(Gap.l))
            return
        }
        if (loginBusy) {
            Text("Подтвердите вход в Telegram и вернитесь сюда", style = PamirType.support, color = c.textDim, textAlign = TextAlign.Center)
            Spacer(Modifier.height(Gap.m))
            SecondaryButton("Отменить") { cancelLogin() }
        } else {
            val focus = remember { FocusRequester() }
            LaunchedEffect(Unit) { if (tv) runCatching { focus.requestFocus() } }
            PrimaryButton(
                "Войти через Telegram", Modifier.focusRequester(focus), subtitle = "Подписка подключится сама",
                icon = PamirIcons.Telegram, loading = updating
            ) { loginTelegram() }
        }
        Spacer(Modifier.height(Gap.m))
        SecondaryButton("Войти по почте и паролю", icon = PamirIcons.Mail) { emailRegister = false; emailLoginOpen = true }
        Spacer(Modifier.height(Gap.xs))
        TextAction("Нет аккаунта? Зарегистрироваться", color = c.accentText) { emailRegister = true; emailLoginOpen = true }
        if (!tv) TextAction("Вставить ссылку подписки", icon = PamirIcons.Link) { importFromClipboard() }
        Spacer(Modifier.height(Gap.l))
    }

    @Composable
    private fun LogoHero() {
        val c = Pamir.colors
        Box(Modifier.size(136.dp), contentAlignment = Alignment.Center) {
            Canvas(Modifier.fillMaxSize()) {
                val r = size.minDimension / 2
                drawCircle(Brush.radialGradient(listOf(c.accent.copy(alpha = 0.28f), Color.Transparent), center, r), r)
                drawCircle(c.accent.copy(alpha = 0.18f), r * 0.68f, style = Stroke(1.5.dp.toPx()))
                drawCircle(c.surface, r * 0.58f)
                drawCircle(c.accent.copy(alpha = 0.35f), r * 0.58f, style = Stroke(1.5.dp.toPx()))
            }
            Image(painterResource(R.drawable.pamir_logo), contentDescription = null, modifier = Modifier.size(64.dp))
        }
    }

    @Composable
    private fun OnboardingStep(n: Int, title: String, text: String) {
        val c = Pamir.colors
        Row(
            Modifier
                .padding(vertical = Gap.xs)
                .fillMaxWidth()
                .clip(Radius.m)
                .background(c.surface)
                .border(1.dp, c.line, Radius.m)
                .padding(horizontal = 14.dp, vertical = Gap.m),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier
                    .size(32.dp)
                    .clip(CircleShape)
                    .background(c.accentSoft),
                contentAlignment = Alignment.Center
            ) { Text("$n", style = PamirType.label, color = c.accentText) }
            Spacer(Modifier.width(14.dp))
            Column {
                Text(title, style = PamirType.body, color = c.text)
                Text(text, style = PamirType.support, color = c.textDim)
            }
        }
    }

    // ---------- home ----------

    @Composable
    private fun Home(onPick: () -> Unit) {
        val c = Pamir.colors
        val current = servers.firstOrNull { it.guid == selected }
        val stubMode = servers.all { it.isStub }
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.l),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            HomeHeader()
            HomeNotice()
            if (stubMode) {
                Spacer(Modifier.height(Gap.l))
                StubCard()
                return@Column
            }
            val power = when {
                connecting -> PowerState.CONNECTING
                running -> PowerState.ON
                else -> PowerState.OFF
            }
            val stateText = when (power) {
                PowerState.CONNECTING -> "Подключение…"
                PowerState.ON -> "Защищено"
                PowerState.OFF -> "Не подключено"
            }
            val powerFocus = remember { FocusRequester() }
            LaunchedEffect(Unit) { if (tv) runCatching { powerFocus.requestFocus() } }
            PowerButton(
                state = power,
                label = if (running) "Отключить VPN" else "Подключить VPN",
                stateLabel = stateText,
                onClick = { toggle() },
                modifier = Modifier.focusRequester(powerFocus)
            )
            AnimatedContent(targetState = stateText, transitionSpec = { fadeIn(tween(250)) togetherWith fadeOut(tween(150)) }, label = "state") { s ->
                Text(
                    s, style = PamirType.headline, color = if (s == "Защищено") c.accentText else c.text,
                    modifier = Modifier
                        .clip(Radius.s)
                        .clickable(role = Role.Button) { toggle() }
                        .padding(horizontal = Gap.m, vertical = Gap.xs)
                )
            }
            if (running) {
                Timer()
            } else {
                Text(
                    if (connecting) "Устанавливаем защищённое соединение" else "Нажмите, чтобы защитить соединение",
                    style = PamirType.support, color = c.textDim
                )
            }
            Spacer(Modifier.height(Gap.xl))
            if (current != null) ServerCard(current, onPick)
            AnimatedVisibility(visible = running, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
                SpeedCard()
            }
            if (!running && !tv) {
                if (whitelist && current?.isLte != true) {
                    Spacer(Modifier.height(Gap.m))
                    WhitelistCard()
                }
            }
            if (tv) TvFooter()
            Spacer(Modifier.height(Gap.l))
        }
    }

    /** TV instead of the Settings tab: autostart with the TV and support (as a QR code). */
    @Composable
    private fun TvFooter() {
        var boot by remember { mutableStateOf(MmkvManager.decodeStartOnBoot()) }
        Spacer(Modifier.height(Gap.m))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Gap.s)) {
            SecondaryButton(if (boot) "Автозапуск: вкл" else "Автозапуск: выкл", Modifier.weight(1f), icon = PamirIcons.Power) {
                boot = !boot
                MmkvManager.encodeStartOnBoot(boot)
                toast(if (boot) "VPN включится сам при включении телевизора" else "Автозапуск выключен")
            }
            SecondaryButton("Поддержка", Modifier.weight(1f), icon = PamirIcons.Chat) {
                openUrl(BOT_URL, "Поддержка", "Отсканируйте код телефоном — ответим в Telegram")
            }
        }
    }

    /** On TV the VPN should come back after the TV is unplugged: autostart is on by default (once, user can turn it off). */
    private fun enableTvBootOnce() {
        if (MmkvManager.decodeSettingsBool(PREF_TV_BOOT_INIT, false)) return
        MmkvManager.encodeSettings(PREF_TV_BOOT_INIT, true)
        MmkvManager.encodeStartOnBoot(true)
    }

    @Composable
    private fun HomeHeader() {
        val c = Pamir.colors
        Row(
            Modifier
                .fillMaxWidth()
                .padding(vertical = Gap.s),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Image(painterResource(R.drawable.pamir_logo), contentDescription = null, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(Gap.s))
            Text("Pamir VPN", style = PamirType.subtitle, color = c.text, modifier = Modifier.weight(1f))
            val d = daysLeft
            val tone = if (d != null && d <= 3) Tone.WARN else Tone.ACCENT
            val left = when {
                d == null -> "Подписка"
                d <= 0 -> "Сегодня"
                else -> "$d ${plural(d, "день", "дня", "дней")}"
            }
            Row(
                Modifier
                    .heightIn(min = 40.dp)
                    .clip(CircleShape)
                    .background(tone.soft())
                    .clickable(role = Role.Button) { openRenew() }
                    .padding(horizontal = Gap.m),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(tone.color()))
                Spacer(Modifier.width(Gap.s))
                Text("$left · Продлить", style = PamirType.label, color = tone.color(), maxLines = 1)
            }
        }
    }

    /** At most one notice on the home screen, the most important first. */
    @Composable
    private fun HomeNotice() {
        val d = daysLeft
        when {
            newVersion != null -> Banner(
                PamirIcons.Download, "Доступна версия $newVersion",
                if (updProgress >= 0) "Загрузка $updProgress%" else "Обновить", Tone.ACCENT, { installUpdate() },
                Modifier.padding(top = Gap.xs)
            )
            lastChance != null && activePromo == null -> Banner(
                PamirIcons.Star, "Скидка ${lastChance?.optInt("discount_percent")}% на продление — только сейчас",
                "Забрать", Tone.WARN, { applyLastChance() }, Modifier.padding(top = Gap.xs)
            )
            d != null && d <= 3 -> Banner(
                PamirIcons.Clock,
                when {
                    d <= 0 -> "Подписка заканчивается сегодня"
                    d == 1 -> "Подписка закончится завтра"
                    else -> "Подписка закончится через $d ${plural(d, "день", "дня", "дней")}"
                },
                "Продлить", Tone.WARN, { openRenew() }, Modifier.padding(top = Gap.xs)
            )
            else -> PamirNews.unseen(news)?.let { n ->
                Banner(
                    PamirIcons.Info, n.optString("text").trim().lineSequence().first(),
                    "Читать", Tone.ACCENT, { openNews() }, Modifier.padding(top = Gap.xs)
                )
            }
        }
    }

    /** Cabinet: the card for auto-renewal, or the offer to add one. */
    @Composable
    private fun AutopayCard() {
        val c = Pamir.colors
        val info = cardInfo ?: return
        if (info.optBoolean("has_card")) {
            PamirCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBadge(PamirIcons.Wallet, size = 44.dp, iconSize = 24.dp)
                    Spacer(Modifier.width(Gap.m))
                    Column(Modifier.weight(1f)) {
                        val type = info.optString("card_type").takeIf { it.isNotBlank() && it != "null" } ?: "Карта"
                        val last4 = info.optString("card_last4").takeIf { it.isNotBlank() && it != "null" }
                        Text(if (last4 != null) "$type •••• $last4" else type, style = PamirType.body, color = c.text)
                        Text("Подписка продлевается сама — переключатель у каждого ключа", style = PamirType.support, color = c.textDim)
                    }
                }
                Spacer(Modifier.height(Gap.s))
                TextAction("Отвязать карту", color = c.danger) { cardUnlinkOpen = true }
            }
        } else {
            CardOffer(onLater = null, onNever = null)
        }
    }

    /**
     * Offer to add a card for auto-renewal: after a payment and in the cabinet. The main action is big;
     * "Не сейчас" and "Больше не показывать" are deliberately quiet (only after a payment).
     */
    @Composable
    private fun CardOffer(onLater: (() -> Unit)?, onNever: (() -> Unit)?) {
        val c = Pamir.colors
        PamirCard(tone = Tone.ACCENT) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBadge(PamirIcons.Wallet, size = 44.dp, iconSize = 24.dp)
                Spacer(Modifier.width(Gap.m))
                Text("Продлевать вручную больше не нужно", style = PamirType.subtitle, color = c.text, modifier = Modifier.weight(1f))
            }
            Spacer(Modifier.height(Gap.s))
            Text(
                "Привяжите карту — подписка будет продлеваться сама в день окончания. VPN не отключится в самый неподходящий момент.",
                style = PamirType.bodyRegular, color = c.text
            )
            Spacer(Modifier.height(Gap.xs))
            Text("Отключить можно в любой момент. Для проверки спишем 1 ₽ и сразу вернём.", style = PamirType.support, color = c.textDim)
            Spacer(Modifier.height(Gap.l))
            PrimaryButton("Привязать карту", icon = PamirIcons.Wallet, loading = cardBusy) { bindCard() }
            if (onLater != null) {
                TextAction("Не сейчас", Modifier.align(Alignment.CenterHorizontally)) { onLater() }
            }
            if (onNever != null) {
                Text(
                    "Больше не показывать", style = PamirType.caption, color = c.textDim.copy(alpha = 0.7f),
                    modifier = Modifier
                        .align(Alignment.CenterHorizontally)
                        .clip(Radius.s)
                        .clickable(role = Role.Button) { onNever() }
                        .padding(horizontal = Gap.s, vertical = Gap.xs)
                )
            }
        }
    }

    @Composable
    private fun CardUnlinkSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        PamirSheet(onDismiss = onDismiss, title = "Отвязать карту?", subtitle = "Автопродление выключится — продлевать подписку придётся вручную") {
            Spacer(Modifier.height(Gap.s))
            SecondaryButton("Оставить карту") { onDismiss() }
            Spacer(Modifier.height(Gap.xs))
            TextAction("Отвязать", Modifier.align(Alignment.CenterHorizontally), color = c.danger) { unlinkCard() }
        }
    }

    @Composable
    private fun NewsSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        PamirSheet(onDismiss = onDismiss, title = "Новости") {
            if (news.isEmpty()) Text("Пока новостей нет", style = PamirType.support, color = c.textDim)
            news.take(10).forEach { n ->
                PamirCard(Modifier.padding(vertical = Gap.xs), contentPadding = 14.dp) {
                    Text(n.optString("text").trim(), style = PamirType.bodyRegular, color = c.text)
                    val d = PamirNews.date(n)
                    if (d.isNotEmpty()) {
                        Spacer(Modifier.height(Gap.xs))
                        Text(d, style = PamirType.support, color = c.textDim)
                    }
                }
            }
        }
    }

    @Composable
    private fun StubCard() {
        NoteCard(
            PamirIcons.Warning, "Нет доступа к серверам",
            servers.joinToString("\n") { "${it.flag} ${it.name}".trim() }, Tone.DANGER
        ) {
            PrimaryButton("Продлить подписку", icon = PamirIcons.Star) { openRenew() }
            Spacer(Modifier.height(Gap.s))
            SecondaryButton(if (updating) "Обновляем…" else "Проверить снова", icon = PamirIcons.Refresh, loading = updating) { updateSubscription() }
            if (loggedIn && !tv) TextAction("Устройства и ключи — в кабинете", Modifier.align(Alignment.CenterHorizontally)) { tab = Tab.CABINET }
            TextAction("Поддержка", Modifier.align(Alignment.CenterHorizontally), icon = PamirIcons.Chat) {
                openUrl(BOT_URL, "Поддержка", "Отсканируйте код телефоном — ответим в Telegram")
            }
        }
    }

    @Composable
    private fun Timer() {
        var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
        LaunchedEffect(running) {
            while (running) { now = System.currentTimeMillis(); delay(1000) }
        }
        val sec = if (connectedAt > 0) ((now - connectedAt) / 1000).coerceAtLeast(0) else 0
        val t = String.format("%02d:%02d:%02d", sec / 3600, (sec % 3600) / 60, sec % 60)
        Text(
            "В защите $t", style = PamirType.support.copy(fontFeatureSettings = "tnum"), color = Pamir.colors.textDim,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }.clearAndSetSemantics { contentDescription = "Подключено $t" }
        )
    }

    @Composable
    private fun FlagBadge(flag: String, size: Dp = 44.dp) {
        Box(
            Modifier
                .size(size)
                .clip(CircleShape)
                .background(Pamir.colors.surfaceHigh),
            contentAlignment = Alignment.Center
        ) { Text(flag, fontSize = (size.value * 0.5f).sp) }
    }

    @Composable
    private fun ServerCard(s: PServer, onPick: () -> Unit) {
        val c = Pamir.colors
        val auto = MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false)
        val p = pings[s.guid]
        PamirCard(onClick = onPick, contentPadding = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                FlagBadge(s.flag)
                Spacer(Modifier.width(Gap.m))
                Column(Modifier.weight(1f)) {
                    Text(s.name, style = PamirType.body.copy(fontWeight = FontWeight.Bold), color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val sub = when {
                        locTick.let { PamirLocations.isDown(s.rawRemarks) } -> "Перебои — смените сервер"
                        auto -> "Выбран автоматически"
                        s.isLte -> "Для мобильного интернета"
                        p != null && p > 0 -> "Отклик $p мс"
                        else -> "Нажмите, чтобы сменить"
                    }
                    Text(sub, style = PamirType.support, color = c.textDim, maxLines = 1)
                }
                if (!s.isLte) {
                    PingBars(pingQuality(p))
                    Spacer(Modifier.width(Gap.m))
                }
                Chip("Сменить", Tone.ACCENT)
            }
        }
    }

    @Composable
    private fun WhitelistCard() {
        NoteCard(
            PamirIcons.Signal, "Похоже, включены «белые списки»",
            "Обычные серверы сейчас недоступны. LTE Обход работает и в этом режиме.", Tone.WARN
        ) {
            PrimaryButton("Подключить LTE Обход", icon = PamirIcons.Bolt) {
                lteServer()?.let { useLte(it); if (!running) toggle() else LauncherManager.restartService(this@PamirActivity) }
            }
        }
    }

    @Composable
    private fun SpeedCard() {
        val c = Pamir.colors
        LaunchedEffect(running) { if (running) speedLoop() }
        PamirCard(Modifier.padding(top = Gap.m), contentPadding = 0.dp) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = Gap.l, end = Gap.l, top = Gap.l),
                verticalAlignment = Alignment.CenterVertically
            ) {
                SpeedValue(PamirIcons.ArrowDown, "Загрузка", rxSpeed, c.accentText, Modifier.weight(1f))
                SpeedValue(PamirIcons.ArrowUp, "Отдача", txSpeed, c.info, Modifier.weight(1f))
            }
            Sparkline(
                speedHist, if (c.isDark) c.accent else c.accentDeep,
                Modifier
                    .fillMaxWidth()
                    .height(52.dp)
                    .padding(top = Gap.s)
            )
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(c.surfaceHigh.copy(alpha = if (c.isDark) 0.55f else 0.7f))
                    .padding(horizontal = Gap.l, vertical = Gap.m)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(PamirIcons.Globe, contentDescription = null, modifier = Modifier.size(16.dp), tint = c.textDim)
                    Spacer(Modifier.width(Gap.s))
                    Text(
                        if (ipInfo.isNotEmpty()) "IP $ipInfo" else "Определяем IP…",
                        style = PamirType.support, color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "За сессию ↓ ${fmtBytes(rxTotal)}  ↑ ${fmtBytes(txTotal)}",
                        style = PamirType.caption, color = c.textDim, maxLines = 1, modifier = Modifier.weight(1f)
                    )
                    Text(
                        if (MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) "РФ напрямую" else "Всё через VPN",
                        style = PamirType.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textDim, maxLines = 1
                    )
                }
            }
        }
    }

    @Composable
    private fun SpeedValue(icon: ImageVector, label: String, bps: Long, color: Color, modifier: Modifier) {
        val c = Pamir.colors
        Row(modifier, verticalAlignment = Alignment.CenterVertically) {
            IconBadge(icon, tint = color, background = color.copy(alpha = 0.14f), size = 36.dp, iconSize = 18.dp, shape = CircleShape)
            Spacer(Modifier.width(Gap.s + 2.dp))
            Column {
                Text(
                    fmtBytes(bps) + "/с", style = PamirType.number.copy(fontSize = 19.sp, fontFeatureSettings = "tnum"),
                    color = c.text, maxLines = 1
                )
                Text(label, style = PamirType.caption, color = c.textDim)
            }
        }
    }

    // ---------- server picker ----------

    @Composable
    private fun ServerSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        LaunchedEffect(Unit) { if (realPinged.isEmpty()) runPing() }
        LaunchedEffect(Unit) { loadLocations(force = true) }
        val auto = MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false)
        PamirSheet(
            onDismiss = onDismiss,
            title = "Выбор сервера",
            subtitle = if (pingBusy) "Проверяем скорость серверов…" else "Чем больше делений, тем быстрее отклик",
            headerAction = {
                if (pingBusy) {
                    Box(Modifier.size(48.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = c.accentText, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                    }
                } else {
                    IconAction(PamirIcons.Refresh, "Проверить серверы", { lifecycleScope.launch { runPing() } }, tint = c.accentText)
                }
            }
        ) {
            SheetRow(
                selected = auto,
                leading = { IconBadge(PamirIcons.Bolt, size = 40.dp) },
                title = "Лучший автоматически",
                detail = "Подключим самый быстрый сервер",
                onClick = { pickBest(); onDismiss() }
            )
            // Reachable servers by response time; unknown and silent ones keep subscription order at the end.
            locTick // recompose when the location status is refreshed
            val normal = servers.filter { !it.isLte && !it.isStub }.sortedWith(compareBy<PServer> { PamirLocations.isDown(it.rawRemarks) }.thenBy { s ->
                val p = pings[s.guid]
                when {
                    p == null -> Int.MAX_VALUE - 1
                    p <= 0 -> Int.MAX_VALUE
                    else -> p
                }
            })
            val favs = normal.filter { it.name in favorites }
            val rest = normal.filter { it.name !in favorites }
            val lte = servers.filter { it.isLte && !it.isStub }
            if (favs.isNotEmpty()) {
                SectionHeader("Избранное")
                favs.forEach { s -> ServerItem(s, s.guid == selected && !auto, onDismiss) }
            }
            if (rest.isNotEmpty()) {
                SectionHeader(if (favs.isEmpty()) "Серверы" else "Остальные")
                rest.forEach { s -> ServerItem(s, s.guid == selected && !auto, onDismiss) }
            }
            if (lte.isNotEmpty()) {
                SectionHeader("Для мобильного интернета с ограничениями")
                lte.forEach { s -> ServerItem(s, s.guid == selected, onDismiss) }
            }
        }
    }

    @Composable
    private fun ServerItem(s: PServer, sel: Boolean, onDismiss: () -> Unit) {
        val c = Pamir.colors
        val fav = s.name in favorites
        val p = pings[s.guid]
        val q = pingQuality(p)
        val down = locTick.let { PamirLocations.isDown(s.rawRemarks) }
        SheetRow(
            selected = sel,
            leading = { FlagBadge(s.flag, 40.dp) },
            title = s.name,
            detail = when {
                down -> "Перебои на сервере"
                s.isLte -> "Для «белых списков»"
                else -> pingText(s).ifEmpty { "Нажмите, чтобы подключить" }
            },
            detailColor = when {
                down -> c.danger
                s.isLte || p == null -> c.textDim
                else -> q.color()
            },
            onClick = { selectServer(s.guid); onDismiss() }
        ) {
            if (!s.isLte) PingBars(q)
            IconAction(
                if (fav) PamirIcons.Star else PamirIcons.StarOutline,
                if (fav) "Убрать ${s.name} из избранного" else "Добавить ${s.name} в избранное",
                { toggleFavorite(s.name) },
                tint = if (fav) c.warn else c.textDim
            )
        }
    }

    private fun pingText(s: PServer): String {
        val p = pings[s.guid] ?: return if (pingBusy) "Проверяем…" else ""
        return if (p > 0) "$p мс" else "нет связи"
    }

    @Composable
    private fun SheetRow(
        selected: Boolean,
        leading: @Composable () -> Unit,
        title: String,
        detail: String?,
        onClick: () -> Unit,
        detailColor: Color = Pamir.colors.textDim,
        trailing: @Composable RowScope.() -> Unit = {},
    ) {
        val c = Pamir.colors
        val border by animateColorAsState(if (selected) c.accentText.copy(alpha = 0.7f) else c.line, tween(200), label = "rowBorder")
        Row(
            Modifier
                .padding(vertical = Gap.xs)
                .fillMaxWidth()
                .heightIn(min = 64.dp)
                .clip(Radius.m)
                .background(c.surface)
                .background(if (selected) c.accentSoft else Color.Transparent)
                .border(1.dp, border, Radius.m)
                .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
                .padding(start = Gap.m, end = Gap.m, top = Gap.s, bottom = Gap.s),
            verticalAlignment = Alignment.CenterVertically
        ) {
            leading()
            Spacer(Modifier.width(Gap.m))
            Column(Modifier.weight(1f)) {
                Text(title, style = PamirType.body, color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (!detail.isNullOrEmpty()) Text(detail, style = PamirType.support, color = detailColor, maxLines = 1)
            }
            trailing()
            Spacer(Modifier.width(Gap.xs))
            Box(
                Modifier
                    .size(22.dp)
                    .clip(CircleShape)
                    .border(2.dp, if (selected) c.accentText else c.track, CircleShape)
                    .padding(5.dp)
                    .clip(CircleShape)
                    .background(if (selected) c.accentText else Color.Transparent)
            )
        }
    }

    // ---------- renewal ----------

    @Composable
    private fun RenewSheet(onDismiss: () -> Unit) {
        PamirSheet(
            onDismiss = onDismiss,
            title = if (renewKeys.isEmpty() && loggedIn && !renewLoading) "Оформить подписку" else "Продление подписки"
        ) {
            when {
                payState == "paid" -> {
                    val offer = !tv && cardInfo != null && !hasCard() && !cardPromptSkipped && !PamirOffers.cardPromptNever
                    NoteCard(
                        PamirIcons.Check, "Оплата прошла",
                        if (payBuy) "Подписка оформлена и уже подключается." else "Новый срок применён — VPN работает без перерыва.", Tone.ACCENT
                    ) {
                        if (!offer) PrimaryButton("Отлично") { payState = null; onDismiss() }
                    }
                    if (offer) {
                        Spacer(Modifier.height(Gap.m))
                        CardOffer(
                            onLater = { cardPromptSkipped = true; payState = null; onDismiss() },
                            onNever = { PamirOffers.cardPromptNever = true; payState = null; onDismiss() }
                        )
                    }
                }
                payState == "waiting" -> NoteCard(
                    PamirIcons.Clock, "Проверяем оплату",
                    "Как только платёж пройдёт, срок обновится сам — обычно это меньше минуты.", Tone.WARN
                ) {
                    SecondaryButton("Открыть оплату ещё раз") { openPayment(payUrl, "Оплата", "Отсканируйте код телефоном и оплатите — подписка продлится сама") }
                    TextAction("Отменить", Modifier.align(Alignment.CenterHorizontally)) { payState = null; payJob?.cancel() }
                }
                payState == "failed" -> NoteCard(
                    PamirIcons.Warning, "Оплата не прошла",
                    "Деньги не списаны. Попробуйте ещё раз или выберите другой способ.", Tone.DANGER
                ) {
                    SecondaryButton("Выбрать тариф") { payState = null }
                }
                !loggedIn -> NoteCard(
                    PamirIcons.Telegram, "Войдите через Telegram",
                    "Так вы сможете продлевать подписку прямо здесь — в пару касаний, через СБП, карту или с баланса.", Tone.ACCENT
                ) {
                    LoginButtons()
                    TextAction("Продлить в личном кабинете", Modifier.align(Alignment.CenterHorizontally)) { openUrl(CABINET_URL) }
                }
                renewLoading -> {
                    SkeletonCard("Загружаем тарифы")
                    Spacer(Modifier.height(Gap.m))
                    SkeletonCard("Загружаем тарифы")
                }
                else -> RenewContent()
            }
        }
    }

    /** Telegram login (or its progress) plus the e-mail alternative. */
    @Composable
    private fun LoginButtons() {
        if (loginBusy) {
            Text("Подтвердите вход в Telegram и вернитесь сюда", style = PamirType.support, color = Pamir.colors.textDim)
            Spacer(Modifier.height(Gap.s))
            SecondaryButton("Отменить") { cancelLogin() }
        } else {
            PrimaryButton("Войти через Telegram", icon = PamirIcons.Telegram) { loginTelegram() }
        }
        Spacer(Modifier.height(Gap.s))
        SecondaryButton("Войти по почте и паролю", icon = PamirIcons.Mail) { emailRegister = false; emailLoginOpen = true }
    }

    @Composable
    private fun TrialCard() {
        val o = trialOffer?.takeIf { trialShown } ?: return
        val days = o.optInt("duration_days")
        NoteCard(
            PamirIcons.Star, "Пробный период — бесплатно",
            "${o.optString("name").takeIf { it.isNotBlank() && it != "null" } ?: "VPN"} на $days ${plural(days, "день", "дня", "дней")}. Один раз, без оплаты и привязки карты.",
            Tone.ACCENT
        ) {
            PrimaryButton("Попробовать бесплатно", icon = PamirIcons.Bolt, loading = trialBusy) { activateTrial() }
        }
    }

    @Composable
    private fun ColumnScope.RenewContent() {
        val c = Pamir.colors
        if (trialShown) {
            TrialCard()
            Spacer(Modifier.height(Gap.s))
        }
        if (renewKeys.size > 1) {
            SectionHeader("Ключ", Modifier.padding(top = 0.dp))
            renewKeys.forEach { k ->
                val id = k.optInt("id")
                SheetRow(
                    selected = id == renewKeyId,
                    leading = { IconBadge(PamirIcons.Key, size = 40.dp) },
                    title = k.optString("display_name").ifBlank { "Ключ #$id" },
                    detail = keyExpiry(k),
                    onClick = { renewKeyId = id }
                )
            }
        } else if (renewKeys.size == 1) {
            Text(
                "${renewKeys[0].optString("display_name").ifBlank { "Ваш ключ" }} · ${keyExpiry(renewKeys[0])}",
                style = PamirType.support, color = c.textDim
            )
        }
        val promo = activePromo
        if (promo != null) {
            Banner(PamirIcons.Star, "Скидка $promo% применится при оплате", null, Tone.ACCENT, {}, Modifier.padding(bottom = Gap.s))
        } else if (lastChance != null) {
            Banner(PamirIcons.Star, "Скидка ${lastChance?.optInt("discount_percent")}% на продление — только сейчас", "Применить", Tone.WARN, { applyLastChance() }, Modifier.padding(bottom = Gap.s))
        }
        val key = renewKeys.firstOrNull { it.optInt("id") == renewKeyId }
        val group = key?.optInt("tariff_group_id", 0) ?: 0
        val list = tariffs.filter { group == 0 || it.optInt("group_id", 0) == 0 || it.optInt("group_id") == group }.ifEmpty { tariffs }
        SectionHeader("Тариф")
        if (list.isEmpty()) {
            Text("Тарифы сейчас недоступны. Попробуйте позже или продлите в кабинете.", style = PamirType.support, color = c.textDim)
            Spacer(Modifier.height(Gap.m))
            SecondaryButton("Открыть кабинет") { openUrl(CABINET_URL) }
            return
        }
        list.forEach { t ->
            val id = t.optInt("id")
            val price = t.optLong("price_minor")
            val days = t.optInt("duration_days")
            PamirCard(Modifier.padding(vertical = Gap.xs), contentPadding = 14.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t.optString("name"), style = PamirType.body.copy(fontWeight = FontWeight.Bold), color = c.text)
                        if (days > 0) Text("$days ${plural(days, "день", "дня", "дней")}", style = PamirType.support, color = c.textDim)
                    }
                    if (promo != null) {
                        Column(horizontalAlignment = Alignment.End) {
                            Text(rub(price), style = PamirType.support.copy(textDecoration = androidx.compose.ui.text.style.TextDecoration.LineThrough), color = c.textDim)
                            Text(rub(Math.round(price * (100 - promo) / 10_000.0) * 100), style = PamirType.number.copy(fontSize = 20.sp), color = c.accentText)
                        }
                    } else {
                        Text(rub(price), style = PamirType.number.copy(fontSize = 20.sp), color = c.accentText)
                    }
                }
                Spacer(Modifier.height(Gap.m))
                Row(horizontalArrangement = Arrangement.spacedBy(Gap.s)) {
                    PrimaryButton("СБП / Карта", Modifier.weight(1f), loading = payBusy == "$id:yookassa_qr") { pay(id, "yookassa_qr") }
                    val bal = balanceMinor
                    if (bal != null && bal >= price) {
                        SecondaryButton("С баланса", Modifier.weight(1f), loading = payBusy == "$id:balance") { pay(id, "balance") }
                    }
                }
            }
        }
        balanceMinor?.let {
            Spacer(Modifier.height(Gap.s))
            Text("На балансе: ${rub(it)}", style = PamirType.support, color = c.textDim, modifier = Modifier.align(Alignment.CenterHorizontally))
        }
        var promoOpen by remember { mutableStateOf(false) }
        Spacer(Modifier.height(Gap.s))
        if (promoOpen) PromoCard()
        else TextAction("Есть промокод?", Modifier.align(Alignment.CenterHorizontally), icon = PamirIcons.Star) { promoOpen = true }
    }

    private fun keyExpiry(k: JSONObject): String {
        val raw = k.optString("expires_at")
        if (!k.optBoolean("is_active")) return "закончилась"
        if (raw.isBlank() || raw == "null") return "активна"
        val date = raw.take(10).split("-")
        return if (date.size == 3) "до ${date[2]}.${date[1]}.${date[0]}" else "активна"
    }

    // ---------- report ----------

    @Composable
    private fun ReportSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        var text by remember { mutableStateOf("") }
        var withLog by remember { mutableStateOf(true) }
        PamirSheet(
            onDismiss = onDismiss,
            title = "Сообщить о проблеме",
            subtitle = "Опишите, что случилось: что нажимали, какой сервер, мобильный интернет или Wi-Fi."
        ) {
            OutlinedTextField(
                value = text, onValueChange = { if (it.length <= 1500) text = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 140.dp),
                placeholder = { Text("Например: не подключается Испания 1 на мобильном интернете", style = PamirType.support) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                shape = Radius.m,
                colors = pamirFieldColors()
            )
            Spacer(Modifier.height(Gap.m))
            RowGroup {
                ToggleRow(PamirIcons.Attach, "Приложить журнал", "Технические записи — без паролей и ссылок", withLog) { withLog = it }
            }
            Spacer(Modifier.height(Gap.l))
            PrimaryButton("Отправить", loading = reportBusy) {
                if (text.isBlank()) toast("Опишите проблему хотя бы парой слов") else sendReport(text.trim(), withLog)
            }
            Spacer(Modifier.height(Gap.s))
            Text(
                "Если вы вошли через Telegram, мы сможем написать вам", style = PamirType.caption, color = c.textDim,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()
            )
        }
    }

    // ---------- cabinet ----------

    @Composable
    private fun CabinetScreen() {
        val c = Pamir.colors
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.l)
                .padding(bottom = Gap.l)
        ) {
            ScreenTitle("Кабинет")
            Spacer(Modifier.height(Gap.m))
            if (!loggedIn) {
                NoteCard(
                    PamirIcons.Person, "Войдите в аккаунт",
                    "Подписка, баланс, устройства, платежи и поддержка — всё здесь, без перехода на сайт.", Tone.ACCENT
                ) { LoginButtons() }
                return@Column
            }
            BalanceCard()
            if (cabLoading && !cabLoaded) {
                Spacer(Modifier.height(Gap.m))
                SkeletonCard("Загружаем кабинет")
                Spacer(Modifier.height(Gap.m))
                SkeletonCard("Загружаем кабинет")
                return@Column
            }
            if (trialShown) {
                Spacer(Modifier.height(Gap.m))
                TrialCard()
            }
            SectionHeader("Подписка")
            if (renewKeys.isEmpty() && cabLoaded) {
                NoteCard(PamirIcons.Key, "Подписки пока нет", "Выберите тариф — подключится за минуту.", Tone.ACCENT) {
                    PrimaryButton("Выбрать тариф") { openRenew() }
                }
            }
            renewKeys.forEachIndexed { i, k ->
                if (i > 0) Spacer(Modifier.height(Gap.m))
                KeyCard(k)
            }
            if (cardInfo != null && renewKeys.isNotEmpty()) {
                SectionHeader("Автопродление")
                AutopayCard()
            }
            val devKeys = renewKeys.filter { cabDevices.containsKey(it.optInt("id")) }
            if (devKeys.isNotEmpty()) {
                SectionHeader("Устройства")
                devKeys.forEachIndexed { i, k ->
                    if (i > 0) Spacer(Modifier.height(Gap.m))
                    DevicesCard(k)
                }
            }
            cabReferral?.takeIf { it.optString("link").isNotBlank() }?.let { r ->
                SectionHeader("Пригласить друзей")
                ReferralCard(r)
            }
            SectionHeader("История платежей")
            PaymentsCard()
        }
    }

    @Composable
    private fun BalanceCard() {
        val c = Pamir.colors
        PamirCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBadge(PamirIcons.Wallet, size = 44.dp, iconSize = 24.dp)
                Spacer(Modifier.width(Gap.m))
                Column(Modifier.weight(1f)) {
                    Text("Баланс", style = PamirType.support, color = c.textDim)
                    Text(balanceMinor?.let { rub(it) } ?: "—", style = PamirType.number, color = c.text)
                }
                PrimaryButton("Пополнить", Modifier, icon = PamirIcons.Add) { cabTopupOpen = true }
            }
        }
    }

    @Composable
    private fun KeyCard(k: JSONObject) {
        val c = Pamir.colors
        val id = k.optInt("id")
        val active = k.optBoolean("is_active")
        val left = if (active) daysUntil(k.optString("expires_at").takeIf { it != "null" }) else null
        val used = k.optLong("traffic_used")
        val limit = k.optLong("traffic_limit")
        val (status, tone) = when {
            !active -> "Закончилась" to Tone.DANGER
            left != null && left <= 3 -> "Осталось ${maxOf(left, 0)} ${plural(maxOf(left, 0), "день", "дня", "дней")}" to Tone.WARN
            else -> "Активна" to Tone.ACCENT
        }
        PamirCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(keyName(k), style = PamirType.subtitle, color = c.text)
                    val tn = k.optString("tariff_name").takeIf { it.isNotBlank() && it != "null" }
                    if (tn != null) Text(tn, style = PamirType.support, color = c.textDim)
                }
                Chip(status, tone)
            }
            if (id == deviceKeyId && renewKeys.size > 1) {
                Spacer(Modifier.height(Gap.s))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(PamirIcons.Phone, contentDescription = null, modifier = Modifier.size(16.dp), tint = c.accentText)
                    Spacer(Modifier.width(6.dp))
                    Text("Используется на этом телефоне", style = PamirType.caption.copy(fontWeight = FontWeight.SemiBold), color = c.accentText)
                }
            }
            Spacer(Modifier.height(Gap.m))
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (active && left != null) {
                    val d = maxOf(left, 0)
                    DaysRing(d, plural(d, "день", "дня", "дней"), tone)
                    Spacer(Modifier.width(Gap.l))
                }
                Column(Modifier.weight(1f)) {
                    Text(keyExpiry(k).replaceFirstChar { it.uppercase() }, style = PamirType.body, color = c.text)
                    if (limit > 0) {
                        val frac = (used.toFloat() / limit.toFloat()).coerceIn(0f, 1f)
                        Spacer(Modifier.height(Gap.s))
                        ProgressLine(frac, if (frac > 0.9f) c.danger else c.accentDeep)
                        Spacer(Modifier.height(Gap.xs))
                        Text("Трафик: ${fmtBytes(used)} из ${fmtBytes(limit)}", style = PamirType.caption, color = c.textDim)
                    } else if (used > 0) {
                        Spacer(Modifier.height(Gap.xs))
                        Text("Трафик: ${fmtBytes(used)} · без лимита", style = PamirType.caption, color = c.textDim)
                    }
                }
            }
            if (hasCard()) {
                Spacer(Modifier.height(Gap.s))
                ToggleRow(
                    leading = null, title = "Автопродление",
                    subtitle = if (k.optBoolean("auto_renew")) "Продлим с карты в день окончания" else "Выключено — продлевайте вручную",
                    checked = k.optBoolean("auto_renew"),
                    onCheckedChange = { toggleAutoRenew(k, it) }
                )
            }
            Spacer(Modifier.height(Gap.l))
            PrimaryButton(if (active) "Продлить" else "Возобновить") { openRenew(id) }
            if (active && k.optString("subscription_url").startsWith("http")) {
                Spacer(Modifier.height(Gap.s))
                SecondaryButton("Отправить на другой телефон", icon = PamirIcons.Share) { shareKey(k) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextAction("Переименовать", color = c.textDim, icon = PamirIcons.Edit) { renameTarget = k }
                if (active && id != deviceKeyId && subKey(k.optString("subscription_url")) !in mySubUrls()) {
                    TextAction("На этот телефон", color = c.accentText, icon = PamirIcons.Phone) {
                        if (!updating) lifecycleScope.launch { applyDeviceKey(k) }
                    }
                }
            }
        }
    }

    @Composable
    private fun DevicesCard(k: JSONObject) {
        val c = Pamir.colors
        val id = k.optInt("id")
        val (list, limit) = cabDevices[id] ?: return
        PamirCard {
            Text(
                (if (renewKeys.size > 1) "${k.optString("display_name").ifBlank { "Ключ #$id" }} · " else "") +
                    "${list.size}" + (if (limit > 0) " из $limit" else "") + " ${plural(list.size, "устройство", "устройства", "устройств")}",
                style = PamirType.body, color = c.text
            )
            if (list.isEmpty()) {
                Spacer(Modifier.height(Gap.xs))
                Text("Пока ни одного — устройства появятся после первого подключения.", style = PamirType.support, color = c.textDim)
            }
            list.forEach { d ->
                val devId = d.optInt("id")
                val name = listOf(d.optString("device_model"), d.optString("device_os")).filter { it.isNotBlank() && it != "null" }.joinToString(" · ")
                    .ifBlank { "Устройство" }
                Spacer(Modifier.height(Gap.s))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBadge(PamirIcons.Phone, tint = c.textDim, background = c.surfaceHigh)
                    Spacer(Modifier.width(Gap.m))
                    Column(Modifier.weight(1f)) {
                        Text(name, style = PamirType.body.copy(fontSize = 14.sp), color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val seen = fmtDate(d.optString("last_seen").takeIf { it != "null" })
                        if (seen.isNotEmpty()) Text("был в сети $seen", style = PamirType.caption, color = c.textDim)
                    }
                    TextAction(if (cabBusy == "dev$devId") "Отключаем…" else "Отключить", color = c.danger) { removeDevice(id, devId) }
                }
            }
        }
    }

    @Composable
    private fun ReferralCard(r: JSONObject) {
        val c = Pamir.colors
        PamirCard {
            Text("Друг оформит подписку по вашей ссылке — вы оба получите +7 дней", style = PamirType.body, color = c.text)
            Spacer(Modifier.height(Gap.xs))
            val earned = r.optLong("total_reward_minor")
            Text(
                "Приглашено: ${r.optInt("referrals_count")}" + if (earned > 0) " · заработано раньше ${rub(earned)}" else "",
                style = PamirType.support, color = c.textDim
            )
            Spacer(Modifier.height(Gap.m))
            Text(
                r.optString("link"), style = PamirType.support.copy(fontWeight = FontWeight.SemiBold), color = c.accentText,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(Radius.s)
                    .background(c.surfaceHigh)
                    .padding(horizontal = Gap.m, vertical = Gap.m)
            )
            Spacer(Modifier.height(Gap.m))
            PrimaryButton("Поделиться ссылкой", icon = PamirIcons.Share) {
                runCatching {
                    startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                        .putExtra(Intent.EXTRA_TEXT, "Подключайся к Pamir VPN по моей ссылке — после оформления подписки получишь +7 дней в подарок: " + r.optString("link")), null))
                }
            }
            TextAction("Скопировать ссылку", Modifier.align(Alignment.CenterHorizontally), icon = PamirIcons.Copy) { copyText("ref", r.optString("link")) }
        }
    }

    @Composable
    private fun PromoCard() {
        val c = Pamir.colors
        var code by remember { mutableStateOf("") }
        PamirCard {
            Text("Введите промокод — цены выше пересчитаются со скидкой.", style = PamirType.support, color = c.textDim)
            Spacer(Modifier.height(Gap.m))
            OutlinedTextField(
                value = code, onValueChange = { code = it.take(40); promoResult = null }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Введите код", style = PamirType.bodyRegular) },
                leadingIcon = { Icon(PamirIcons.Star, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { applyPromo(code) }),
                shape = Radius.m, colors = pamirFieldColors()
            )
            promoResult?.let { (ok, msg) ->
                Spacer(Modifier.height(Gap.s))
                Text(msg, style = PamirType.support, color = if (ok) c.accentText else c.danger)
            }
            Spacer(Modifier.height(Gap.m))
            PrimaryButton("Применить", loading = promoBusy) { applyPromo(code) }
        }
    }

    @Composable
    private fun PaymentsCard() {
        val c = Pamir.colors
        PamirCard {
            val shown = cabPayments.filter { it.optString("status") == "paid" }.take(8)
            if (shown.isEmpty()) {
                Text(if (cabLoaded) "Платежей пока нет" else "Загружаем…", style = PamirType.support, color = c.textDim)
            }
            shown.forEachIndexed { i, pmt ->
                if (i > 0) Spacer(Modifier.height(Gap.m))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBadge(PamirIcons.Receipt, tint = c.textDim, background = c.surfaceHigh, size = 32.dp, iconSize = 18.dp)
                    Spacer(Modifier.width(Gap.m))
                    Column(Modifier.weight(1f)) {
                        Text(
                            pmt.optString("description").takeIf { it.isNotBlank() && it != "null" } ?: "Платёж",
                            style = PamirType.body.copy(fontSize = 14.sp), color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            fmtDate(pmt.optString("paid_at").takeIf { it != "null" && it.isNotBlank() } ?: pmt.optString("created_at")),
                            style = PamirType.caption, color = c.textDim
                        )
                    }
                    Text(rub(pmt.optLong("payable_amount_minor")), style = PamirType.label.copy(fontSize = 14.sp), color = c.accentText)
                }
            }
        }
    }

    @Composable
    private fun SupportCard() {
        val c = Pamir.colors
        var text by remember { mutableStateOf("") }
        PamirCard {
            val msgs = cabSupport.takeLast(6)
            if (msgs.isEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBadge(PamirIcons.Chat)
                    Spacer(Modifier.width(Gap.m))
                    Text("Напишите нам — отвечаем быстро. Ответ появится здесь и придёт в Telegram.", style = PamirType.support, color = c.textDim)
                }
            }
            msgs.forEach { m ->
                val mine = m.optString("sender_type") == "user"
                val body = runCatching { Html.fromHtml(m.optString("text"), Html.FROM_HTML_MODE_COMPACT).toString().trim() }.getOrDefault(m.optString("text"))
                    .ifBlank { if (m.optString("media_type") == "photo") "Фото" else "" }
                if (body.isBlank()) return@forEach
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp),
                    horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start
                ) {
                    Text(
                        body, style = PamirType.support, color = if (mine) c.onAccent else c.text,
                        modifier = Modifier
                            .fillMaxWidth(0.85f)
                            .wrapContentWidth(if (mine) Alignment.End else Alignment.Start)
                            .clip(RoundedCornerShape(16.dp, 16.dp, if (mine) 4.dp else 16.dp, if (mine) 16.dp else 4.dp))
                            .background(if (mine) c.accent else c.surfaceHigh)
                            .padding(horizontal = Gap.m, vertical = Gap.s)
                    )
                }
            }
            Spacer(Modifier.height(Gap.m))
            OutlinedTextField(
                value = text, onValueChange = { text = it.take(1500) }, modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Ваше сообщение", style = PamirType.support) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                shape = Radius.m, colors = pamirFieldColors(), maxLines = 4
            )
            Spacer(Modifier.height(Gap.m))
            PrimaryButton("Отправить", loading = cabBusy == "support") {
                if (text.isBlank()) toast("Введите сообщение") else { sendSupport(text); text = "" }
            }
        }
    }

    @Composable
    private fun TopupSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        var custom by remember { mutableStateOf("") }
        PamirSheet(
            onDismiss = onDismiss,
            title = "Пополнение баланса",
            subtitle = "Оплата через СБП или карту. Деньги придут на баланс за пару секунд."
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(Gap.s)) {
                listOf(100, 300, 500, 1000).forEach { a ->
                    Box(
                        Modifier
                            .weight(1f)
                            .height(52.dp)
                            .clip(Radius.m)
                            .background(c.surface)
                            .border(1.dp, c.line, Radius.m)
                            .clickable(enabled = cabBusy == null, role = Role.Button) { topUp(a) },
                        contentAlignment = Alignment.Center
                    ) { Text("$a ₽", style = PamirType.label.copy(fontSize = 15.sp), color = c.text) }
                }
            }
            Spacer(Modifier.height(Gap.m))
            OutlinedTextField(
                value = custom, onValueChange = { custom = it.filter { ch -> ch.isDigit() }.take(5) }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Другая сумма, от 100 ₽", style = PamirType.bodyRegular) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                shape = Radius.m, colors = pamirFieldColors()
            )
            Spacer(Modifier.height(Gap.m))
            PrimaryButton("Пополнить", loading = cabBusy == "topup") {
                val v = custom.toIntOrNull() ?: 0
                if (v < 100) toast("Минимальная сумма — 100 ₽") else topUp(v)
            }
        }
    }

    // ---------- apps without VPN ----------

    @Composable
    private fun AppsScreen() {
        val c = Pamir.colors
        val list = appList
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.l)
                .padding(bottom = Gap.l)
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(top = Gap.s),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconAction(PamirIcons.Back, "Назад", { tab = Tab.SETTINGS }, Modifier.padding(end = Gap.xs))
                Text("Приложения без VPN", style = PamirType.headline, color = c.text, modifier = Modifier.semantics { heading() })
            }
            Text(
                "Некоторые банки и госсервисы не работают, когда включён VPN. Отметьте их — они будут ходить в интернет напрямую, а всё остальное останется защищённым.",
                style = PamirType.support, color = c.textDim,
                modifier = Modifier.padding(start = Gap.xs, end = Gap.xs, top = Gap.xs, bottom = Gap.s)
            )
            when {
                list == null -> {
                    Spacer(Modifier.height(Gap.m))
                    SkeletonCard("Ищем приложения")
                }
                list.isEmpty() -> {
                    Spacer(Modifier.height(Gap.m))
                    NoteCard(PamirIcons.Apps, "Популярных банков и сервисов не нашли", "Нужное приложение можно выбрать из полного списка ниже.", Tone.NEUTRAL) {}
                }
                else -> {
                    val rec = list.filter { it.group == "Банки" || it.group == "Госуслуги и налоги" }.map { it.pkg }
                    if (rec.isNotEmpty() && rec.any { bypassSel[it] != true }) {
                        Spacer(Modifier.height(Gap.s))
                        SecondaryButton("Отметить все банки и Госуслуги", icon = PamirIcons.Check) { setBypass(rec, true) }
                    }
                    list.groupBy { it.group }.forEach { (group, apps) ->
                        SectionHeader(group)
                        RowGroup {
                            apps.forEachIndexed { i, a ->
                                if (i > 0) RowDivider()
                                val on = bypassSel[a.pkg] == true
                                ToggleRow(
                                    leading = {
                                        if (a.icon != null) Image(a.icon, contentDescription = null, modifier = Modifier.size(36.dp).clip(Radius.s))
                                        else IconBadge(PamirIcons.Apps)
                                    },
                                    title = a.label,
                                    subtitle = if (on) "Напрямую, без VPN" else "Через VPN",
                                    checked = on,
                                    onCheckedChange = { setBypass(listOf(a.pkg), it) },
                                    subtitleColor = if (on) c.accentText else c.textDim
                                )
                            }
                        }
                    }
                }
            }
            SectionHeader("Другие")
            RowGroup {
                LinkRow(PamirIcons.Apps, "Все приложения", "Выбрать любое приложение из списка") {
                    appsChanged = true
                    startActivity(Intent(this@PamirActivity, PerAppProxyActivity::class.java))
                }
            }
        }
    }

    /** Support chat from Settings (same messages as in the web cabinet; answers also come to Telegram). */
    @Composable
    private fun SupportSheet(onDismiss: () -> Unit) {
        LaunchedEffect(Unit) { loadSupport() }
        PamirSheet(onDismiss = onDismiss, title = "Поддержка", subtitle = "Отвечаем быстро — ответ появится здесь") {
            SupportCard()
            Spacer(Modifier.height(Gap.s))
            TextAction("Написать в Telegram", Modifier.align(Alignment.CenterHorizontally), icon = PamirIcons.Telegram) { openUrl(BOT_URL) }
        }
    }

    /** Result of «О приложении» → check for updates: the latest version already, or a newer one to install. */
    @Composable
    private fun UpdateSheet(state: String, onDismiss: () -> Unit) {
        PamirSheet(onDismiss = onDismiss, title = "Обновление") {
            when (state) {
                "checking" -> SkeletonCard("Проверяем обновления")
                "new" -> NoteCard(
                    PamirIcons.Download, "Доступна версия ${newVersion.orEmpty()}",
                    "У вас ${appVersion()}. Обновление скачается и установится поверх — ключи и настройки сохранятся.", Tone.ACCENT
                ) {
                    PrimaryButton(
                        if (updProgress >= 0) "Загрузка $updProgress%" else "Обновить", icon = PamirIcons.Download
                    ) { installUpdate() }
                }
                "latest" -> NoteCard(PamirIcons.Check, "У вас последняя версия", "Pamir VPN ${appVersion()} — обновлений нет.", Tone.ACCENT) {
                    PrimaryButton("Отлично") { onDismiss() }
                }
                else -> NoteCard(PamirIcons.Warning, "Не удалось проверить", "Проверьте интернет и попробуйте ещё раз.", Tone.WARN) {
                    PrimaryButton("Проверить снова") { updCheck = "checking"; checkAppUpdate(manual = true) }
                }
            }
        }
    }

    // ---------- settings ----------

    @Composable
    private fun Settings() {
        var ru by remember { mutableStateOf(MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) }
        var boot by remember { mutableStateOf(MmkvManager.decodeStartOnBoot()) }
        var smart by remember { mutableStateOf(smartLte()) }
        var autoSwitch by remember { mutableStateOf(MmkvManager.decodeSettingsBool(PamirWatch.K_AUTO_SWITCH, true)) }
        val c = Pamir.colors
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Gap.l)
                .padding(bottom = Gap.l)
        ) {
            ScreenTitle("Настройки")
            SectionHeader("Подключение")
            RowGroup {
                ToggleRow(PamirIcons.Split, "Сайты РФ напрямую", "Госуслуги, банки — без VPN", ru) { ru = it; setRuDirect(it) }
                RowDivider()
                ToggleRow(PamirIcons.Refresh, "Автосмена сервера", "Если сервер перестал отвечать, подключим другой", autoSwitch) {
                    autoSwitch = it; MmkvManager.encodeSettings(PamirWatch.K_AUTO_SWITCH, it)
                }
                RowDivider()
                ToggleRow(PamirIcons.Signal, "Умный LTE-режим", "Сам включит LTE Обход при «белых списках»", smart) {
                    smart = it; MmkvManager.encodeSettings(PREF_SMART_LTE, it)
                }
                RowDivider()
                ToggleRow(PamirIcons.Power, "Автоподключение", "При включении телефона", boot) { boot = it; MmkvManager.encodeStartOnBoot(it) }
                RowDivider()
                val bc = remember { bypassCount() }
                LinkRow(PamirIcons.Apps, "Приложения без VPN", if (bc > 0) "Без VPN: $bc ${plural(bc, "приложение", "приложения", "приложений")}" else "Банки, Госуслуги и др.") {
                    loadApps(); tab = Tab.APPS
                }
            }
            SectionHeader("Оформление")
            RowGroup {
                Column(Modifier.padding(horizontal = 14.dp, vertical = Gap.m)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconBadge(PamirIcons.Theme)
                        Spacer(Modifier.width(14.dp))
                        Column {
                            Text("Тема", style = PamirType.body, color = c.text)
                            Text("«Авто» — как в настройках телефона", style = PamirType.support, color = c.textDim)
                        }
                    }
                    Spacer(Modifier.height(Gap.m))
                    SegmentedControl(
                        PamirThemeMode.entries.map { it.label },
                        selected = themeMode.ordinal,
                        onSelect = { setTheme(PamirThemeMode.entries[it]) }
                    )
                }
            }
            SectionHeader("Аккаунт")
            RowGroup {
                if (loggedIn) {
                    val dk = renewKeys.firstOrNull { it.optInt("id") == deviceKeyId }
                    LinkRow(PamirIcons.Key, "Ключ на этом телефоне", dk?.let { keyName(it) + " · сменить" } ?: "Выбрать, какой ключ использовать") { openKeyPicker() }
                    RowDivider()
                    LinkRow(PamirIcons.Person, "Вы вошли в аккаунт", balanceMinor?.let { "Баланс: ${rub(it)} · продление в приложении" } ?: "Продление прямо в приложении") { openRenew() }
                    RowDivider()
                    LinkRow(PamirIcons.Logout, "Выйти из аккаунта", "VPN отключится, ключ уйдёт с телефона", tone = Tone.DANGER) { signOut() }
                } else {
                    LinkRow(PamirIcons.Telegram, if (loginBusy) "Ждём подтверждения…" else "Войти через Telegram", "Продление и оплата прямо в приложении", loading = loginBusy) {
                        if (loginBusy) cancelLogin() else loginTelegram()
                    }
                    RowDivider()
                    LinkRow(PamirIcons.Mail, "Войти по почте", "Если привязали почту в кабинете") { emailRegister = false; emailLoginOpen = true }
                }
            }
            SectionHeader("Подписка")
            RowGroup {
                val upd = if (lastUpdate > 0) "Обновлено ${agoText(lastUpdate)}" else "Ещё не обновлялись"
                LinkRow(PamirIcons.Refresh, if (updating) "Обновляем…" else "Обновить серверы", upd, loading = updating) { updateSubscription() }
                RowDivider()
                LinkRow(PamirIcons.Share, "Пригласить друга", "Вам и другу — по +7 дней") { tab = Tab.CABINET }
            }
            SectionHeader("Помощь")
            RowGroup {
                LinkRow(PamirIcons.Info, "Новости", news.firstOrNull()?.let { PamirNews.date(it).ifEmpty { null } }?.let { "Последняя — $it" } ?: "Новые серверы и акции") { openNews() }
                RowDivider()
                LinkRow(PamirIcons.Chat, "Поддержка", if (loggedIn) "Напишите нам прямо здесь" else "Ответим в Telegram") {
                    if (loggedIn) supportOpen = true else openUrl(BOT_URL)
                }
                RowDivider()
                LinkRow(PamirIcons.Report, "Сообщить о проблеме", "Отправим описание и журнал разработчикам") { reportOpen = true }
                RowDivider()
                LinkRow(PamirIcons.Info, "О приложении", if (newVersion != null) "Версия ${appVersion()} · доступна $newVersion" else "Версия ${appVersion()} · актуальная") {
                    updCheck = if (newVersion != null) "new" else "checking"
                    if (newVersion == null) checkAppUpdate(manual = true)
                }
            }
            Spacer(Modifier.height(Gap.m))
            TextAction("Расширенные настройки", Modifier.align(Alignment.CenterHorizontally), icon = PamirIcons.Settings) {
                startActivity(Intent(this@PamirActivity, MainActivity::class.java))
            }
        }
    }

    private fun appVersion(): String =
        runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: ""

    private fun agoText(ts: Long): String {
        val m = (System.currentTimeMillis() - ts) / 60000
        return when {
            m < 1 -> "только что"
            m < 60 -> "$m мин назад"
            m < 60 * 24 -> "${m / 60} ч назад"
            else -> "${m / 1440} дн назад"
        }
    }

    private fun plural(n: Int, one: String, few: String, many: String): String {
        val a = n % 100; val b = n % 10
        return when {
            a in 11..14 -> many
            b == 1 -> one
            b in 2..4 -> few
            else -> many
        }
    }

    // ---------- key of this phone ----------

    @Composable
    private fun KeyPickerSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        val keys = activeKeys(renewKeys)
        PamirSheet(
            onDismiss = onDismiss,
            title = "Какой ключ на этом телефоне?",
            subtitle = if (keys.isEmpty()) null else if (keyPickerMigrate) "Сейчас здесь подключены сразу несколько ключей, поэтому серверы повторяются. Оставьте свой — остальные можно отправить близким из кабинета."
            else "У вас несколько ключей. Выберите свой — остальные можно отправить близким из кабинета."
        ) {
            if (keys.isEmpty()) {
                if (keyPickerLoading) SkeletonCard("Загружаем ключи")
                else NoteCard(PamirIcons.Key, "Активных ключей нет", "Оформите подписку — ключ сразу подключится к этому телефону.", Tone.ACCENT) {
                    PrimaryButton("Выбрать тариф") { keyPickerOpen = false; openRenew() }
                }
                return@PamirSheet
            }
            keys.forEach { k ->
                SheetRow(
                    selected = k.optInt("id") == deviceKeyId,
                    leading = { IconBadge(PamirIcons.Key, size = 40.dp) },
                    title = keyName(k),
                    detail = keyExpiry(k),
                    onClick = { if (!updating) lifecycleScope.launch { applyDeviceKey(k) } }
                )
            }
            if (updating) {
                Spacer(Modifier.height(Gap.m))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(color = c.accentText, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(Gap.s))
                    Text("Подключаем ключ…", style = PamirType.support, color = c.textDim)
                }
            }
        }
    }

    @Composable
    private fun RenameKeySheet(k: JSONObject, onDismiss: () -> Unit) {
        val c = Pamir.colors
        var name by remember { mutableStateOf(keyName(k)) }
        PamirSheet(onDismiss = onDismiss, title = "Название ключа", subtitle = "Например: «Мама» или «Ноутбук» — чтобы не путать ключи") {
            OutlinedTextField(
                value = name, onValueChange = { name = it.take(40) }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                leadingIcon = { Icon(PamirIcons.Key, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { renameKey(k, name) }),
                shape = Radius.m, colors = pamirFieldColors()
            )
            Spacer(Modifier.height(Gap.l))
            PrimaryButton("Сохранить", loading = cabBusy == "rename") { renameKey(k, name) }
        }
    }

    // ---------- e-mail login ----------

    @Composable
    private fun EmailCodeStep(target: String, onDismiss: () -> Unit) {
        val c = Pamir.colors
        var code by remember { mutableStateOf("") }
        var now by remember { mutableStateOf(System.currentTimeMillis()) }
        LaunchedEffect(emailCodeSentAt) { while (true) { now = System.currentTimeMillis(); delay(1000) } }
        val wait = ((emailCodeSentAt + 60_000L - now) / 1000).coerceAtLeast(0)
        PamirSheet(onDismiss = onDismiss, title = "Подтвердите почту", subtitle = "Мы отправили 6-значный код на $target. Письмо может попасть в «Спам»") {
            OutlinedTextField(
                value = code, onValueChange = { v -> code = v.filter { it.isDigit() }.take(6); if (code.length == 6) verifyEmailCode(code) },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Код из письма", style = PamirType.bodyRegular) },
                leadingIcon = { Icon(PamirIcons.Mail, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                textStyle = PamirType.number.copy(color = c.text, letterSpacing = 6.sp),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { verifyEmailCode(code) }),
                shape = Radius.m, colors = pamirFieldColors()
            )
            Spacer(Modifier.height(Gap.l))
            PrimaryButton("Подтвердить", loading = emailBusy) { verifyEmailCode(code) }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                if (wait > 0) Text("Новый код — через $wait с", style = PamirType.support, color = c.textDim, modifier = Modifier.padding(vertical = Gap.s))
                else TextAction("Отправить код ещё раз", color = c.accentText) { resendEmailCode() }
                TextAction("Другая почта") { emailCodeFor = null }
            }
        }
    }

    @Composable
    private fun EmailLoginSheet(onDismiss: () -> Unit) {
        val c = Pamir.colors
        var email by remember { mutableStateOf("") }
        var pass by remember { mutableStateOf("") }
        var pass2 by remember { mutableStateOf("") }
        val reg = emailRegister
        val submit = { if (reg) registerEmail(email, pass, pass2) else loginEmail(email, pass) }
        emailCodeFor?.let { target ->
            EmailCodeStep(target, onDismiss)
            return
        }
        PamirSheet(
            onDismiss = onDismiss,
            title = if (reg) "Регистрация" else "Вход по почте",
            subtitle = if (reg) "Создайте аккаунт Pamir VPN — подписку оформите сразу после этого"
            else "Почта и пароль от личного кабинета Pamir VPN"
        ) {
            OutlinedTextField(
                value = email, onValueChange = { email = it.trim() }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Почта", style = PamirType.bodyRegular) },
                leadingIcon = { Icon(PamirIcons.Mail, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                shape = Radius.m, colors = pamirFieldColors()
            )
            Spacer(Modifier.height(Gap.s))
            OutlinedTextField(
                value = pass, onValueChange = { pass = it }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text(if (reg) "Придумайте пароль" else "Пароль", style = PamirType.bodyRegular) },
                leadingIcon = { Icon(PamirIcons.Lock, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                textStyle = PamirType.bodyRegular.copy(color = c.text),
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = if (reg) ImeAction.Next else ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { submit() }),
                shape = Radius.m, colors = pamirFieldColors()
            )
            if (reg) {
                Spacer(Modifier.height(Gap.s))
                OutlinedTextField(
                    value = pass2, onValueChange = { pass2 = it }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Повторите пароль", style = PamirType.bodyRegular) },
                    leadingIcon = { Icon(PamirIcons.Lock, contentDescription = null, modifier = Modifier.size(20.dp), tint = c.textDim) },
                    textStyle = PamirType.bodyRegular.copy(color = c.text),
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                    shape = Radius.m, colors = pamirFieldColors()
                )
            }
            Spacer(Modifier.height(Gap.l))
            PrimaryButton(if (reg) "Создать аккаунт" else "Войти", loading = emailBusy) { submit() }
            if (reg) {
                TextAction("У меня уже есть аккаунт", Modifier.align(Alignment.CenterHorizontally), color = c.accentText) { emailRegister = false }
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextAction("Забыли пароль?", color = c.accentText) { forgotPassword(email) }
                    TextAction("Регистрация") { emailRegister = true }
                }
            }
        }
    }
}
