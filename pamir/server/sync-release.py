#!/usr/bin/env python3
"""Mirror the latest Pamir VPN GitHub release into the site's download folder.

Run from cron every 10 minutes. When GitHub has a newer non-prerelease version than
download/android.json, it downloads both APKs to temporary files, checks their sizes,
keeps the previous files in bak-<old version>/, then swaps the APKs and android.json in.
Nothing changes when the release is not newer or any download fails.

Env:
  PAMIR_REPO  GitHub repository, default Said240705/pamir-vpn-android
  PAMIR_DIR   site download folder, default /var/www/pamir-miniapp/frontend/download
"""
import json
import os
import shutil
import sys
import urllib.request

REPO = os.environ.get('PAMIR_REPO', 'Said240705/pamir-vpn-android')
DIR = os.environ.get('PAMIR_DIR', '/var/www/pamir-miniapp/frontend/download')
# file in DIR -> (fixed asset name, versioned asset suffix)
FILES = {
    'pamir-vpn.apk': ('pamir-vpn.apk', '_arm64-v8a.apk'),
    'pamir-vpn-universal.apk': ('pamir-vpn-universal.apk', '_universal.apk'),
}


def log(msg):
    print(msg, flush=True)


def newer(remote, local):
    r = [int(x) if x.isdigit() else 0 for x in remote.split('.')]
    l = [int(x) if x.isdigit() else 0 for x in local.split('.')]
    n = max(len(r), len(l))
    return r + [0] * (n - len(r)) > l + [0] * (n - len(l))


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'pamir-sync', 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=timeout)


def main():
    meta_path = os.path.join(DIR, 'android.json')
    try:
        current = json.load(open(meta_path, encoding='utf-8')).get('version', '0')
    except (OSError, ValueError):
        current = '0'
    release = json.load(fetch(f'https://api.github.com/repos/{REPO}/releases/latest'))
    version = release['tag_name'].lstrip('v')
    if not newer(version, current):
        return
    assets = {a['name']: a for a in release['assets']}

    def asset(fixed, suffix):
        return assets.get(fixed) or next((a for n, a in assets.items() if n.endswith(suffix)), None)

    picked = {f: asset(*spec) for f, spec in FILES.items()}
    if None in picked.values():
        log(f'{version}: release has no APK for ' + ', '.join(f for f, a in picked.items() if a is None))
        return 1
    log(f'update {current} -> {version}')

    tmp = {}
    try:
        for f, a in picked.items():
            path = os.path.join(DIR, f + '.new')
            with fetch(a['browser_download_url'], timeout=300) as src, open(path, 'wb') as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            tmp[f] = path
            if os.path.getsize(path) != a['size']:
                raise IOError(f'{a["name"]}: got {os.path.getsize(path)} of {a["size"]} bytes')
    except Exception:
        for path in tmp.values():
            os.remove(path)
        raise

    bak = os.path.join(DIR, f'bak-{current}')
    os.makedirs(bak, exist_ok=True)
    for f in list(FILES) + ['android.json']:
        if os.path.exists(os.path.join(DIR, f)):
            shutil.copy2(os.path.join(DIR, f), bak)
    for f, path in tmp.items():
        os.replace(path, os.path.join(DIR, f))
    meta = {'version': version}
    meta['arm64-v8a'] = {'file': 'pamir-vpn.apk', 'size': picked['pamir-vpn.apk']['size']}
    meta['universal'] = {'file': 'pamir-vpn-universal.apk', 'size': picked['pamir-vpn-universal.apk']['size']}
    with open(meta_path + '.new', 'w', encoding='utf-8') as out:
        json.dump(meta, out)
    os.replace(meta_path + '.new', meta_path)
    # keep only the latest backup
    for d in os.listdir(DIR):
        if d.startswith('bak-') and d != os.path.basename(bak):
            shutil.rmtree(os.path.join(DIR, d), ignore_errors=True)
    log(f'done: {version}')


if __name__ == '__main__':
    sys.exit(main())
