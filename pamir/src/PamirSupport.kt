package com.v2ray.ang.pamir

import android.app.NotificationManager
import android.content.Context
import android.text.Html
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkerParameters
import androidx.work.multiprocess.RemoteWorkManager
import com.v2ray.ang.handler.MmkvManager
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Support tickets (GET /topup/support/messages): one open ticket per user, numbered by the server.
 * While a ticket is open, [PamirSupportWorker] checks it every 15 minutes and notifies
 * «Поддержка ответила» on a new admin message and «Обращение №N закрыто» when it gets closed.
 */
object PamirSupport {
    const val EXTRA_SUPPORT = "pamir_support"
    private const val K_THREAD = "pamir_support_thread"   // open ticket being watched, 0 — none
    private const val K_SEEN = "pamir_support_seen"       // "thread:lastAdminMessageId" already shown or notified
    private const val NOTIFY_ID = 7316

    data class State(val threadId: Int, val status: String?, val messages: List<JSONObject>) {
        val open get() = status == "open"
        val lastAdminId get() = messages.filter { it.optString("sender_type") == "admin" }.maxOfOrNull { it.optInt("id") } ?: 0
    }

    fun parse(j: JSONObject): State = State(
        j.optInt("thread_id"),
        j.optString("thread_status").takeIf { it.isNotEmpty() && it != "null" },
        j.optJSONArray("messages")?.let { a -> (0 until a.length()).map { a.getJSONObject(it) } }.orEmpty()
    )

    /** Blocking: the current ticket, or null (not signed in or no connection). */
    fun fetch(proxyPort: Int? = null): State? {
        if (PamirApi.token == null) return null
        return runCatching { parse(PamirApi.call("/topup/support/messages", proxyPort = proxyPort)) }
            .onFailure { Log.w("Pamir", "support: ${it.message}") }.getOrNull()
    }

    private fun seen(threadId: Int): Int? {
        val v = MmkvManager.decodeSettingsString(K_SEEN, "").orEmpty().split(":")
        return if (v.size == 2 && v[0].toIntOrNull() == threadId) v[1].toIntOrNull() else null
    }

    private fun setSeen(threadId: Int, adminId: Int) = MmkvManager.encodeSettings(K_SEEN, "$threadId:$adminId")

    /** True when the open ticket has an answer the user has not opened yet. */
    fun unread(s: State): Boolean = s.open && s.lastAdminId > (seen(s.threadId) ?: s.lastAdminId)

    /**
     * App side: remember the ticket so the worker follows it. [viewed] — the chat is on screen, so its
     * answers count as read and their notification is removed.
     */
    fun track(ctx: Context, s: State, viewed: Boolean) {
        if (s.open && s.threadId > 0) {
            if (viewed || seen(s.threadId) == null) setSeen(s.threadId, s.lastAdminId)
            if (MmkvManager.decodeSettingsInt(K_THREAD, 0) != s.threadId) {
                MmkvManager.encodeSettings(K_THREAD, s.threadId)
                PamirSupportWorker.schedule(ctx)
            }
        } else {
            stopWatching(ctx)
        }
        if (viewed) cancelNotification(ctx)
    }

    /** The user closed the ticket in the app — nothing to notify about. */
    fun stopWatching(ctx: Context) {
        if (MmkvManager.decodeSettingsInt(K_THREAD, 0) == 0) return
        MmkvManager.encodeSettings(K_THREAD, 0)
        PamirSupportWorker.cancel(ctx)
    }

    fun cancelNotification(ctx: Context) {
        runCatching { (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).cancel(NOTIFY_ID) }
    }

    /** Worker: notify about a new answer or the closing of the watched ticket. Returns false when nothing is left to watch. */
    fun check(ctx: Context): Boolean {
        val watched = MmkvManager.decodeSettingsInt(K_THREAD, 0)
        if (watched == 0 || PamirApi.token == null) return false
        val s = fetch() ?: return true
        if (s.open && s.threadId == watched) {
            val last = s.lastAdminId
            if (last > (seen(watched) ?: last)) {
                setSeen(watched, last)
                val answer = s.messages.lastOrNull { it.optInt("id") == last }?.let { plain(it) }.orEmpty()
                notify(ctx, "Поддержка ответила", answer.ifBlank { "Обращение №$watched — откройте, чтобы прочитать ответ" }, "Открыть")
            }
            return true
        }
        MmkvManager.encodeSettings(K_THREAD, 0)
        if (s.status == "closed" && s.threadId == watched) {
            notify(ctx, "Обращение №$watched закрыто", "Если вопрос остался — откройте новое обращение в Настройках → Поддержка.", null)
        }
        return false
    }

    /** Message text without HTML; a photo without a caption becomes «Фото». */
    fun plain(m: JSONObject): String =
        runCatching { Html.fromHtml(m.optString("text"), Html.FROM_HTML_MODE_COMPACT).toString().trim() }.getOrDefault(m.optString("text"))
            .ifBlank { if (m.optString("media_type") == "photo") "Фото" else "" }

    private fun notify(ctx: Context, title: String, text: String, action: String?) = PamirWatch.notify(
        ctx, title, text, EXTRA_SUPPORT, action, NOTIFY_ID,
        channel = "pamir_support", channelName = "Поддержка", channelDesc = "Ответы поддержки и закрытие обращений"
    )
}

/** Every 15 minutes while a support ticket is open (WorkManager process, works with the app closed). */
class PamirSupportWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val more = runCatching { PamirSupport.check(applicationContext) }.getOrDefault(true)
        if (!more) cancel(applicationContext)
        return Result.success()
    }

    companion object {
        private const val NAME = "pamir_support_watch"

        fun schedule(context: Context) {
            runCatching {
                val request = PeriodicWorkRequestBuilder<PamirSupportWorker>(15, TimeUnit.MINUTES)
                    .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                    .setInitialDelay(5, TimeUnit.MINUTES)
                    .build()
                RemoteWorkManager.getInstance(context.applicationContext)
                    .enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
            }.onFailure { Log.w("Pamir", "support watch schedule failed: ${it.message}") }
        }

        fun cancel(context: Context) {
            runCatching { RemoteWorkManager.getInstance(context.applicationContext).cancelUniqueWork(NAME) }
        }
    }
}
