#!/usr/bin/env python3
"""Mognu (Pamir) branding for the v2rayNG sources. Runs in CI before the Gradle build.

Env:
  PAMIR_OWNER    GitHub owner of the pamir-vpn-android repo (for update checks)
  PAMIR_VERSION  versionName, e.g. 1.0.0 (must be digits and dots for the update checker)
  PAMIR_CODE     integer versionCode (monotonic, e.g. 1000 + run number)
  PAMIR_TEST     1 = private test build: own package (installs next to the real app), name «Mognu тест»
"""
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'V2rayNG', 'app'))
MAIN = os.path.join(ROOT, 'src', 'main')
PKG = os.path.join(MAIN, 'java', 'com', 'v2ray', 'ang')
OWNER = os.environ.get('PAMIR_OWNER', 'pamirvpn')
VERSION = os.environ.get('PAMIR_VERSION', '1.0.0')
CODE = os.environ.get('PAMIR_CODE', '1000')
TEST = os.environ.get('PAMIR_TEST') == '1'
BRAND = 'Mognu'
APP_NAME = BRAND + (' тест' if TEST else '')
PACKAGE = 'ru.pamirlink.vpn' + ('.test' if TEST else '')
BRAND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'res', 'brand')

# Mognu palette: lime accent on near-black, violet carries the accent in the light theme
MINT, MINT_DEEP = 'C8FF2E', 'A3E000'
VIOLET, VIOLET_DEEP = '6A3DF5', '5428E0'
BG, SURFACE, SURFACE_HI = '1E1640', '2A2058', '352A68'


def edit(path, pairs, required=True):
    s = open(path, encoding='utf-8').read()
    for old, new in pairs:
        if isinstance(old, re.Pattern):
            s, n = old.subn(new, s)
        else:
            n = s.count(old)
            s = s.replace(old, new)
        if required and n == 0:
            sys.exit(f'brand: pattern not found in {path}: {old!r}')
    open(path, 'w', encoding='utf-8').write(s)


# 1. package id, version, apk names
edit(os.path.join(ROOT, 'build.gradle.kts'), [
    ('applicationId = "com.v2ray.ang"', f'applicationId = "{PACKAGE}"'),
    ('    namespace = "com.v2ray.ang"\n', '    namespace = "com.v2ray.ang"\n    lint { checkReleaseBuilds = false }\n'),
    (re.compile(r'versionCode = \d+'), f'versionCode = {int(CODE)}'),
    (re.compile(r'versionName = "[^"]*"'), f'versionName = "{VERSION}"'),
    ('"v2rayNG_', '"PamirVPN_'),
])

# 2. app name in every language
for f in glob.glob(os.path.join(MAIN, 'res', 'values*', 'strings.xml')):
    edit(f, [('v2rayNG', APP_NAME)], required=False)

# 3. links: updates from our repo, support -> our bot, "promotion" -> cabinet
edit(os.path.join(PKG, 'AppConfig.kt'), [
    ('const val APP_URL = "$GITHUB_URL/2dust/v2rayNG"', f'const val APP_URL = "$GITHUB_URL/{OWNER}/pamir-vpn-android"'),
    ('https://api.github.com/repos/2dust/v2rayNG/releases', f'https://api.github.com/repos/{OWNER}/pamir-vpn-android/releases'),
    ('https://t.me/github_2dust', 'https://t.me/pamirlink_bot'),
    (re.compile(r'APP_PROMOTION_URL = "[^"]*"'), 'APP_PROMOTION_URL = "aHR0cHM6Ly9hcHAucGFtaXJsaW5rLnJ1"'),
])

# 4. deep link pamirvpn://install-sub?url=... (in addition to v2rayng://)
edit(os.path.join(MAIN, 'AndroidManifest.xml'), [
    ('<data android:scheme="v2rayng" />', '<data android:scheme="v2rayng" />\n                <data android:scheme="pamirvpn" />'),
])

