package com.v2ray.ang.pamir

import android.content.BroadcastReceiver
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.TrafficStats
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import android.os.Process
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.graphics.drawable.toBitmap
import androidx.lifecycle.lifecycleScope
import com.v2ray.ang.AppConfig
import com.v2ray.ang.R
import com.v2ray.ang.core.LauncherManager
import com.v2ray.ang.enums.RoutingType
import com.v2ray.ang.extension.toast
import com.v2ray.ang.handler.AngConfigManager
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.handler.SettingsManager
import com.v2ray.ang.helper.MessageHelper
import com.v2ray.ang.ui.main.MainActivity
import com.v2ray.ang.ui.perappproxy.PerAppProxyActivity
import com.v2ray.ang.util.Utils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL

// ---------- palette ----------
private val BgColor = Color(0xFF0A121D)
private val Surface1 = Color(0xFF111C2B)
private val Surface2 = Color(0xFF162335)
private val Line = Color(0x12FFFFFF)
private val Mint = Color(0xFF2BEFC0)
private val MintDeep = Color(0xFF17B896)
private val TextMain = Color(0xFFEEF3F7)
private val TextDim = Color(0xFF8494A8)
private val Danger = Color(0xFFF0766A)

private const val CABINET_URL = "https://app.pamirlink.ru/?from=android"
private const val BOT_URL = "https://t.me/pamirlink_bot"
private const val PREF_RU_DIRECT = "pamir_ru_direct"
private const val PREF_ROUTING_INIT = "pamir_routing_init"
private const val PREF_AUTO_BEST = "pamir_auto_best"
private const val PREF_LAST_SUB_UPDATE = "pamir_last_sub_update"
private const val PREF_USER_CHOSE = "pamir_user_chose"
private const val PREF_SMART_LTE = "pamir_smart_lte"
private const val PREF_AUTO_LTE_ACTIVE = "pamir_auto_lte_active"
private const val PREF_PREFERRED = "pamir_preferred"
private const val UPDATE_JSON = "https://app.pamirlink.ru/download/android.json"
private const val DOWNLOAD_BASE = "https://app.pamirlink.ru/download/"

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

private enum class Tab { HOME, SETTINGS, APPS }

class PamirActivity : AppCompatActivity() {

    private var running by mutableStateOf(false)
    private var connecting by mutableStateOf(false)
    private var servers by mutableStateOf<List<PServer>>(emptyList())
    private var selected by mutableStateOf<String?>(null)
    private val pings = mutableStateMapOf<String, Int>()
    private var pingBusy by mutableStateOf(false)
    private var updating by mutableStateOf(false)
    private var connectedAt by mutableLongStateOf(0L)
    private var ipInfo by mutableStateOf("")
    private var daysLeft by mutableStateOf<Int?>(null)
    private var lastUpdate by mutableLongStateOf(0L)
    private var whitelist by mutableStateOf(false)
    private var autoSwitched = false
    private var lastPrecheck = 0L
    private var newVersion by mutableStateOf<String?>(null)
    private var newVersionUrl = ""
    private var updProgress by mutableStateOf(-1)
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
    private var payBuy = false
    private var payJob: kotlinx.coroutines.Job? = null
    private var reportOpen by mutableStateOf(false)
    private var emailLoginOpen by mutableStateOf(false)
    private var emailBusy by mutableStateOf(false)
    private var reportBusy by mutableStateOf(false)

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
                AppConfig.MSG_STATE_RUNNING, AppConfig.MSG_STATE_START_SUCCESS -> onRunning(true)
                AppConfig.MSG_STATE_NOT_RUNNING, AppConfig.MSG_STATE_STOP_SUCCESS -> onRunning(false)
                AppConfig.MSG_STATE_START_FAILURE -> {
                    onRunning(false)
                    toast("Не удалось подключиться. Попробуйте другой сервер")
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
        setContent { PamirTheme { Root() } }
        if (servers.isNotEmpty() && System.currentTimeMillis() - lastUpdate > 60 * 60 * 1000L) {
            updateSubscription(silent = true)
        }
        checkAppUpdate()
        PamirReminderWorker.schedule(this)
        lifecycleScope.launch(Dispatchers.IO) {
            delay(4000)
            runCatching { PamirCrash.sendPending(applicationContext, proxyPort()) }
        }
        if (loggedIn) refreshAccount()
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
                logout(); if (!quiet) toast("Войдите заново через Telegram", true)
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
            openUrl(link)
            val enc = Uri.encode(token)
            repeat(150) {
                delay(2000)
                val r = api(quiet = true) { p -> PamirApi.call("/auth/telegram/poll?token=$enc", auth = false, proxyPort = p) }
                if (r?.optString("status") == "approved") {
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
            val r = api { p ->
                PamirApi.call("/auth/email/login", "POST", JSONObject().put("email", email.trim()).put("password", password), auth = false, proxyPort = p)
            }
            emailBusy = false
            val t = r?.optString("access_token").orEmpty()
            if (t.isBlank()) return@launch
            PamirApi.token = t
            loggedIn = true
            emailLoginOpen = false
            Log.w("Pamir", "email login ok")
            onLoggedIn()
        }
    }

    private fun forgotPassword(email: String) {
        if (!email.contains("@")) { toast("Сначала введите почту"); return }
        lifecycleScope.launch {
            val r = api { p -> PamirApi.call("/auth/email/forgot-password", "POST", JSONObject().put("email", email.trim()), auth = false, proxyPort = p) }
            if (r != null) toast("Если почта зарегистрирована, мы отправили ссылку для сброса пароля", true)
        }
    }

    private fun logout() {
        PamirApi.token = null
        loggedIn = false
        balanceMinor = null
        renewKeys = emptyList()
    }

    private fun refreshAccount() {
        lifecycleScope.launch {
            val me = api(quiet = true) { p -> PamirApi.call("/auth/me", proxyPort = p) } ?: return@launch
            balanceMinor = if (me.isNull("balance")) null else me.optLong("balance")
        }
    }

    /** After login: import the subscriptions of all active keys. */
    private suspend fun onLoggedIn() {
        refreshAccount()
        val keys = api { p -> PamirApi.call("/auth/keys", proxyPort = p) }?.optJSONArray("keys") ?: return
        val list = (0 until keys.length()).map { keys.getJSONObject(it) }
        renewKeys = list
        val urls = list.filter { it.optBoolean("is_active") }.mapNotNull { it.optString("subscription_url").takeIf { u -> u.startsWith("http") } }
        if (urls.isEmpty()) {
            toast(if (list.isEmpty()) "Вы вошли. Подписки пока нет — выберите тариф" else "Вы вошли. Подписка закончилась — продлите её", true)
            openRenew()
            return
        }
        updating = true
        var added = 0
        withContext(Dispatchers.IO) {
            urls.forEach { u -> runCatching { AngConfigManager.importBatchConfig(u, "", false) }.onSuccess { added += it.first + it.second } }
        }
        updating = false
        MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, System.currentTimeMillis())
        reloadServers()
        toast(if (added > 0) "Готово! Подписка подключена" else "Вы вошли в аккаунт")
        if (renewOpen) openRenew()
    }

