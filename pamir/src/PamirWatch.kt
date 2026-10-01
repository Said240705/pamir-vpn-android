package com.v2ray.ang.pamir

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.TrafficStats
import android.os.Build
import android.os.PowerManager
import android.os.Process
import android.util.Log
import androidx.core.app.NotificationCompat
import com.v2ray.ang.AppConfig
import com.v2ray.ang.R
import com.v2ray.ang.core.CoreServiceManager
import com.v2ray.ang.dto.entities.ProfileItem
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.helper.MessageHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Pamir background logic that lives next to the VPN core (":daemon" process):
 *  - remembers when the connection started and the traffic counters at that moment;
 *  - shows a notification when the VPN drops without the user pressing "stop";
 *  - watchdog: while the screen is on, checks that traffic really goes through the server;
 *    if it does not, switches to "LTE Обход" (smart LTE) or tells the user.
 * Also holds helpers shared with the UI (server names, LTE detection).
 */
object PamirWatch {
    const val EXTRA_RECONNECT = "pamir_reconnect"
    const val EXTRA_SERVERS = "pamir_servers"
    const val EXTRA_RENEW = "pamir_renew"

    const val K_CONN_AT = "pamir_conn_at"
    const val K_BASE_RX = "pamir_base_rx"
    const val K_BASE_TX = "pamir_base_tx"
    const val K_ALERTS = "pamir_drop_alerts"
    const val K_SMART_LTE = "pamir_smart_lte"
    const val K_AUTO_LTE_ACTIVE = "pamir_auto_lte_active"
    const val K_PREFERRED = "pamir_preferred"
    const val K_REMIND = "pamir_remind"
    private const val K_REMIND_LAST = "pamir_remind_last"
    private const val K_USER_STOP = "pamir_user_stop"

    private const val CHANNEL = "pamir_status"
    const val ALERT_ID = 7311
    const val REMIND_ID = 7312
    private const val TAG = "Pamir"

    private var job: Job? = null

    // ---------- shared helpers ----------

    fun cleanName(remarks: String): Pair<String, String> {
        var s = remarks.substringBefore("|").trim()
        s = s.replace(Regex("-?\\s*user_[^\\s|]*"), "")
        val flagMatch = Regex("^([\\x{1F1E6}-\\x{1F1FF}]{2})").find(s)
        val flag = flagMatch?.value ?: "🌐"
        if (flagMatch != null) s = s.removePrefix(flagMatch.value)
        s = s.replace(Regex("\\s*-\\s*(\\d+)"), " $1").replace(Regex("\\s{2,}"), " ").trim().trim('-').trim()
        if (s.isEmpty()) s = "Сервер"
        return flag to s
    }

    /** "🇪🇸 Испания 1" for notifications, tile and widget. */
    fun title(remarks: String?): String {
        if (remarks.isNullOrBlank()) return "Pamir VPN"
        val (flag, name) = cleanName(remarks)
        return "$flag $name"
    }

    fun isLte(p: ProfileItem): Boolean =
        cleanName(p.remarks).second.contains("LTE", true) || p.network == "xhttp"

    fun isStub(p: ProfileItem): Boolean {
        val h = p.server.orEmpty()
        return h.startsWith("127.") || h == "localhost"
    }

