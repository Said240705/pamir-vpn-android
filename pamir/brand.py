#!/usr/bin/env python3
"""Pamir VPN branding for the v2rayNG sources. Runs in CI before the Gradle build.

Env:
  PAMIR_OWNER    GitHub owner of the pamir-vpn-android repo (for update checks)
  PAMIR_VERSION  versionName, e.g. 1.0.0 (must be digits and dots for the update checker)
  PAMIR_CODE     integer versionCode (monotonic, e.g. 1000 + run number)
"""
import glob
import io
import os
import re
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'V2rayNG', 'app'))
MAIN = os.path.join(ROOT, 'src', 'main')
PKG = os.path.join(MAIN, 'java', 'com', 'v2ray', 'ang')
OWNER = os.environ.get('PAMIR_OWNER', 'pamirvpn')
VERSION = os.environ.get('PAMIR_VERSION', '1.0.0')
CODE = os.environ.get('PAMIR_CODE', '1000')
APP_NAME = 'Pamir VPN'
ASSETS = 'https://app.pamirlink.ru/assets/'

MINT, MINT_DEEP = '2BEFC0', '17B896'
BG, SURFACE, SURFACE_HI = '0B1420', '101B2A', '17243A'


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
    ('applicationId = "com.v2ray.ang"', 'applicationId = "ru.pamirlink.vpn"'),
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
    'primary': MINT, 'onPrimary': '05241D', 'primaryContainer': '0F3B31', 'onPrimaryContainer': 'B8FFEA',
    'secondary': MINT, 'onSecondary': '05241D', 'secondaryContainer': '0F3B31', 'onSecondaryContainer': 'B8FFEA',
    'tertiary': MINT, 'onTertiary': '05241D',
    'background': BG, 'surface': BG, 'surfaceTint': MINT, 'inversePrimary': '0F6B57',
    'surfaceVariant': SURFACE_HI, 'outlineVariant': '24344D',
    'surfaceContainerLowest': '070E17', 'surfaceContainerLow': SURFACE, 'surfaceContainer': SURFACE,
    'surfaceContainerHigh': SURFACE_HI, 'surfaceContainerHighest': '1D2C45',
}
light = {'primary': MINT_DEEP, 'onPrimary': 'FFFFFF', 'secondary': MINT_DEEP, 'onSecondary': 'FFFFFF',
         'secondaryContainer': 'D3FBEF', 'onSecondaryContainer': '00382E', 'surfaceTint': MINT_DEEP}
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
s = s.replace('val colorFabActive = Color(0xFFf97910)', f'val colorFabActive = Color(0xFF{MINT_DEEP})')
s = s.replace('val colorConfigType = Color(0xFFf97910)', f'val colorConfigType = Color(0xFF{MINT_DEEP})')
s = s.replace('decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "0") ?: "0"', 'decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "2") ?: "2"')
s = s.replace('decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, true)', 'decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, false)')
open(theme, 'w', encoding='utf-8').write(s)
edit(os.path.join(PKG, 'ui', 'settings', 'SettingsActivity.kt'), [
    ('rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "0")', 'rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "2")'),
    ('rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, true)', 'rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, false)'),
])

# 6. launcher icons from the Pamir logo
from PIL import Image, ImageDraw  # noqa: E402


def fetch(name):
    local = os.environ.get('PAMIR_ASSETS_DIR')
    if local:
        return Image.open(os.path.join(local, name)).convert('RGBA')
    req = urllib.request.Request(ASSETS + name, headers={'User-Agent': 'pamir-ci'})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert('RGBA')


icon = fetch('icon-512.webp')   # full square icon (dark bg + mark)
mark = fetch('logo.webp')       # transparent mark
bbox = mark.getbbox()
if bbox:
    mark = mark.crop(bbox)

edit(os.path.join(MAIN, 'res', 'values', 'ic_launcher_background.xml'), [('#FFFFFF', '#FF' + SURFACE)])
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
])

print(f'brand: ok -> ru.pamirlink.vpn {VERSION} ({CODE}), owner {OWNER}')