# 5. colours: dark by default, no Material You override, mint accents
theme = os.path.join(PKG, 'ui', 'compose', 'Theme.kt')
dark = {
    'primary': MINT, 'onPrimary': '0A0A10', 'primaryContainer': '2E3A0A', 'onPrimaryContainer': 'E6FFB0',
    'secondary': MINT, 'onSecondary': '0A0A10', 'secondaryContainer': '2E3A0A', 'onSecondaryContainer': 'E6FFB0',
    'tertiary': MINT, 'onTertiary': '0A0A10',
    'background': BG, 'surface': BG, 'surfaceTint': MINT, 'inversePrimary': '4A6A00',
    'surfaceVariant': SURFACE_HI, 'outlineVariant': '453A80',
    'surfaceContainerLowest': '160F33', 'surfaceContainerLow': SURFACE, 'surfaceContainer': SURFACE,
    'surfaceContainerHigh': SURFACE_HI, 'surfaceContainerHighest': '3F3378',
}
light = {'primary': VIOLET, 'onPrimary': 'FFFFFF', 'secondary': VIOLET, 'onSecondary': 'FFFFFF',
         'secondaryContainer': 'E6DEFF', 'onSecondaryContainer': '1F0A66', 'surfaceTint': VIOLET}
s = open(theme, encoding='utf-8').read()
for name, colors in (('DarkColor', dark), ('LightColor', light)):
    m = re.search(r'private val %s = \w+ColorScheme\((.*?)\n\)' % name, s, re.S)
    if not m:
        sys.exit(f'brand: {name} not found')
    block = m.group(1)
    for key, val in colors.items():
        block, n = re.subn(r'(\n\s*%s = Color\(0x)FF[0-9A-Fa-f]{6}' % key, r'\g<1>FF' + val, block)
        if n != 1:
            sys.exit(f'brand: {name}.{key} not found')
    s = s[:m.start(1)] + block + s[m.end(1):]
s = s.replace('val colorFabActive = Color(0xFFf97910)', f'val colorFabActive = Color(0xFF{VIOLET})')
s = s.replace('val colorConfigType = Color(0xFFf97910)', f'val colorConfigType = Color(0xFF{VIOLET})')
s = s.replace('decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "0") ?: "0"', 'decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "2") ?: "2"')
s = s.replace('decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, true)', 'decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, false)')
open(theme, 'w', encoding='utf-8').write(s)
edit(os.path.join(PKG, 'ui', 'settings', 'SettingsActivity.kt'), [
    ('rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "0")', 'rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "2")'),
    ('rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, true)', 'rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, false)'),
])

# 6. launcher icons: Mognu crowned M from pamir/res/brand (kept in the repo, so a build never depends on the site)
from PIL import Image, ImageDraw  # noqa: E402

icon = Image.open(os.path.join(BRAND_DIR, 'icon.png')).convert('RGBA')   # full square icon (lime + mark)
mark = Image.open(os.path.join(BRAND_DIR, 'mark.png')).convert('RGBA')   # transparent dark mark
bbox = mark.getbbox()
if bbox:
    mark = mark.crop(bbox)