    fun selectedTitle(): String =
        MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it) }?.let { title(it.remarks) } ?: "Pamir VPN"

    /** Called by every "stop"/"restart" request, so the following stop is not treated as a drop. */
    fun markUserStop() {
        MmkvManager.encodeSettings(K_USER_STOP, System.currentTimeMillis())
    }

    // ---------- core lifecycle hooks (daemon process) ----------

    fun onStarted(ctx: Context) {
        runCatching {
            val uid = Process.myUid()
            MmkvManager.encodeSettings(K_CONN_AT, System.currentTimeMillis())
            MmkvManager.encodeSettings(K_BASE_RX, TrafficStats.getUidRxBytes(uid))
            MmkvManager.encodeSettings(K_BASE_TX, TrafficStats.getUidTxBytes(uid))
            cancelAlert(ctx)
            startWatchdog(ctx.applicationContext)
        }.onFailure { Log.w(TAG, "onStarted: ${it.message}") }
    }

    fun onStopped(ctx: Context) {
        runCatching {
            job?.cancel()
            job = null
            MmkvManager.encodeSettings(K_CONN_AT, 0L)
            val byUser = System.currentTimeMillis() - MmkvManager.decodeSettingsLong(K_USER_STOP, 0L) < 15_000
            Log.w(TAG, "core stopped, byUser=$byUser")
            if (!byUser && alertsOn()) {
                notify(
                    ctx, "Pamir VPN отключился",
                    "Соединение прервано. Нажмите, чтобы подключиться снова",
                    EXTRA_RECONNECT, "Подключить"
                )
            }
        }.onFailure { Log.w(TAG, "onStopped: ${it.message}") }
    }

    private fun alertsOn() = true // always on

    private fun startWatchdog(ctx: Context) {
        job?.cancel()
        job = CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            var fails = 0
            var alerted = false
            delay(25_000)
            while (isActive) {
                if (screenOn(ctx) && hasUnderlyingNetwork(ctx)) {
                    val t = CoreServiceManager.pamirProbe()
                    when {
                        t == -2L -> Unit // core is reloading or not running
                        t >= 0 -> {
                            fails = 0
                            if (alerted) { cancelAlert(ctx); alerted = false }
                        }
                        else -> {
                            fails++
                            Log.w(TAG, "watchdog: no response ($fails)")
                            if (fails >= 2 && !alerted) {
                                alerted = true
                                if (switchToLte(ctx)) return@launch
                                if (alertsOn()) {
                                    notify(
                                        ctx, "Нет связи через ${selectedTitle()}",
                                        "Сервер не отвечает из вашей сети. Нажмите, чтобы выбрать другой",
                                        EXTRA_SERVERS, "Сменить сервер"
                                    )
                                }
                            }
                        }
                    }
                }
                delay(if (fails > 0) 20_000 else 60_000)
            }
        }
    }

    /** Smart LTE in background: regular server is dead -> switch to "LTE Обход" once. */
    private fun switchToLte(ctx: Context): Boolean {
        if (!MmkvManager.decodeSettingsBool(K_SMART_LTE, true)) return false
        val cur = MmkvManager.getSelectServer() ?: return false
        val curP = MmkvManager.decodeServerConfig(cur) ?: return false
        if (isLte(curP)) return false
        val lte = MmkvManager.decodeAllServerList().firstOrNull { g ->
            MmkvManager.decodeServerConfig(g)?.let { isLte(it) && !isStub(it) } == true
        } ?: return false
        Log.w(TAG, "watchdog: switching to LTE")
        MmkvManager.encodeSettings(K_PREFERRED, cur)
        MmkvManager.encodeSettings(K_AUTO_LTE_ACTIVE, true)
        MmkvManager.setSelectServer(lte)
        markUserStop()
        MessageHelper.sendMsg2Service(ctx, AppConfig.MSG_STATE_RESTART, "")
        if (alertsOn()) {
            notify(
                ctx, "Включили LTE Обход",
                "Обычные серверы не отвечают в вашей сети — переключились на обход «белых списков»",
                EXTRA_SERVERS, null
            )
        }
        return true
    }

    private fun screenOn(ctx: Context): Boolean =
        (ctx.getSystemService(Context.POWER_SERVICE) as? PowerManager)?.isInteractive ?: true

    /** True when the phone itself has Wi-Fi / mobile internet (so "no answer" is the server's fault). */
    @Suppress("DEPRECATION")
    private fun hasUnderlyingNetwork(ctx: Context): Boolean {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return true
        return runCatching {
            cm.allNetworks.any { n ->
                val c = cm.getNetworkCapabilities(n) ?: return@any false
                !c.hasTransport(NetworkCapabilities.TRANSPORT_VPN) &&
                    c.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                    (c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
                        c.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) ||
                        c.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))
            }
        }.getOrDefault(true)
    }

    // ---------- subscription expiry ----------

    /** Days left from the server names ("…|⏳3D"), null = unknown / unlimited. */
    fun daysLeft(): Int? = MmkvManager.decodeAllServerList().asSequence()
        .mapNotNull { MmkvManager.decodeServerConfig(it)?.remarks }
        .mapNotNull { Regex("⏳\\s*(\\d+)\\s*D").find(it)?.groupValues?.get(1)?.toIntOrNull() }
        .firstOrNull()

    /** Reminder 3 days, 1 day and on the last day. Called by [PamirReminderWorker] twice a day. */
    fun checkExpiry(ctx: Context) {
        val d = daysLeft() ?: return
        if (d !in setOf(0, 1, 3)) return
        val key = "${System.currentTimeMillis() / 86_400_000L}:$d"
        if (MmkvManager.decodeSettingsString(K_REMIND_LAST, "") == key) return
        MmkvManager.encodeSettings(K_REMIND_LAST, key)
        val title = when (d) {
            0 -> "Подписка заканчивается сегодня"
            1 -> "Подписка закончится завтра"
            else -> "Подписка закончится через 3 дня"
        }
        Log.w(TAG, "expiry reminder d=$d")
        notify(ctx, title, "Продлите заранее, чтобы VPN не отключился в неподходящий момент", EXTRA_RENEW, "Продлить", REMIND_ID)
    }

    // ---------- notifications ----------

    fun cancelAlert(ctx: Context) {
        runCatching { (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).cancel(ALERT_ID) }
    }

    private fun notify(ctx: Context, title: String, text: String, extra: String, action: String?, id: Int = ALERT_ID) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Состояние подключения", NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = "Обрыв VPN и проблемы с сервером"
                }
            )
        }
        val open = Intent(ctx, PamirActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(extra, true)
        val pi = PendingIntent.getActivity(
            ctx, extra.hashCode(), open,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val b = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_name)
            .setColor(0xFF2BEFC0.toInt())
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pi)
        if (action != null) b.addAction(0, action, pi)
        runCatching { nm.notify(id, b.build()) }
    }
}
