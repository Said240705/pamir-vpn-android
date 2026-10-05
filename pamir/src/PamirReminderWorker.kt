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
 * notifies about a new news item from the admin panel and about a comeback discount.
 * Runs in the WorkManager process (":bg"), so it works even when the app is closed.
 */
class PamirReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        runCatching { AngConfigManager.updateConfigViaSubAll() }
            .onFailure { Log.w("Pamir", "reminder: sub update failed ${it.message}") }
        runCatching { PamirWatch.checkExpiry(applicationContext) }
        runCatching { PamirNews.notifyNew(applicationContext) }
        runCatching { PamirOffers.notifyNew(applicationContext) }
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