edit(os.path.join(MAIN, 'res', 'values', 'ic_launcher_background.xml'), [('#FFFFFF', '#FF' + MINT)])
sizes = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
for dens, px in sizes.items():
    d = os.path.join(MAIN, 'res', 'mipmap-' + dens)
    os.makedirs(d, exist_ok=True)
    sq = icon.resize((px, px), Image.LANCZOS)
    rmask = Image.new('L', (px, px), 0)
    ImageDraw.Draw(rmask).rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * 0.22), fill=255)
    out = Image.new('RGBA', (px, px), (0, 0, 0, 0)); out.paste(sq, (0, 0), rmask)
    out.save(os.path.join(d, 'ic_launcher.png'))
    cmask = Image.new('L', (px, px), 0)
    ImageDraw.Draw(cmask).ellipse((0, 0, px - 1, px - 1), fill=255)
    out = Image.new('RGBA', (px, px), (0, 0, 0, 0)); out.paste(sq, (0, 0), cmask)
    out.save(os.path.join(d, 'ic_launcher_round.png'))
    fg = int(px * 108 / 48)                     # adaptive foreground canvas = 108dp
    canvas = Image.new('RGBA', (fg, fg), (0, 0, 0, 0))
    m = mark.copy(); m.thumbnail((int(fg * 0.64), int(fg * 0.64)), Image.LANCZOS)
    canvas.paste(m, ((fg - m.width) // 2, (fg - m.height) // 2 + int(fg * 0.02)), m)
    canvas.save(os.path.join(d, 'ic_launcher_foreground.png'))

# New Year icon (PamirSeason switches the launcher alias to it Dec 20 – Jan 10): the M in a Santa hat instead of the crown
icon_ny = Image.open(os.path.join(BRAND_DIR, 'icon_ny.png')).convert('RGBA')
mark_ny = Image.open(os.path.join(BRAND_DIR, 'mark_ny.png')).convert('RGBA')
if mark_ny.getbbox():
    mark_ny = mark_ny.crop(mark_ny.getbbox())
for dens, px in sizes.items():
    d = os.path.join(MAIN, 'res', 'mipmap-' + dens)
    sq = icon_ny.resize((px, px), Image.LANCZOS)
    rmask = Image.new('L', (px, px), 0)
    ImageDraw.Draw(rmask).rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * 0.22), fill=255)
    out = Image.new('RGBA', (px, px), (0, 0, 0, 0)); out.paste(sq, (0, 0), rmask)
    out.save(os.path.join(d, 'ic_launcher_ny.png'))
    cmask = Image.new('L', (px, px), 0)
    ImageDraw.Draw(cmask).ellipse((0, 0, px - 1, px - 1), fill=255)
    out = Image.new('RGBA', (px, px), (0, 0, 0, 0)); out.paste(sq, (0, 0), cmask)
    out.save(os.path.join(d, 'ic_launcher_ny_round.png'))
    fg = int(px * 108 / 48)
    canvas = Image.new('RGBA', (fg, fg), (0, 0, 0, 0))
    m = mark_ny.copy(); m.thumbnail((int(fg * 0.5), int(fg * 0.5)), Image.LANCZOS)   # hat and M inside the 66dp safe circle
    canvas.paste(m, ((fg - m.width) // 2, (fg - m.height) // 2), m)
    canvas.save(os.path.join(d, 'ic_launcher_ny_foreground.png'))
for name in ('ic_launcher_ny', 'ic_launcher_ny_round'):
    with open(os.path.join(MAIN, 'res', 'mipmap-anydpi-v26', name + '.xml'), 'w', encoding='utf-8') as f:
        # themed (monochrome) icons keep the plain mark: a one-colour hat would read as a blob
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/ic_launcher_background" />\n'
                '    <foreground android:drawable="@mipmap/ic_launcher_ny_foreground" />\n'
                '    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />\n</adaptive-icon>\n')

# 7. device headers for subscription requests (panel HWID limit + device list in the cabinet)
HEADERS_FN = r'''    private fun pamirDeviceHeaders(b: Request.Builder) {
        try {
            var id = com.v2ray.ang.handler.MmkvManager.decodeSettingsString("pamir_hwid", "") ?: ""
            if (id.isBlank()) {
                id = java.util.UUID.randomUUID().toString().replace("-", "")
                com.v2ray.ang.handler.MmkvManager.encodeSettings("pamir_hwid", id)
            }
            val model = listOfNotNull(android.os.Build.MANUFACTURER, android.os.Build.MODEL).joinToString(" ").trim()
            b.header("x-hwid", id)
            b.header("x-device-os", "Android")
            b.header("x-ver-os", android.os.Build.VERSION.RELEASE ?: "")
            b.header("x-device-model", model.replace(Regex("[^\\x20-\\x7E]"), ""))
        } catch (_: Exception) {
        }
    }

    private fun applyEmbeddedBasicAuthHeader('''
edit(os.path.join(PKG, 'util', 'HttpUtil.kt'), [
    ('            applyEmbeddedBasicAuthHeader(currentUrl, requestBuilder)\n',
     '            applyEmbeddedBasicAuthHeader(currentUrl, requestBuilder)\n            pamirDeviceHeaders(requestBuilder)\n'),
    ('    private fun applyEmbeddedBasicAuthHeader(', HEADERS_FN),
    # subscription expiry for the app comes from this header, so server names can stay clean
    ('                    response.isSuccessful -> {\n                        return response.body?.string() ?: ""\n',
     '                    response.isSuccessful -> {\n'
     '                        com.v2ray.ang.pamir.PamirWatch.saveSubInfo(request.url, response.header("subscription-userinfo"))\n'
     '                        return response.body?.string() ?: ""\n'),
])

# 8. imported subscription is called "Pamir VPN"; empty groups (e.g. "Default") are hidden,
#    so right after import the user lands on the list with servers
edit(os.path.join(PKG, 'handler', 'AngConfigManager.kt'), [
    ('subItem.remarks = uri.fragment ?: "import sub"', f'subItem.remarks = uri.fragment ?: "{BRAND}"'),
])
# «Расширенные настройки» open the stock v2rayNG screen on top of Pamir in the same task: Back must return to Pamir
# (upstream sends the whole task to the background there, so the user could not get back).
edit(os.path.join(PKG, 'ui', 'main', 'MainActivity.kt'), [
    ('BackHandler { moveTaskToBack(false) }', 'BackHandler { finish() }'),
    ("""        if (keyCode == KeyEvent.KEYCODE_BUTTON_B) {
            moveTaskToBack(false)""", """        if (keyCode == KeyEvent.KEYCODE_BUTTON_B) {
            finish()"""),
])
edit(os.path.join(PKG, 'ui', 'main', 'MainRepository.kt'), [
    ('        result += MmkvManager.decodeSubscriptions()\n        return result',
     '        val subs = MmkvManager.decodeSubscriptions()\n'
     '        val nonEmpty = subs.filter { MmkvManager.decodeServerList(it.guid).isNotEmpty() }\n'
     '        result += if (nonEmpty.isEmpty()) subs else nonEmpty\n'
     '        return result'),
])

# 9. Pamir UI: own launcher activity on top of the v2rayNG core
import shutil
dst = os.path.join(PKG, 'pamir')
os.makedirs(dst, exist_ok=True)
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'PamirActivity.kt'), os.path.join(dst, 'PamirActivity.kt'))
# in-app logo: the full rounded icon (the dark mark alone would vanish on the dark theme)
logo = icon.resize((256, 256), Image.LANCZOS)
lmask = Image.new('L', (256, 256), 0)
ImageDraw.Draw(lmask).rounded_rectangle((0, 0, 255, 255), radius=56, fill=255)
logo.putalpha(lmask)
os.makedirs(os.path.join(MAIN, 'res', 'drawable-nodpi'), exist_ok=True)
logo.save(os.path.join(MAIN, 'res', 'drawable-nodpi', 'pamir_logo.png'))
edit(os.path.join(MAIN, 'AndroidManifest.xml'), [
    ('''                <category android:name="android.intent.category.LAUNCHER" />
                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
''', ''),
    ('''        <activity
            android:name=".ui.UrlSchemeActivity"''', '''        <activity
            android:name=".pamir.PamirHome"
            android:exported="true"
            android:launchMode="singleTask" />
        <!-- The launcher entry keeps the name .pamir.PamirActivity it always had, so home-screen shortcuts made
             before the New Year icon still point at it. PamirSeason swaps it for .pamir.PamirNewYear (the same
             screen with the hat icon) Dec 20 – Jan 10; one of the two is always enabled. -->
        <activity-alias
            android:name=".pamir.PamirActivity"
            android:targetActivity=".pamir.PamirHome"
            android:exported="true"
            android:enabled="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
            </intent-filter>
        </activity-alias>
        <activity-alias
            android:name=".pamir.PamirNewYear"
            android:targetActivity=".pamir.PamirHome"
            android:icon="@mipmap/ic_launcher_ny"
            android:roundIcon="@mipmap/ic_launcher_ny_round"
            android:exported="true"
            android:enabled="false">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity-alias>
        <activity
            android:name=".ui.UrlSchemeActivity"'''),
])
edit(os.path.join(MAIN, 'AndroidManifest.xml'), [
    ('    <application', '    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />\n\n    <application'),
])
edit(os.path.join(PKG, 'ui', 'UrlSchemeActivity.kt'), [
    ('startActivity(Intent(this, MainActivity::class.java))', 'startActivity(Intent(this, com.v2ray.ang.pamir.PamirHome::class.java))'),
])
edit(os.path.join(PKG, 'handler', 'NotificationManager.kt'), [
    ('Intent(service, MainActivity::class.java)', 'Intent(service, com.v2ray.ang.pamir.PamirHome::class.java)'),
])