    private fun mySubUrls(): Set<String> =
        runCatching { MmkvManager.decodeSubscriptions().map { it.subscription.url }.toSet() }.getOrDefault(emptySet())

    /** Renewal inside the app (tariffs + payment); without login — offer to log in. */
    private fun openRenew() {
        renewOpen = true
        if (payState == "paid" || payState == "failed") payState = null
        if (!loggedIn) return
        renewLoading = true
        lifecycleScope.launch {
            refreshAccount()
            val keysJ = api { p -> PamirApi.call("/auth/keys", proxyPort = p) }
            val tarJ = api(quiet = true) { p -> PamirApi.call("/topup/tariffs", proxyPort = p) }
            renewLoading = false
            if (keysJ == null) return@launch
            val ka = keysJ.optJSONArray("keys")
            val list = if (ka == null) emptyList() else (0 until ka.length()).map { ka.getJSONObject(it) }
            renewKeys = list
            val mine = mySubUrls()
            renewKeyId = (list.firstOrNull { it.optString("subscription_url") in mine }
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
            when {
                r.optString("payment_url").startsWith("http") -> {
                    payUrl = r.optString("payment_url")
                    payOrder = r.optString("order_id").takeIf { it.isNotBlank() }
                    payState = "waiting"
                    openUrl(payUrl)
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
        }
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
        payJob?.cancel()
        Log.w("Pamir", "payment ok buy=$payBuy")
        lifecycleScope.launch {
            delay(1500)
            refreshAccount()
            if (payBuy) onLoggedIn() else updateSubscription(silent = true)
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
        daysLeft = list.firstNotNullOfOrNull { Regex("⏳\\s*(\\d+)\\s*D").find(it.rawRemarks)?.groupValues?.get(1)?.toIntOrNull() }
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
            val best = servers.filter { !it.isStub && !it.isLte && (pings[it.guid] ?: -1) > 0 }
                .minByOrNull { pings[it.guid] ?: Int.MAX_VALUE }
            if (best != null) {
                selectServer(best.guid)
                MmkvManager.encodeSettings(PREF_AUTO_BEST, true)
                toast("Выбран ${best.name}")
            } else toast("Не удалось проверить серверы")
        }
    }

    private suspend fun runPing() {
        if (pingBusy) return
        pingBusy = true
        val targets = servers.filter { !it.isStub }
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
        }.forEach { (g, ms) -> pings[g] = ms }
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
                toast("Нет соединения через VPN. Попробуйте другой сервер", true)
            }
        }
    }

    private fun smartLte() = MmkvManager.decodeSettingsBool(PREF_SMART_LTE, true)

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
        runPing()
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

    private fun checkAppUpdate() {
        lifecycleScope.launch {
            val json = withContext(Dispatchers.IO) {
                runCatching {
                    val c = URL(UPDATE_JSON).openConnection() as HttpURLConnection
                    c.connectTimeout = 6000; c.readTimeout = 6000
                    c.setRequestProperty("Cache-Control", "no-cache")
                    c.inputStream.bufferedReader().use { it.readText() }
                }.getOrNull()
            } ?: return@launch
            runCatching {
                val o = org.json.JSONObject(json)
                val v = o.optString("version")
                if (v.isNotBlank() && isNewer(v, appVersion())) {
                    val abi = if (android.os.Build.SUPPORTED_ABIS.contains("arm64-v8a") && o.has("arm64-v8a")) "arm64-v8a" else "universal"
                    val file = o.optJSONObject(abi)?.optString("file") ?: "pamir-vpn-universal.apk"
                    newVersionUrl = DOWNLOAD_BASE + file
                    newVersion = v
                }
            }
        }
    }

