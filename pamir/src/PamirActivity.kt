package com.v2ray.ang.pamir

import android.content.BroadcastReceiver
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
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
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
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

private enum class Tab { HOME, SETTINGS }

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

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            if (it.resultCode == RESULT_OK) startVpn() else connecting = false
        }

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
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
        initRouting()
        reloadServers()
        setContent { PamirTheme { Root() } }
        if (servers.isNotEmpty() && System.currentTimeMillis() - lastUpdate > 60 * 60 * 1000L) {
            updateSubscription(silent = true)
        }
    }

    override fun onResume() {
        super.onResume()
        reloadServers()
        MessageHelper.sendMsg2Service(this, AppConfig.MSG_REGISTER_CLIENT, "")
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
            connectedAt = System.currentTimeMillis()
            fetchIp()
        }
        if (!value) {
            connectedAt = 0L
            ipInfo = ""
        }
        running = value
    }

    private fun initRouting() {
        if (!MmkvManager.decodeSettingsBool(PREF_ROUTING_INIT, false)) {
            runCatching { SettingsManager.resetRoutingRulesetsFromPresets(this, RoutingType.WHITE_RUSSIA) }
            MmkvManager.encodeSettings(PREF_RU_DIRECT, true)
            MmkvManager.encodeSettings(PREF_ROUTING_INIT, true)
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
        var sel = MmkvManager.getSelectServer()
        if (sel == null || list.none { it.guid == sel }) {
            sel = list.firstOrNull { !it.isStub && !it.isLte }?.guid ?: list.firstOrNull()?.guid
            sel?.let { MmkvManager.setSelectServer(it) }
        }
        selected = sel
    }

    private fun cleanName(remarks: String): Pair<String, String> {
        var s = remarks.substringBefore("|").trim()
        s = s.replace(Regex("-?\\s*user_[^\\s|]*"), "")
        val flagMatch = Regex("^([\\x{1F1E6}-\\x{1F1FF}]{2})").find(s)
        val flag = flagMatch?.value ?: "🌐"
        if (flagMatch != null) s = s.removePrefix(flagMatch.value)
        s = s.replace(Regex("\\s*-\\s*(\\d+)"), " $1").replace(Regex("\\s{2,}"), " ").trim().trim('-').trim()
        if (s.isEmpty()) s = "Сервер"
        return flag to s
    }

    private fun toggle() {
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
        connecting = true
        val intent = VpnService.prepare(this)
        if (intent == null) startVpn() else vpnPermission.launch(intent)
    }

    private fun startVpn() {
        val sel = selected ?: return
        LauncherManager.startService(this, sel)
        lifecycleScope.launch {
            delay(12000)
            if (connecting) connecting = false
        }
    }

    private fun selectServer(guid: String) {
        selected = guid
        MmkvManager.setSelectServer(guid)
        MmkvManager.encodeSettings(PREF_AUTO_BEST, false)
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
            delay(1500)
            val text = withContext(Dispatchers.IO) {
                runCatching {
                    val c = URL("https://api.ipify.org").openConnection() as HttpURLConnection
                    c.connectTimeout = 6000; c.readTimeout = 6000
                    c.inputStream.bufferedReader().use { it.readText().trim() }
                }.getOrDefault("")
            }
            if (running) ipInfo = text
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
        var tab by remember { mutableStateOf(Tab.HOME) }
        var sheet by remember { mutableStateOf(false) }
        BackHandler(enabled = tab != Tab.HOME) { tab = Tab.HOME }
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
                                Tab.HOME -> Home(onPick = { sheet = true })
                                Tab.SETTINGS -> Settings()
                            }
                        }
                    }
                    BottomNav(tab) { tab = it }
                }
            }
            if (sheet) ServerSheet(onDismiss = { sheet = false })
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
            Image(painterResource(R.drawable.pamir_logo), null, Modifier.size(104.dp))
            Spacer(Modifier.height(22.dp))
            Text("Добро пожаловать\nв Pamir VPN", color = TextMain, fontSize = 27.sp, fontWeight = FontWeight.ExtraBold, textAlign = TextAlign.Center, lineHeight = 33.sp)
            Spacer(Modifier.height(10.dp))
            Text("Подключите подписку — это займёт секунду", color = TextDim, fontSize = 14.sp, textAlign = TextAlign.Center)
            Spacer(Modifier.height(24.dp))
            Feature("⚡", "Подключение в одно касание")
            Feature("🌍", "Быстрые европейские серверы")
            Feature("📶", "Работает даже в «белых списках»")
            Spacer(Modifier.weight(1f))
            if (updating) CircularProgressIndicator(color = Mint, modifier = Modifier.size(28.dp))
            Spacer(Modifier.height(12.dp))
            PrimaryButton("Войти через кабинет") { openUrl(CABINET_URL) }
            Spacer(Modifier.height(10.dp))
            SecondaryButton("Вставить ссылку подписки") { importFromClipboard() }
            Spacer(Modifier.height(10.dp))
            Text(
                "Нет подписки? Оформите её в боте @pamirlink_bot",
                color = TextDim, fontSize = 12.sp, textAlign = TextAlign.Center,
                modifier = Modifier.clickable { openUrl(BOT_URL) }.padding(8.dp)
            )
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
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(icon, fontSize = 16.sp)
            Spacer(Modifier.width(10.dp))
            Text(text, color = TextMain, fontSize = 14.sp)
        }
    }

    @Composable
    private fun Header(title: String? = null) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (title == null) {
                Image(painterResource(R.drawable.pamir_logo), null, Modifier.size(30.dp))
                Spacer(Modifier.width(8.dp))
                Text("Pamir VPN", color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
            } else {
                Text(title, color = TextMain, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
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
            if (stubMode) {
                StubCard()
                return@Column
            }
            Spacer(Modifier.height(30.dp))
            PowerButton()
            Spacer(Modifier.height(20.dp))
            val stateText = when {
                connecting -> "Подключение…"
                running -> "Защищено"
                else -> "Не подключено"
            }
            Text(stateText, color = if (running) Mint else TextMain, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.clickable { toggle() })
            Spacer(Modifier.height(4.dp))
            if (running) Timer() else Text("Нажмите, чтобы защитить соединение", color = TextDim, fontSize = 13.sp)
            Spacer(Modifier.height(22.dp))
            if (current != null) ServerCard(current, onPick)
            if (running) {
                InfoRow()
            } else if (current?.isLte != true && servers.any { it.isLte && !it.isStub }) {
                LteHint(onPick)
            }
            Spacer(Modifier.height(16.dp))
        }
    }

    @Composable
    private fun StatusPill() {
        val d = daysLeft
        Row(
            Modifier
                .padding(horizontal = 18.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(16.dp))
                .clickable { openUrl(CABINET_URL) }
                .padding(horizontal = 14.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(if (d == null || d > 0) Mint else Danger))
            Spacer(Modifier.width(10.dp))
            val txt = when {
                d == null -> "Подписка активна"
                d <= 0 -> "Подписка истекает сегодня"
                else -> "Подписка активна · ещё ${d} ${plural(d, "день", "дня", "дней")}"
            }
            Text(txt, color = TextDim, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text("Продлить ›", color = Mint, fontSize = 12.sp, fontWeight = FontWeight.Bold)
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
                .size(196.dp)
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
                    inner, style = Stroke(width = 3.dp.toPx())
                )
                val ic = if (running) Mint else Color(0xFF9FB0C3)
                val ir = inner * 0.30f
                drawArc(
                    ic, startAngle = -60f, sweepAngle = 300f, useCenter = false,
                    topLeft = Offset(center.x - ir, center.y - ir + ir * 0.12f),
                    size = androidx.compose.ui.geometry.Size(ir * 2, ir * 2),
                    style = Stroke(width = 7.dp.toPx(), cap = StrokeCap.Round)
                )
                drawLine(ic, Offset(center.x, center.y - ir * 1.15f), Offset(center.x, center.y - ir * 0.05f), strokeWidth = 7.dp.toPx(), cap = StrokeCap.Round)
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
        Text(if (ipInfo.isNotEmpty()) "$t · IP $ipInfo" else t, color = TextDim, fontSize = 13.sp)
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
                .padding(horizontal = 14.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(s.flag, fontSize = 26.sp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(s.name, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val p = pings[s.guid]
                val sub = when {
                    MmkvManager.decodeSettingsBool(PREF_AUTO_BEST, false) -> "Выбран автоматически"
                    s.isLte -> "Для мобильного интернета"
                    p != null && p > 0 -> "$p мс"
                    else -> "Нажмите, чтобы сменить"
                }
                Text(sub, color = TextDim, fontSize = 12.sp)
            }
            Text("Сменить ›", color = Mint, fontSize = 13.sp, fontWeight = FontWeight.Bold)
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
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("📶  Не работает мобильный интернет?", color = Color(0xFFBFEEE0), fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text("LTE Обход ›", color = Mint, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun InfoRow() {
        Row(
            Modifier
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            InfoBox("Статус", "Трафик защищён", Modifier.weight(1f))
            InfoBox("Сайты РФ", if (MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) "Напрямую" else "Через VPN", Modifier.weight(1f))
        }
    }

    @Composable
    private fun InfoBox(label: String, value: String, modifier: Modifier) {
        Column(
            modifier
                .clip(RoundedCornerShape(16.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(16.dp))
                .padding(12.dp)
        ) {
            Text(value, color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Text(label, color = TextDim, fontSize = 11.sp)
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
                    Text("Выбор сервера", color = TextMain, fontSize = 19.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
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
                .padding(vertical = 4.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(15.dp))
                .background(if (sel) Color(0xFF0F2A29) else Surface1)
                .border(1.dp, if (sel) Mint.copy(alpha = 0.6f) else Line, RoundedCornerShape(15.dp))
                .clickable { onClick() }
                .padding(horizontal = 13.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(flag, fontSize = 22.sp)
            Spacer(Modifier.width(12.dp))
            Text(name, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            val rc = when {
                !pingColored -> TextDim
                right == "нет связи" -> Danger
                right.endsWith("мс") -> Mint
                else -> TextDim
            }
            Text(right, color = rc, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(10.dp))
            Box(
                Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .border(2.dp, if (sel) Mint else Color(0xFF3A4A5E), CircleShape)
                    .padding(4.dp)
                    .clip(CircleShape)
                    .background(if (sel) Mint else Color.Transparent)
            )
        }
    }

    @Composable
    private fun Settings() {
        var ru by remember { mutableStateOf(MmkvManager.decodeSettingsBool(PREF_RU_DIRECT, true)) }
        var boot by remember { mutableStateOf(MmkvManager.decodeStartOnBoot()) }
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
                ToggleRow("⟳", "Автоподключение", "При включении телефона", boot) { boot = it; MmkvManager.encodeStartOnBoot(it) }
                LinkRow("▦", "Приложения без VPN", "Выбрать исключения") {
                    startActivity(Intent(this@PamirActivity, PerAppProxyActivity::class.java))
                }
            }
            Section("Подписка")
            Group {
                val ago = if (lastUpdate > 0) agoText(lastUpdate) else "ещё не обновлялись"
                LinkRow("↻", if (updating) "Обновляем…" else "Обновить серверы", "Обновлено $ago") { updateSubscription() }
                LinkRow("👤", "Личный кабинет", "Продление и устройства") { openUrl(CABINET_URL) }
            }
            Section("Помощь")
            Group {
                LinkRow("✈", "Поддержка", "Ответим в Telegram") { openUrl(BOT_URL) }
                LinkRow("ⓘ", "О приложении", "Версия ${appVersion()}") { toast("Pamir VPN ${appVersion()}") }
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
            modifier = Modifier.padding(start = 22.dp, top = 16.dp, bottom = 7.dp)
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
                .size(32.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Mint.copy(alpha = 0.10f)),
            contentAlignment = Alignment.Center
        ) { Text(icon, color = Mint, fontSize = 15.sp) }
    }

    @Composable
    private fun ToggleRow(icon: String, title: String, sub: String, value: Boolean, onChange: (Boolean) -> Unit) {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable { onChange(!value) }
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            RowIcon(icon)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                Text(sub, color = TextDim, fontSize = 11.5.sp)
            }
            Switch(
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
                .padding(horizontal = 14.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            RowIcon(icon)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                Text(sub, color = TextDim, fontSize = 11.5.sp)
            }
            Text("›", color = TextDim, fontSize = 18.sp)
        }
    }

    @Composable
    private fun BottomNav(tab: Tab, onTab: (Tab) -> Unit) {
        Row(
            Modifier
                .padding(horizontal = 14.dp, vertical = 10.dp)
                .fillMaxWidth()
                .height(62.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Surface2.copy(alpha = 0.95f))
                .border(1.dp, Line, RoundedCornerShape(22.dp)),
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
            Image(painterResource(icon), null, Modifier.size(21.dp), colorFilter = ColorFilter.tint(c))
            Spacer(Modifier.height(3.dp))
            Text(label, color = c, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
    }

    @Composable
    private fun PrimaryButton(text: String, onClick: () -> Unit) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(54.dp)
                .clip(RoundedCornerShape(17.dp))
                .background(Brush.linearGradient(listOf(Mint, MintDeep)))
                .clickable { onClick() },
            contentAlignment = Alignment.Center
        ) { Text(text, color = Color(0xFF05241D), fontSize = 16.sp, fontWeight = FontWeight.ExtraBold) }
    }

    @Composable
    private fun SecondaryButton(text: String, onClick: () -> Unit) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(50.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Surface1)
                .border(1.dp, Line, RoundedCornerShape(16.dp))
                .clickable { onClick() },
            contentAlignment = Alignment.Center
        ) { Text(text, color = Color(0xFFD8E2EA), fontSize = 14.sp, fontWeight = FontWeight.Bold) }
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