# 10. background features: drop alerts + watchdog, branded tile/widget/status icon, cleaner notification
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'res')
for f in glob.glob(os.path.join(SRC, 'Pamir*.kt')):
    shutil.copy(f, os.path.join(dst, os.path.basename(f)))
shutil.copy(os.path.join(SRC, 'QSTileService.kt'), os.path.join(PKG, 'service', 'QSTileService.kt'))
shutil.copy(os.path.join(SRC, 'WidgetProvider.kt'), os.path.join(PKG, 'receiver', 'WidgetProvider.kt'))
for f in glob.glob(os.path.join(MAIN, 'res', 'drawable-*dpi', 'ic_stat_*.png')):
    os.remove(f)
for sub in ('layout', 'drawable', 'xml', 'font'):
    os.makedirs(os.path.join(MAIN, 'res', sub), exist_ok=True)
    for f in glob.glob(os.path.join(RES, sub, '*.xml' if sub != 'font' else '*.ttf')):
        shutil.copy(f, os.path.join(MAIN, 'res', sub, os.path.basename(f)))
# Android TV launcher banner: our PNG replaces the v2rayNG one; the adaptive banner (API 26+) would win over it
shutil.copy(os.path.join(RES, 'mipmap-xhdpi', 'ic_banner.png'), os.path.join(MAIN, 'res', 'mipmap-xhdpi', 'ic_banner.png'))
banner_xml = os.path.join(MAIN, 'res', 'mipmap-anydpi-v26', 'ic_banner.xml')
if os.path.exists(banner_xml):
    os.remove(banner_xml)
