package com.v2ray.ang.pamir

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkerParameters
import androidx.work.multiprocess.RemoteWorkManager
import com.v2ray.ang.handler.AngConfigManager
import java.util.concurrent.TimeUnit

/**
 * Every 6 hours: refreshes the subscription (fresh "days left"), reminds about renewal
 * notifies about a new news item from the admin panel and about a comeback discount, and gets a new app build
 * ready on Wi-Fi (PamirUpdater).
 * Runs in the WorkManager process (":bg"), so it works even when the app is closed.
 */
class PamirReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        runCatching { AngConfigManager.updateConfigViaSubAll() }
            .onFailure { Log.w("Pamir", "reminder: sub update failed ${it.message}") }
        runCatching { PamirWatch.checkExpiry(applicationContext) }
        runCatching { PamirNews.notifyNew(applicationContext) }
        runCatching { PamirOffers.notifyNew(applicationContext) }
        runCatching { PamirApi.pingInstall(applicationContext) }
        runCatching { PamirHosts.refresh() }
        runCatching { PamirSeason.applyIcon(applicationContext) }   // the New Year icon on Dec 20 and back on Jan 11
        // one-tap update: a new build is downloaded on Wi-Fi and announced «готов — нажми, чтобы установить»
        runCatching { PamirUpdater.background(applicationContext) }
            .onFailure { Log.w("Pamir", "reminder: update step failed ${it.message}") }
        return Result.success()
    }

    companion object {
        private const val NAME = "pamir_expiry_reminder"

        fun schedule(context: Context) {
            runCatching {
                val request = PeriodicWorkRequestBuilder<PamirReminderWorker>(6, TimeUnit.HOURS)
                    .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                    .setInitialDelay(30, TimeUnit.MINUTES)
                    .build()
                RemoteWorkManager.getInstance(context.applicationContext)
                    .enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
            }.onFailure { Log.w("Pamir", "reminder schedule failed: ${it.message}") }
        }
    }
}