    private fun isNewer(remote: String, local: String): Boolean {
        val r = remote.split(".").map { it.toIntOrNull() ?: 0 }
        val l = local.split(".").map { it.toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(r.size, l.size)) {
            val a = r.getOrElse(i) { 0 }; val b = l.getOrElse(i) { 0 }
            if (a != b) return a > b
        }
        return false
    }

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
                runCatching {
                    val dir = java.io.File(cacheDir, "update").apply { mkdirs() }
                    val f = java.io.File(dir, "pamir-vpn.apk")
                    val c = URL(newVersionUrl).openConnection() as HttpURLConnection
                    c.connectTimeout = 10000; c.readTimeout = 20000
                    val total = c.contentLengthLong
                    c.inputStream.use { input ->
                        f.outputStream().use { out ->
                            val buf = ByteArray(64 * 1024)
                            var done = 0L
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
                    f
                }.getOrNull()
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

    private fun updateSubscription(silent: Boolean = false) {
        if (updating) return
        updating = true
        lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { runCatching { AngConfigManager.updateConfigViaSubAll() }.getOrNull() }
            updating = false
            if (res != null && res.successCount > 0) {
                MmkvManager.encodeSettings(PREF_LAST_SUB_UPDATE, System.currentTimeMillis())
            }
            reloadServers()
            if (!silent) {
                if (res != null && res.successCount > 0) toast("Серверы обновлены")
                else toast("Не удалось обновить. Проверьте интернет")
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
            val (count, subs) = withContext(Dispatchers.IO) {
                runCatching { AngConfigManager.importBatchConfig(text, "", false) }.getOrDefault(0 to 0)
            }
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

    private fun openUrl(url: String) {
        runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
    }

    // ---------- UI ----------

    @Composable
    private fun Root() {
        BackHandler(enabled = tab != Tab.HOME) { tab = if (tab == Tab.APPS) Tab.SETTINGS else Tab.HOME }
        LaunchedEffect(tab) { if (tab != Tab.APPS) applyAppsIfChanged() }
        Box(
            Modifier
                .fillMaxSize()
                .background(BgColor)
        ) {
            Box(
                Modifier
                    .size(460.dp)
                    .padding(0.dp)
                    .background(
                        Brush.radialGradient(
                            listOf(Mint.copy(alpha = if (running) 0.16f else 0.08f), Color.Transparent)
                        )
                    )
            )
            if (servers.isEmpty()) {
                Onboarding()
            } else {
                Column(
                    Modifier
                        .fillMaxSize()
                        .statusBarsPadding()
                        .navigationBarsPadding()
                ) {
                    Box(Modifier.weight(1f)) {
                        AnimatedContent(targetState = tab, transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(160)) }, label = "tab") { t ->
                            when (t) {
                                Tab.HOME -> Home(onPick = { sheetOpen = true })
                                Tab.SETTINGS -> Settings()
                                Tab.APPS -> AppsScreen()
                            }
                        }
                    }
                    BottomNav(if (tab == Tab.APPS) Tab.SETTINGS else tab) { tab = it }
                }
            }
            if (sheetOpen) ServerSheet(onDismiss = { sheetOpen = false })
            if (renewOpen) RenewSheet(onDismiss = { renewOpen = false })
            if (reportOpen) ReportSheet(onDismiss = { reportOpen = false })
            if (emailLoginOpen) EmailLoginSheet(onDismiss = { emailLoginOpen = false })
        }
    }

    @Composable
    private fun Onboarding() {
        LaunchedEffect(Unit) {
            while (true) { delay(1500); reloadServers() }
        }
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(Modifier.weight(0.8f))
            Image(painterResource(R.drawable.pamir_logo), null, Modifier.size(84.dp))
            Spacer(Modifier.height(22.dp))
            Text("Добро пожаловать\nв Pamir VPN", color = TextMain, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold, textAlign = TextAlign.Center, lineHeight = 28.sp)
            Spacer(Modifier.height(10.dp))
            Text("Подключите подписку — это займёт секунду", color = TextDim, fontSize = 13.sp, textAlign = TextAlign.Center)
            Spacer(Modifier.height(24.dp))
            Feature("⚡", "Подключение в одно касание")
            Feature("🌍", "Быстрые европейские серверы")
            Feature("📶", "Работает даже в «белых списках»")
            Spacer(Modifier.weight(1f))
            if (updating || loginBusy) CircularProgressIndicator(color = Mint, modifier = Modifier.size(28.dp))
            Spacer(Modifier.height(12.dp))
            if (loginBusy) {
                Text("Подтвердите вход в Telegram и вернитесь сюда", color = TextDim, fontSize = 12.sp, textAlign = TextAlign.Center)
                Spacer(Modifier.height(8.dp))
                SecondaryButton("Отменить") { cancelLogin() }
            } else {
                PrimaryButton2("✈  Войти через Telegram", "Подписка подключится сама") { loginTelegram() }
            }
            Spacer(Modifier.height(10.dp))
            SecondaryButton("Войти по почте и паролю") { emailLoginOpen = true }
            Spacer(Modifier.height(4.dp))
            Text(
                "Вставить ссылку подписки",
                color = TextDim, fontSize = 12.5.sp,
                modifier = Modifier.clickable { importFromClipboard() }.padding(10.dp)
            )
            Spacer(Modifier.height(10.dp))
            Spacer(Modifier.height(10.dp))
        }
    }

    @Composable
    private fun Feature(icon: String, text: String) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(14.dp))
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(icon, fontSize = 14.sp)
            Spacer(Modifier.width(10.dp))
            Text(text, color = TextMain, fontSize = 13.sp)
        }
    }

    @Composable
    private fun Header(title: String? = null) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (title == null) {
                Image(painterResource(R.drawable.pamir_logo), null, Modifier.size(24.dp))
                Spacer(Modifier.width(8.dp))
                Text("Pamir VPN", color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold)
            } else {
                Text(title, color = TextMain, fontSize = 19.sp, fontWeight = FontWeight.ExtraBold)
            }
        }
    }

    @Composable
    private fun Home(onPick: () -> Unit) {
        val current = servers.firstOrNull { it.guid == selected }
        val stubMode = servers.all { it.isStub }
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Header()
            StatusPill()
            if (newVersion != null) UpdateCard()
            if (stubMode) {
                StubCard()
                return@Column
            }
            Spacer(Modifier.height(26.dp))
            PowerButton()
            Spacer(Modifier.height(14.dp))
            val stateText = when {
                connecting -> "Подключение…"
                running -> "Защищено"
                else -> "Не подключено"
            }
            Text(stateText, color = if (running) Mint else TextMain, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.clickable { toggle() })
            Spacer(Modifier.height(4.dp))
            if (running) Timer() else Text("Нажмите, чтобы защитить соединение", color = TextDim, fontSize = 12.sp)
            Spacer(Modifier.height(20.dp))
            if (current != null) ServerCard(current, onPick)
            if (running) {
                SpeedCard()
            } else if (whitelist && current?.isLte != true) {
                WhitelistCard()
            } else if (current?.isLte != true && servers.any { it.isLte && !it.isStub }) {
                LteHint(onPick)
            }
            Spacer(Modifier.height(16.dp))
        }
    }

    @Composable
    private fun StatusPill() {
        val d = daysLeft
        val warn = d != null && d <= 3
        val amber = Color(0xFFF0B46A)
        Row(
            Modifier
                .padding(horizontal = 18.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(if (warn) Color(0xFF2A1F12) else Surface1)
                .border(1.dp, if (warn) amber.copy(alpha = 0.45f) else Line, RoundedCornerShape(16.dp))
                .clickable { openRenew() }
                .padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(if (warn) amber else Mint))
            Spacer(Modifier.width(10.dp))
            val txt = when {
                d == null -> "Подписка активна"
                d <= 0 -> "Подписка заканчивается сегодня"
                d == 1 -> "Подписка закончится завтра"
                warn -> "Осталось ${d} ${plural(d, "день", "дня", "дней")} — продлите"
                else -> "Активна · ещё ${d} ${plural(d, "день", "дня", "дней")}"
            }
            Text(txt, color = if (warn) Color(0xFFF5D3A6) else TextDim, fontSize = 12.sp, fontWeight = if (warn) FontWeight.SemiBold else FontWeight.Normal,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Text("Продлить ›", color = if (warn) amber else Mint, fontSize = 11.5.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun StubCard() {
        Column(
            Modifier
                .padding(18.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(Surface1)
                .border(1.dp, Danger.copy(alpha = 0.4f), RoundedCornerShape(20.dp))
                .padding(18.dp)
        ) {
            Text("Нет доступа к серверам", color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
            Spacer(Modifier.height(8.dp))
            servers.forEach {
                Text("${it.flag} ${it.name}".trim(), color = TextDim, fontSize = 13.sp, modifier = Modifier.padding(vertical = 2.dp))
            }
            Spacer(Modifier.height(14.dp))
            PrimaryButton("Открыть бота") { openUrl(BOT_URL) }
            Spacer(Modifier.height(8.dp))
            SecondaryButton(if (updating) "Обновляем…" else "Проверить снова") { updateSubscription() }
        }
    }

    @Composable
    private fun PowerButton() {
        val pulse = rememberInfiniteTransition(label = "pulse")
        val a by pulse.animateFloat(0.25f, 0.75f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "a")
        val ringAlpha = when {
            connecting -> a
            running -> 0.75f
            else -> 0.10f
        }
        Box(
            Modifier
                .size(148.dp)
                .clip(CircleShape)
                .clickable { toggle() },
            contentAlignment = Alignment.Center
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val r = size.minDimension / 2
                if (running || connecting) {
                    drawCircle(Brush.radialGradient(listOf(Mint.copy(alpha = 0.28f * ringAlpha + 0.05f), Color.Transparent), center, r), r)
                }
                val inner = r * 0.86f
                drawCircle(
                    Brush.radialGradient(
                        if (running) listOf(Color(0xFF1D5A4D), Color(0xFF0D2E28)) else listOf(Color(0xFF1B2A3F), Color(0xFF101A28)),
                        center = Offset(center.x, center.y - inner * 0.3f), radius = inner * 1.2f
                    ),
                    inner
                )
                drawCircle(
                    if (running || connecting) Mint.copy(alpha = ringAlpha) else Color.White.copy(alpha = 0.08f),
                    inner, style = Stroke(width = 2.dp.toPx())
                )
                val ic = if (running) Mint else Color(0xFF9FB0C3)
                val ir = inner * 0.30f
                drawArc(
                    ic, startAngle = -60f, sweepAngle = 300f, useCenter = false,
                    topLeft = Offset(center.x - ir, center.y - ir + ir * 0.12f),
                    size = androidx.compose.ui.geometry.Size(ir * 2, ir * 2),
                    style = Stroke(width = 5.dp.toPx(), cap = StrokeCap.Round)
                )
                drawLine(ic, Offset(center.x, center.y - ir * 1.15f), Offset(center.x, center.y - ir * 0.05f), strokeWidth = 5.dp.toPx(), cap = StrokeCap.Round)
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
        Text(if (ipInfo.isNotEmpty()) "$t · IP $ipInfo" else t, color = TextDim, fontSize = 12.sp)
    }

    @Composable
    private fun ServerCard(s: PServer, onPick: () -> Unit) {
        Row(
            Modifier
                .padding(horizontal = 18.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(18.dp))
                .clickable { onPick() }
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(s.flag, fontSize = 20.sp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(s.name, color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val p = pings[s.guid]
                val sub = when {
                    MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false) -> "Выбран автоматически"
                    s.isLte -> "Для мобильного интернета"
                    p != null && p > 0 -> "$p мс"
                    else -> "Нажмите, чтобы сменить"
                }
                Text(sub, color = TextDim, fontSize = 11.sp, maxLines = 1)
            }
            Text("Сменить ›", color = Mint, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun UpdateCard() {
        Row(
            Modifier
                .padding(start = 18.dp, end = 18.dp, top = 8.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(14.dp))
                .background(Mint.copy(alpha = 0.08f))
                .border(1.dp, Mint.copy(alpha = 0.35f), RoundedCornerShape(14.dp))
                .clickable { installUpdate() }
                .padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("⬆", color = Mint, fontSize = 13.sp)
            Spacer(Modifier.width(8.dp))
            Text("Доступна версия $newVersion", color = TextMain, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text(if (updProgress >= 0) "Загрузка $updProgress%" else "Обновить ›", color = Mint, fontSize = 11.5.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun WhitelistCard() {
        Column(
            Modifier
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(Color(0xFF2A1D14))
                .border(1.dp, Color(0x55F0B46A), RoundedCornerShape(16.dp))
                .padding(12.dp)
        ) {
            Text("📶  Похоже, включены «белые списки»", color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(3.dp))
            Text("Обычные серверы сейчас недоступны. LTE Обход работает и в этом режиме.", color = TextDim, fontSize = 11.5.sp)
            Spacer(Modifier.height(9.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(38.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Brush.linearGradient(listOf(Mint, MintDeep)))
                    .clickable {
                        lteServer()?.let { useLte(it); if (!running) toggle() else LauncherManager.restartService(this@PamirActivity) }
                    },
                contentAlignment = Alignment.Center
            ) { Text("Подключить LTE Обход", color = Color(0xFF05241D), fontSize = 13.sp, fontWeight = FontWeight.ExtraBold) }
        }
    }

    @Composable
    private fun LteHint(onPick: () -> Unit) {
        Row(
            Modifier
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(Mint.copy(alpha = 0.05f))
                .border(1.dp, Mint.copy(alpha = 0.3f), RoundedCornerShape(16.dp))
                .clickable { onPick() }
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("📶  Не работает мобильный интернет?", color = Color(0xFFBFEEE0), fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Text("LTE Обход ›", color = Mint, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun SpeedCard() {
        LaunchedEffect(running) { if (running) speedLoop() }
        Column(
            Modifier
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(18.dp))
        ) {
            Row(Modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                SpeedValue("↓", "Загрузка", rxSpeed, Mint, Modifier.weight(1f))
                Box(Modifier.width(1.dp).height(30.dp).background(Line))
                Spacer(Modifier.width(14.dp))
                SpeedValue("↑", "Отдача", txSpeed, Color(0xFF7FB8FF), Modifier.weight(1f))
            }
            Sparkline(
                speedHist,
                Modifier
                    .fillMaxWidth()
                    .height(34.dp)
                    .padding(top = 6.dp)
            )
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(Color(0x0DFFFFFF))
                    .padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("За сессию  ↓ ${fmtBytes(rxTotal)}  ↑ ${fmtBytes(txTotal)}", color = TextDim, fontSize = 11.sp, modifier = Modifier.weight(1f), maxLines = 1)
                Text(
                    if (MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) "РФ напрямую" else "Всё через VPN",
                    color = TextDim, fontSize = 11.sp, maxLines = 1
                )
            }
        }
    }

    @Composable
    private fun SpeedValue(arrow: String, label: String, bps: Long, color: Color, modifier: Modifier) {
        Column(modifier) {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(arrow, color = color, fontSize = 14.sp, fontWeight = FontWeight.ExtraBold)
                Spacer(Modifier.width(5.dp))
                Text(fmtBytes(bps) + "/с", color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, maxLines = 1)
            }
            Text(label, color = TextDim, fontSize = 10.5.sp)
        }
    }

    @Composable
    private fun Sparkline(values: List<Float>, modifier: Modifier) {
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
            drawPath(fill, Brush.verticalGradient(listOf(Mint.copy(alpha = 0.22f), Color.Transparent)))
            drawPath(line, Mint, style = Stroke(width = 1.6.dp.toPx(), cap = StrokeCap.Round))
        }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun ServerSheet(onDismiss: () -> Unit) {
        val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        LaunchedEffect(Unit) { if (pings.isEmpty()) runPing() }
        ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = Color(0xFF0F1926)) {
            Column(
                Modifier
                    .padding(horizontal = 16.dp)
                    .verticalScroll(rememberScrollState())
                    .navigationBarsPadding()
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Выбор сервера", color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                    Text(
                        if (pingBusy) "Проверяем…" else "↻ Проверить",
                        color = Mint, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.clickable { lifecycleScope.launch { runPing() } }.padding(8.dp)
                    )
                }
                Spacer(Modifier.height(8.dp))
                SheetItem("⚡", "Лучший автоматически", "авто", MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false), false) {
                    pickBest(); onDismiss()
                }
                val normal = servers.filter { !it.isLte && !it.isStub }
                val lte = servers.filter { it.isLte && !it.isStub }
                if (normal.isNotEmpty()) GroupLabel("Серверы")
                normal.forEach { s ->
                    SheetItem(s.flag, s.name, pingText(s), s.guid == selected && !MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false), true) {
                        selectServer(s.guid); onDismiss()
                    }
                }
                if (lte.isNotEmpty()) GroupLabel("Для мобильного интернета с ограничениями")
                lte.forEach { s ->
                    SheetItem(s.flag, s.name, "—", s.guid == selected, false) { selectServer(s.guid); onDismiss() }
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }

    private fun pingText(s: PServer): String {
        val p = pings[s.guid] ?: return if (pingBusy) "…" else ""
        return if (p > 0) "$p мс" else "нет связи"
    }

    @Composable
    private fun GroupLabel(text: String) {
        Text(
            text.uppercase(), color = TextDim, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold,
            letterSpacing = 1.sp, modifier = Modifier.padding(start = 4.dp, top = 14.dp, bottom = 7.dp)
        )
    }

    @Composable
    private fun SheetItem(flag: String, name: String, right: String, sel: Boolean, pingColored: Boolean, onClick: () -> Unit) {
        Row(
            Modifier
                .padding(vertical = 3.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(13.dp))
                .background(if (sel) Color(0xFF0F2A29) else Surface1)
                .border(1.dp, if (sel) Mint.copy(alpha = 0.6f) else Line, RoundedCornerShape(13.dp))
                .clickable { onClick() }
                .padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(flag, fontSize = 18.sp)
            Spacer(Modifier.width(12.dp))
            Text(name, color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            val rc = when {
                !pingColored -> TextDim
                right == "нет связи" -> Danger
                right.endsWith("мс") -> Mint
                else -> TextDim
            }
            Text(right, color = rc, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(10.dp))
            Box(
                Modifier
                    .size(16.dp)
                    .clip(CircleShape)
                    .border(2.dp, if (sel) Mint else Color(0xFF3A4A5E), CircleShape)
                    .padding(4.dp)
                    .clip(CircleShape)
                    .background(if (sel) Mint else Color.Transparent)
            )
        }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun RenewSheet(onDismiss: () -> Unit) {
        val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = Color(0xFF0F1926)) {
            Column(
                Modifier
                    .padding(horizontal = 16.dp)
                    .verticalScroll(rememberScrollState())
                    .navigationBarsPadding()
            ) {
                Text(if (renewKeys.isEmpty() && loggedIn && !renewLoading) "Оформить подписку" else "Продление подписки",
                    color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                Spacer(Modifier.height(10.dp))
                when {
                    payState == "paid" -> NoteCard("✅", "Оплата прошла", if (payBuy) "Подписка оформлена и уже подключается." else "Новый срок применён — VPN работает без перерыва.", Mint) {
                        PrimaryButton("Отлично") { payState = null; onDismiss() }
                    }
                    payState == "waiting" -> NoteCard("⏳", "Ожидаем оплату", "Оплатите в открывшемся окне и вернитесь сюда — срок обновится сам.", Color(0xFFF0B46A)) {
                        SecondaryButton("Открыть оплату ещё раз") { openUrl(payUrl) }
                        Spacer(Modifier.height(6.dp))
                        Text("Отменить", color = TextDim, fontSize = 12.sp, modifier = Modifier.align(Alignment.CenterHorizontally).clickable { payState = null; payJob?.cancel() }.padding(8.dp))
                    }
                    payState == "failed" -> NoteCard("⚠", "Оплата не прошла", "Деньги не списаны. Попробуйте ещё раз или выберите другой способ.", Danger) {
                        SecondaryButton("Выбрать тариф") { payState = null }
                    }
                    !loggedIn -> NoteCard("✈", "Войдите через Telegram", "Так вы сможете продлевать подписку прямо здесь — в пару касаний, через СБП, карту или с баланса.", Mint) {
                        if (loginBusy) {
                            Text("Подтвердите вход в Telegram и вернитесь сюда", color = TextDim, fontSize = 12.sp)
                            Spacer(Modifier.height(6.dp))
                            SecondaryButton("Отменить") { cancelLogin() }
                        } else PrimaryButton("Войти через Telegram") { loginTelegram() }
                        Spacer(Modifier.height(8.dp))
                        SecondaryButton("Войти по почте и паролю") { emailLoginOpen = true }
                        Spacer(Modifier.height(4.dp))
                        Text("Продлить в личном кабинете", color = TextDim, fontSize = 12.sp,
                            modifier = Modifier.align(Alignment.CenterHorizontally).clickable { openUrl(CABINET_URL) }.padding(8.dp))
                    }
                    renewLoading -> Box(Modifier.fillMaxWidth().padding(30.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Mint, modifier = Modifier.size(26.dp))
                    }
                    else -> RenewContent()
                }
                Spacer(Modifier.height(18.dp))
            }
        }
    }

    @Composable
    private fun ColumnScope.RenewContent() {
        if (renewKeys.size > 1) {
            GroupLabel("Ключ")
            renewKeys.forEach { k ->
                val id = k.optInt("id")
                SheetItem("🔑", k.optString("display_name").ifBlank { "Ключ #$id" }, keyExpiry(k), id == renewKeyId, false) { renewKeyId = id }
            }
        } else if (renewKeys.size == 1) {
            Text("${renewKeys[0].optString("display_name").ifBlank { "Ваш ключ" }} · ${keyExpiry(renewKeys[0])}", color = TextDim, fontSize = 12.sp)
        }
        val key = renewKeys.firstOrNull { it.optInt("id") == renewKeyId }
        val group = key?.optInt("tariff_group_id", 0) ?: 0
        val list = tariffs.filter { group == 0 || it.optInt("group_id", 0) == 0 || it.optInt("group_id") == group }.ifEmpty { tariffs }
        GroupLabel("Тариф")
        if (list.isEmpty()) {
            Text("Тарифы сейчас недоступны. Попробуйте позже или продлите в кабинете.", color = TextDim, fontSize = 12.sp)
            Spacer(Modifier.height(8.dp))
            SecondaryButton("Открыть кабинет") { openUrl(CABINET_URL) }
            return
        }
        list.forEach { t ->
            val id = t.optInt("id")
            val price = t.optLong("price_minor")
            val days = t.optInt("duration_days")
            Column(
                Modifier
                    .padding(vertical = 4.dp)
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(15.dp))
                    .background(Surface1)
                    .border(1.dp, Line, RoundedCornerShape(15.dp))
                    .padding(12.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t.optString("name"), color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        if (days > 0) Text("$days ${plural(days, "день", "дня", "дней")}", color = TextDim, fontSize = 11.sp)
                    }
                    Text(rub(price), color = Mint, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold)
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val busyQr = payBusy == "$id:yookassa_qr"
                    Box(
                        Modifier
                            .weight(1f)
                            .height(40.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(Brush.linearGradient(listOf(Mint, MintDeep)))
                            .clickable { pay(id, "yookassa_qr") },
                        contentAlignment = Alignment.Center
                    ) { Text(if (busyQr) "Создаём…" else "СБП / Карта", color = Color(0xFF05241D), fontSize = 13.sp, fontWeight = FontWeight.ExtraBold) }
                    val bal = balanceMinor
                    if (bal != null && bal >= price) {
                        Box(
                            Modifier
                                .weight(1f)
                                .height(40.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(Surface2)
                                .border(1.dp, Line, RoundedCornerShape(12.dp))
                                .clickable { pay(id, "balance") },
                            contentAlignment = Alignment.Center
                        ) { Text(if (payBusy == "$id:balance") "Оплачиваем…" else "С баланса", color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.Bold) }
                    }
                }
            }
        }
        balanceMinor?.let {
            Spacer(Modifier.height(6.dp))
            Text("На балансе: ${rub(it)}", color = TextDim, fontSize = 11.5.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }

    private fun keyExpiry(k: JSONObject): String {
        val raw = k.optString("expires_at")
        if (!k.optBoolean("is_active")) return "закончилась"
        if (raw.isBlank() || raw == "null") return "активна"
        val date = raw.take(10).split("-")
        return if (date.size == 3) "до ${date[2]}.${date[1]}.${date[0]}" else "активна"
    }

    @Composable
    private fun NoteCard(icon: String, title: String, text: String, accent: Color, actions: @Composable ColumnScope.() -> Unit) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Surface1)
                .border(1.dp, accent.copy(alpha = 0.35f), RoundedCornerShape(18.dp))
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(34.dp).clip(RoundedCornerShape(11.dp)).background(accent.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) {
                    Text(icon, color = accent, fontSize = 15.sp)
                }
                Spacer(Modifier.width(12.dp))
                Text(title, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
            }
            Spacer(Modifier.height(8.dp))
            Text(text, color = TextDim, fontSize = 12.5.sp, lineHeight = 17.sp)
            Spacer(Modifier.height(14.dp))
            actions()
        }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun ReportSheet(onDismiss: () -> Unit) {
        val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        var text by remember { mutableStateOf("") }
        var withLog by remember { mutableStateOf(true) }
        ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = Color(0xFF0F1926)) {
            Column(
                Modifier
                    .padding(horizontal = 16.dp)
                    .navigationBarsPadding()
                    .padding(bottom = 18.dp)
            ) {
                Text("Сообщить о проблеме", color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                Spacer(Modifier.height(4.dp))
                Text("Опишите, что случилось: что нажимали, какой сервер, мобильный интернет или Wi-Fi.", color = TextDim, fontSize = 12.sp, lineHeight = 16.sp)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = text, onValueChange = { if (it.length <= 1500) text = it },
                    modifier = Modifier.fillMaxWidth().height(130.dp),
                    placeholder = { Text("Например: не подключается Испания 1 на мобильном интернете", color = TextDim.copy(alpha = 0.7f), fontSize = 13.sp) },
                    textStyle = androidx.compose.ui.text.TextStyle(color = TextMain, fontSize = 14.sp),
                    shape = RoundedCornerShape(14.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Mint, unfocusedBorderColor = Color(0xFF2A3647),
                        cursorColor = Mint, focusedContainerColor = Surface1, unfocusedContainerColor = Surface1
                    )
                )
                Spacer(Modifier.height(4.dp))
                ToggleRow("📎", "Приложить журнал", "Технические записи — без паролей и ссылок", withLog) { withLog = it }
                Spacer(Modifier.height(8.dp))
                if (reportBusy) Box(Modifier.fillMaxWidth().height(48.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Mint, modifier = Modifier.size(24.dp))
                } else PrimaryButton("Отправить") {
                    if (text.isBlank()) toast("Опишите проблему хотя бы парой слов") else sendReport(text.trim(), withLog)
                }
                Spacer(Modifier.height(6.dp))
                Text("Если вы вошли через Telegram, мы сможем написать вам", color = TextDim, fontSize = 11.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
            }
        }
    }

    @Composable
    private fun AppsScreen() {
        val list = appList
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(bottom = 16.dp)
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("‹", color = TextMain, fontSize = 26.sp, modifier = Modifier.clip(CircleShape).clickable { tab = Tab.SETTINGS }.padding(horizontal = 12.dp, vertical = 2.dp))
                Text("Приложения без VPN", color = TextMain, fontSize = 19.sp, fontWeight = FontWeight.ExtraBold)
            }
            Text(
                "Некоторые банки и госсервисы не работают, когда включён VPN. Отметьте их — они будут ходить в интернет напрямую, а всё остальное останется защищённым.",
                color = TextDim, fontSize = 12.sp, lineHeight = 17.sp,
                modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = 6.dp)
            )
            when {
                list == null -> Box(Modifier.fillMaxWidth().padding(30.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Mint, modifier = Modifier.size(26.dp))
                }
                list.isEmpty() -> Column(
                    Modifier
                        .padding(16.dp)
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(Surface1)
                        .border(1.dp, Line, RoundedCornerShape(18.dp))
                        .padding(16.dp)
                ) {
                    Text("Популярных банков и сервисов не нашли", color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(4.dp))
                    Text("Нужное приложение можно выбрать из полного списка ниже.", color = TextDim, fontSize = 12.sp)
                }
                else -> {
                    val rec = list.filter { it.group == "Банки" || it.group == "Госуслуги и налоги" }.map { it.pkg }
                    if (rec.isNotEmpty() && rec.any { bypassSel[it] != true }) {
                        Box(
                            Modifier
                                .padding(horizontal = 16.dp, vertical = 6.dp)
                                .fillMaxWidth()
                                .height(40.dp)
                                .clip(RoundedCornerShape(13.dp))
                                .background(Mint.copy(alpha = 0.10f))
                                .border(1.dp, Mint.copy(alpha = 0.35f), RoundedCornerShape(13.dp))
                                .clickable { setBypass(rec, true) },
                            contentAlignment = Alignment.Center
                        ) { Text("Отметить все банки и Госуслуги", color = Mint, fontSize = 13.sp, fontWeight = FontWeight.Bold) }
                    }
                    list.groupBy { it.group }.forEach { (group, apps) ->
                        Section(group)
                        Group {
                            apps.forEach { a ->
                                val on = bypassSel[a.pkg] == true
                                Row(
                                    Modifier
                                        .fillMaxWidth()
                                        .clickable { setBypass(listOf(a.pkg), !on) }
                                        .padding(horizontal = 12.dp, vertical = 5.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    if (a.icon != null) Image(a.icon, null, Modifier.size(30.dp).clip(RoundedCornerShape(8.dp)))
                                    else RowIcon("▦")
                                    Spacer(Modifier.width(12.dp))
                                    Column(Modifier.weight(1f)) {
                                        Text(a.label, color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(if (on) "Напрямую, без VPN" else "Через VPN", color = if (on) Mint else TextDim, fontSize = 11.sp)
                                    }
                                    Switch(modifier = Modifier.scale(0.8f),
                                        checked = on, onCheckedChange = { setBypass(listOf(a.pkg), it) },
                                        colors = SwitchDefaults.colors(
                                            checkedTrackColor = MintDeep, checkedThumbColor = Color.White,
                                            uncheckedTrackColor = Color(0xFF2A3647), uncheckedThumbColor = Color(0xFFB8C4D2),
                                            uncheckedBorderColor = Color.Transparent
                                        )
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Section("Другие")
            Group {
                LinkRow("☰", "Все приложения", "Выбрать любое приложение из списка") {
                    appsChanged = true
                    startActivity(Intent(this@PamirActivity, PerAppProxyActivity::class.java))
                }
            }
        }
    }

    @Composable
    private fun Settings() {
        var ru by remember { mutableStateOf(MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) }
        var boot by remember { mutableStateOf(MmkvManager.decodeStartOnBoot()) }
        var smart by remember { mutableStateOf(smartLte()) }
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(bottom = 16.dp)
        ) {
            Header("Настройки")
            Section("Подключение")
            Group {
                ToggleRow("🇷🇺", "Сайты РФ напрямую", "Госуслуги, банки — без VPN", ru) { ru = it; setRuDirect(it) }
                ToggleRow("📶", "Умный LTE-режим", "Сам включит LTE Обход при «белых списках»", smart) {
                    smart = it; MmkvManager.encodeSettings(PREF_SMART_LTE, it)
                }
                ToggleRow("⟳", "Автоподключение", "При включении телефона", boot) { boot = it; MmkvManager.encodeStartOnBoot(it) }
                val bc = remember { bypassCount() }
                LinkRow("▦", "Приложения без VPN", if (bc > 0) "Без VPN: $bc ${plural(bc, "приложение", "приложения", "приложений")}" else "Банки, Госуслуги и др.") {
                    loadApps(); tab = Tab.APPS
                }
            }
            Section("Аккаунт")
            Group {
                if (loggedIn) {
                    LinkRow("✈", "Вы вошли в аккаунт", balanceMinor?.let { "Баланс: ${rub(it)} · продление в приложении" } ?: "Продление прямо в приложении") { openRenew() }
                    LinkRow("↩", "Выйти из аккаунта", "VPN продолжит работать") { logout(); toast("Вы вышли из аккаунта") }
                } else {
                    LinkRow("✈", if (loginBusy) "Ждём подтверждения…" else "Войти через Telegram", "Продление и оплата прямо в приложении") {
                        if (loginBusy) cancelLogin() else loginTelegram()
                    }
                    LinkRow("✉", "Войти по почте", "Если привязали почту в кабинете") { emailLoginOpen = true }
                }
            }
            Section("Подписка")
            Group {
                val upd = if (lastUpdate > 0) "Обновлено ${agoText(lastUpdate)}" else "Ещё не обновлялись"
                LinkRow("↻", if (updating) "Обновляем…" else "Обновить серверы", upd) { updateSubscription() }
                LinkRow("👤", "Личный кабинет", "Продление и устройства") { openUrl(CABINET_URL) }
            }
            Section("Помощь")
            Group {
                LinkRow("✈", "Поддержка", "Ответим в Telegram") { openUrl(BOT_URL) }
                LinkRow("🆘", "Сообщить о проблеме", "Отправим описание и журнал разработчикам") { reportOpen = true }
                LinkRow("ⓘ", "О приложении", if (newVersion != null) "Версия ${appVersion()} · доступна $newVersion" else "Версия ${appVersion()} · актуальная") {
                    if (newVersion != null) installUpdate() else { toast("Проверяем обновления…"); checkAppUpdate() }
                }
            }
            Spacer(Modifier.height(14.dp))
            Text(
                "Расширенные настройки",
                color = TextDim.copy(alpha = 0.7f), fontSize = 12.sp,
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .clickable { startActivity(Intent(this@PamirActivity, MainActivity::class.java)) }
                    .padding(10.dp)
            )
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

    @Composable
    private fun Section(text: String) {
        Text(
            text.uppercase(), color = TextDim, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.sp,
            modifier = Modifier.padding(start = 22.dp, top = 14.dp, bottom = 6.dp)
        )
    }

    @Composable
    private fun Group(content: @Composable () -> Unit) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(18.dp))
        ) { content() }
    }

    @Composable
    private fun RowIcon(icon: String) {
        Box(
            Modifier
                .size(28.dp)
                .clip(RoundedCornerShape(9.dp))
                .background(Mint.copy(alpha = 0.10f)),
            contentAlignment = Alignment.Center
        ) { Text(icon, color = Mint, fontSize = 13.sp) }
    }

    @Composable
    private fun ToggleRow(icon: String, title: String, sub: String, value: Boolean, onChange: (Boolean) -> Unit) {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable { onChange(!value) }
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            RowIcon(icon)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(sub, color = TextDim, fontSize = 11.sp)
            }
            Switch(modifier = Modifier.scale(0.8f),
                checked = value, onCheckedChange = onChange,
                colors = SwitchDefaults.colors(
                    checkedTrackColor = MintDeep, checkedThumbColor = Color.White,
                    uncheckedTrackColor = Color(0xFF2A3647), uncheckedThumbColor = Color(0xFFB8C4D2),
                    uncheckedBorderColor = Color.Transparent
                )
            )
        }
    }

    @Composable
    private fun LinkRow(icon: String, title: String, sub: String, onClick: () -> Unit) {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable { onClick() }
                .padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            RowIcon(icon)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(sub, color = TextDim, fontSize = 11.sp)
            }
            Text("›", color = TextDim, fontSize = 18.sp)
        }
    }

    @Composable
    private fun BottomNav(tab: Tab, onTab: (Tab) -> Unit) {
        Row(
            Modifier
                .padding(horizontal = 14.dp, vertical = 8.dp)
                .fillMaxWidth()
                .height(54.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(Surface2.copy(alpha = 0.95f))
                .border(1.dp, Line, RoundedCornerShape(18.dp)),
            verticalAlignment = Alignment.CenterVertically
        ) {
            NavItem(R.drawable.ic_lock_24dp, "VPN", tab == Tab.HOME, Modifier.weight(1f)) { onTab(Tab.HOME) }
            NavItem(R.drawable.ic_subscriptions_24dp, "Кабинет", false, Modifier.weight(1f)) { openUrl(CABINET_URL) }
            NavItem(R.drawable.ic_settings_24dp, "Настройки", tab == Tab.SETTINGS, Modifier.weight(1f)) { onTab(Tab.SETTINGS) }
        }
    }

    @Composable
    private fun NavItem(icon: Int, label: String, active: Boolean, modifier: Modifier, onClick: () -> Unit) {
        Column(
            modifier
                .fillMaxSize()
                .clickable { onClick() },
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            val c = if (active) Mint else TextDim
            Image(painterResource(icon), null, Modifier.size(19.dp), colorFilter = ColorFilter.tint(c))
            Spacer(Modifier.height(2.dp))
            Text(label, color = c, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
        }
    }

    @Composable
    private fun PrimaryButton(text: String, onClick: () -> Unit) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(48.dp)
                .clip(RoundedCornerShape(15.dp))
                .background(Brush.linearGradient(listOf(Mint, MintDeep)))
                .clickable { onClick() },
            contentAlignment = Alignment.Center
        ) { Text(text, color = Color(0xFF05241D), fontSize = 15.sp, fontWeight = FontWeight.ExtraBold) }
    }

    @Composable
    private fun PrimaryButton2(title: String, subtitle: String, onClick: () -> Unit) {
        Column(
            Modifier
                .fillMaxWidth()
                .height(56.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Brush.linearGradient(listOf(Mint, MintDeep)))
                .clickable { onClick() },
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(title, color = Color(0xFF05241D), fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
            Text(subtitle, color = Color(0xFF05241D).copy(alpha = 0.72f), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun EmailLoginSheet(onDismiss: () -> Unit) {
        val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        var email by remember { mutableStateOf("") }
        var pass by remember { mutableStateOf("") }
        val fieldColors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Mint, unfocusedBorderColor = Color(0xFF2A3647), cursorColor = Mint,
            focusedContainerColor = Surface1, unfocusedContainerColor = Surface1,
            focusedTextColor = TextMain, unfocusedTextColor = TextMain
        )
        ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = Color(0xFF0F1926)) {
            Column(
                Modifier
                    .padding(horizontal = 16.dp)
                    .navigationBarsPadding()
                    .padding(bottom = 18.dp)
            ) {
                Text("Вход по почте", color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                Spacer(Modifier.height(4.dp))
                Text("Почта и пароль от личного кабинета Pamir VPN", color = TextDim, fontSize = 12.sp)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = email, onValueChange = { email = it.trim() }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Почта", color = TextDim.copy(alpha = 0.7f), fontSize = 14.sp) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                    shape = RoundedCornerShape(14.dp), colors = fieldColors
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = pass, onValueChange = { pass = it }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Пароль", color = TextDim.copy(alpha = 0.7f), fontSize = 14.sp) },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    shape = RoundedCornerShape(14.dp), colors = fieldColors
                )
                Spacer(Modifier.height(14.dp))
                if (emailBusy) Box(Modifier.fillMaxWidth().height(48.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Mint, modifier = Modifier.size(24.dp))
                } else PrimaryButton("Войти") { loginEmail(email, pass) }
                Spacer(Modifier.height(4.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Забыли пароль?", color = Mint, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.clickable { forgotPassword(email) }.padding(vertical = 10.dp, horizontal = 4.dp))
                    Text("Регистрация", color = TextDim, fontSize = 12.5.sp,
                        modifier = Modifier.clickable { openUrl(CABINET_URL) }.padding(vertical = 10.dp, horizontal = 4.dp))
                }
            }
        }
    }

    @Composable
    private fun SecondaryButton(text: String, onClick: () -> Unit) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(46.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(16.dp))
                .clickable { onClick() },
            contentAlignment = Alignment.Center
        ) { Text(text, color = Color(0xFFD8E2EA), fontSize = 13.5.sp, fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun PamirTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Mint, onPrimary = Color(0xFF05241D), background = BgColor, surface = BgColor,
            onBackground = TextMain, onSurface = TextMain, surfaceVariant = Surface1
        ),
        content = content
    )
}