for f in glob.glob(os.path.join(MAIN, 'res', 'values*', 'strings.xml')):
    edit(f, [
        (re.compile(r'<string name="app_widget_name">[^<]*</string>'), f'<string name="app_widget_name">{BRAND}</string>'),
        (re.compile(r'<string name="app_tile_name">[^<]*</string>'), f'<string name="app_tile_name">{BRAND}</string>'),
    ], required=False)

PROBE_FN = """    /** Pamir watchdog probe: delay through the running core, -1 = no answer, -2 = not running. */
    fun pamirProbe(): Long {
        if (!isRunning() || isReloading) return -2L
        for (alt in listOf(false, true)) {
            val t = try {
                coreController.measureDelay(SettingsManager.getDelayTestUrl(alt))
            } catch (e: Exception) {
                -1L
            }
            if (t >= 0) return t
        }
        return -1L
    }

    private fun measureV2rayDelay(requestId: String) {"""
csm = os.path.join(PKG, 'core', 'CoreServiceManager.kt')
edit(csm, [
    ('LogUtil.i(AppConfig.TAG, "StartCore-Manager: Stop service")\n',
     'LogUtil.i(AppConfig.TAG, "StartCore-Manager: Stop service")\n                    com.v2ray.ang.pamir.PamirWatch.markUserStop()\n'),
    ('LogUtil.i(AppConfig.TAG, "StartCore-Manager: Restart service")\n',
     'LogUtil.i(AppConfig.TAG, "StartCore-Manager: Restart service")\n                    com.v2ray.ang.pamir.PamirWatch.markUserStop()\n'),
    ('        launchCore(service, vpnInterface)\n        startNetworkMonitor(service)\n',
     '        launchCore(service, vpnInterface)\n        startNetworkMonitor(service)\n        com.v2ray.ang.pamir.PamirWatch.onStarted(service)\n'),
    ('        MessageHelper.sendMsg2UI(service, AppConfig.MSG_STATE_STOP_SUCCESS, "")\n',
     '        MessageHelper.sendMsg2UI(service, AppConfig.MSG_STATE_STOP_SUCCESS, "")\n        com.v2ray.ang.pamir.PamirWatch.onStopped(service)\n'),
    ('    private fun measureV2rayDelay(requestId: String) {', PROBE_FN),
])

SPEED_FN = """    private fun appendSpeedString(text: StringBuilder, name: String?, up: Double, down: Double) {
        val n = when (name) {
            AppConfig.TAG_PROXY -> "Через VPN"
            AppConfig.TAG_DIRECT -> "Напрямую"
            else -> name ?: ""
        }
        text.append("$n:  ↓ ${pamirSpeed(down)}  ↑ ${pamirSpeed(up)}\\n")
    }

    private fun pamirSpeed(v: Double): String {
        val b = v.toLong()
        return when {
            b < 1024 -> "$b Б/с"
            b < 1024 * 1024 -> String.format("%.0f КБ/с", b / 1024.0)
            else -> String.format("%.1f МБ/с", b / 1048576.0)
        }
    }
"""
nm = os.path.join(PKG, 'handler', 'NotificationManager.kt')
edit(nm, [
    ('.setContentTitle(currentConfig?.remarks ?: service.getString(R.string.app_name))',
     '.setContentTitle(currentConfig?.remarks?.let { com.v2ray.ang.pamir.PamirWatch.title(it) } ?: service.getString(R.string.app_name))\n            .setColor(0xFF' + MINT + '.toInt())'),
    (re.compile(r'    private fun appendSpeedString\(text: StringBuilder, name: String\?, up: Double, down: Double\) \{.*?\n    \}\n', re.S),
     lambda m: SPEED_FN),
])


# 11. crash reports from every process (saved to files, sent on next launch)
edit(os.path.join(PKG, 'AngApplication.kt'), [
    ('        MmkvManager.initialize(this)\n', '        MmkvManager.initialize(this)\n        com.v2ray.ang.pamir.PamirCrash.install(this)\n'),
])

print(f'brand: ok -> {PACKAGE} «{APP_NAME}» {VERSION} ({CODE}), owner {OWNER}')
