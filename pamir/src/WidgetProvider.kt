package com.v2ray.ang.receiver

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.widget.RemoteViews
import com.v2ray.ang.AppConfig
import com.v2ray.ang.R
import com.v2ray.ang.core.CoreServiceManager
import com.v2ray.ang.core.LauncherManager
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.pamir.PamirActivity
import com.v2ray.ang.pamir.PamirWatch

/** Pamir VPN home screen widget: power button + status + server. */
class WidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        render(context, appWidgetManager, appWidgetIds, CoreServiceManager.isRunning())
    }

    private fun render(context: Context, manager: AppWidgetManager, ids: IntArray, isRunning: Boolean) {
        val views = RemoteViews(context.packageName, R.layout.widget_switch)
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val needsApp = !isRunning &&
            (MmkvManager.getSelectServer().isNullOrEmpty() || runCatching { VpnService.prepare(context) != null }.getOrDefault(true))
        val click = if (needsApp) {
            // first connection needs the system VPN dialog -> open the app, it connects by itself
            PendingIntent.getActivity(
                context, R.id.layout_switch,
                Intent(context, PamirActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    .putExtra(PamirWatch.EXTRA_RECONNECT, true),
                flags
            )
        } else {
            PendingIntent.getBroadcast(
                context, R.id.layout_switch,
                Intent(context, WidgetProvider::class.java).setAction(AppConfig.BROADCAST_ACTION_WIDGET_CLICK),
                flags
            )
        }
        views.setOnClickPendingIntent(R.id.layout_switch, click)
        if (isRunning) {
            views.setInt(R.id.layout_background, "setBackgroundResource", R.drawable.pamir_widget_btn_on)
            views.setImageViewResource(R.id.image_switch, R.drawable.pamir_ic_power_dark)
            views.setTextViewText(R.id.widget_status, "Защищено · " + PamirWatch.selectedTitle())
            views.setTextColor(R.id.widget_status, 0xFF2BEFC0.toInt())
        } else {
            views.setInt(R.id.layout_background, "setBackgroundResource", R.drawable.pamir_widget_btn_off)
            views.setImageViewResource(R.id.image_switch, R.drawable.pamir_ic_power_light)
            views.setTextViewText(R.id.widget_status, "Не подключено · нажмите")
            views.setTextColor(R.id.widget_status, 0xFF8494A8.toInt())
        }
        for (id in ids) manager.updateAppWidget(id, views)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            AppConfig.BROADCAST_ACTION_WIDGET_CLICK -> {
                if (CoreServiceManager.isRunning()) {
                    LauncherManager.stopService(context)
                } else {
                    LauncherManager.startServiceFromToggle(context)
                }
            }

            AppConfig.BROADCAST_ACTION_ACTIVITY -> {
                val manager = AppWidgetManager.getInstance(context) ?: return
                val ids = manager.getAppWidgetIds(ComponentName(context, WidgetProvider::class.java))
                if (ids.isEmpty()) return
                when (intent.getIntExtra("key", 0)) {
                    AppConfig.MSG_STATE_RUNNING, AppConfig.MSG_STATE_START_SUCCESS -> render(context, manager, ids, true)
                    AppConfig.MSG_STATE_NOT_RUNNING, AppConfig.MSG_STATE_START_FAILURE,
                    AppConfig.MSG_STATE_STOP_SUCCESS -> render(context, manager, ids, false)
                }
            }
        }
    }
}
