package com.v2ray.ang.pamir

/**
 * The app's main screen as the system sees it. The launcher reaches it through one of two aliases in the manifest:
 * «.pamir.PamirActivity» (the regular icon — the name launchers had stored for years, so existing home-screen
 * shortcuts keep working) or «.pamir.PamirNewYear» (the hat icon, Dec 20 – Jan 10, see PamirSeason.applyIcon).
 * Explicit intents (notifications, widget, tile) target this class, which is never disabled.
 */
class PamirHome : PamirActivity()
