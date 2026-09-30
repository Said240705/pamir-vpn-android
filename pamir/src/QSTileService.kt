package com.v2ray.ang.service

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.drawable.Icon
import android.net.VpnService
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import androidx.core.content.ContextCompat
import com.v2ray.ang.AppConfig
import com.v2ray.ang.R
import com.v2ray.ang.core.CoreServiceManager
import com.v2ray.ang.core.LauncherManager
import com.v2ray.ang.handler.AppLocaleManager
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.helper.MessageHelper
import com.v2ray.ang.pamir.PamirActivity
import com.v2ray.ang.pamir.PamirWatch
import com.v2ray.ang.util.LogUtil
import com.v2ray.ang.util.Utils
import java.lang.ref.SoftReference

/** Pamir VPN quick settings tile: one tap on/off, shows the server while connected. */
class QSTileService : TileService() {

    override fun attachBaseContext(newBase: Context?) {
        super.attachBaseContext(newBase?.let(AppLocaleManager::localizedContext))
    }

    fun setState(state: Int) {
        val tile = qsTile ?: return
        tile.icon = Icon.createWithResource(applicationContext, R.drawable.ic_stat_name)
        if (state == Tile.STATE_ACTIVE) {
            tile.state = Tile.STATE_ACTIVE
            tile.label = PamirWatch.title(CoreServiceManager.getRunningServerName().ifBlank { null })
                .takeIf { it != "Pamir VPN" } ?: PamirWatch.selectedTitle()
            if (Build.VERSION.SDK_INT >= 29) tile.subtitle = "Защищено"
        } else {
            tile.state = Tile.STATE_INACTIVE
            tile.label = "Pamir VPN"
            if (Build.VERSION.SDK_INT >= 29) tile.subtitle = "Отключено"
        }
        tile.updateTile()
    }

    override fun onStartListening() {
        super.onStartListening()
        setState(if (CoreServiceManager.isRunning()) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE)
        mMsgReceive = ReceiveMessageHandler(this)
        val mFilter = IntentFilter(AppConfig.BROADCAST_ACTION_ACTIVITY)
        ContextCompat.registerReceiver(applicationContext, mMsgReceive, mFilter, Utils.receiverFlags())
        MessageHelper.sendMsg2Service(this, AppConfig.MSG_REGISTER_CLIENT, "")
    }

    override fun onStopListening() {
        super.onStopListening()
        try {
            applicationContext.unregisterReceiver(mMsgReceive)
            mMsgReceive = null
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to unregister receiver", e)
        }
    }

    override fun onClick() {
        super.onClick()
        when (qsTile?.state) {
            Tile.STATE_ACTIVE -> LauncherManager.stopService(this)
            else -> {
                // First connection needs the system VPN dialog -> open the app instead
                if (MmkvManager.getSelectServer().isNullOrEmpty() || VpnService.prepare(this) != null) {
                    openApp()
                } else {
                    LauncherManager.startServiceFromToggle(this)
                }
            }
        }
    }

    @SuppressLint("StartActivityAndCollapseDeprecated")
    private fun openApp() {
        val intent = Intent(this, PamirActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .putExtra(PamirWatch.EXTRA_RECONNECT, true)
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startActivityAndCollapse(
                    PendingIntent.getActivity(this, 7, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                )
            } else {
                @Suppress("DEPRECATION")
                startActivityAndCollapse(intent)
            }
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Tile: failed to open app", e)
        }
    }

    private var mMsgReceive: BroadcastReceiver? = null

    private class ReceiveMessageHandler(context: QSTileService) : BroadcastReceiver() {
        var mReference: SoftReference<QSTileService> = SoftReference(context)
        override fun onReceive(ctx: Context?, intent: Intent?) {
            val context = mReference.get()
            when (intent?.getIntExtra("key", 0)) {
                AppConfig.MSG_STATE_RUNNING, AppConfig.MSG_STATE_START_SUCCESS -> context?.setState(Tile.STATE_ACTIVE)
                AppConfig.MSG_STATE_NOT_RUNNING, AppConfig.MSG_STATE_START_FAILURE,
                AppConfig.MSG_STATE_STOP_SUCCESS -> context?.setState(Tile.STATE_INACTIVE)
            }
        }
    }
}
