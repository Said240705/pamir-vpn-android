#!/usr/bin/env bash
# Ежедневная копия всего важного с основного сервера на другой сервер (по умолчанию — входной сервер в Финляндии).
#
# Что копируется: базы панели x-ui и бота (снимок sqlite «.backup», без остановки служб), базы сайта,
# настройки nginx и сертификаты, конфиг Xray, настройки бота и сайта (.env, config.py), наши скрипты из /root,
# службы systemd и cron. Архив шифруется (AES-256, ключ — /root/.mognu-backup-key) и уходит на другой
# сервер по ssh-ключу, которым можно ТОЛЬКО положить архив или посмотреть список — ни войти, ни выполнить команды.
# На том сервере хранятся последние 14 копий, здесь — последние 3.
#
#   bash mognu_backup.sh install 31.77.6.71 [2222]   один раз: ключи, приёмник на том сервере (спросит его пароль),
#                                                    cron 04:17 UTC. Порт ssh — если 22 закрыт (AdminVPS не выпускает
#                                                    исходящий 22): на том сервере  bash mognu_backup.sh ssh-port 2222
#   bash mognu_backup.sh run                  сделать копию сейчас (так её запускает cron)
#   bash mognu_backup.sh list                 какие копии лежат на том сервере
#
# ВАЖНО: без ключа /root/.mognu-backup-key копии не расшифровать. Сохраните его отдельно (менеджер паролей),
# не в чат:  cat /root/.mognu-backup-key
# Восстановление:  openssl enc -d -aes-256-cbc -pbkdf2 -pass file:КЛЮЧ -in mognu-….tar.gz.enc | tar -xz -C /куда
set -euo pipefail
KEY=/root/.mognu-backup-key
SSHKEY=/root/.ssh/mognu_backup
CONF=/etc/mognu-backup.env
LOCAL=/root/backups
LOG=/var/log/mognu-backup.log

remote() { # $1 = команда приёмника (put … / list); stdin — данные
  # shellcheck disable=SC1090
  source "$CONF"
  ssh -i "$SSHKEY" -p "${BACKUP_PORT:-22}" -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "root@$BACKUP_HOST" "$1"
}

case "${1:-}" in
install)
  HOST="${2:?Укажите сервер для копий: bash mognu_backup.sh install 31.77.6.71 [порт]}"
  PORT="${3:-22}"
  timeout 10 bash -c "</dev/tcp/$HOST/$PORT" 2>/dev/null || { echo "До $HOST:$PORT не достучаться. Если закрыт 22 — на том сервере: bash mognu_backup.sh ssh-port 2222, потом install $HOST 2222"; exit 1; }
  umask 077
  [ -s "$KEY" ] || { openssl rand -base64 48 > "$KEY"; echo "Создан ключ шифрования $KEY — сохраните его отдельно (cat $KEY), не в чат."; }
  [ -s "$SSHKEY" ] || ssh-keygen -q -t ed25519 -N "" -C mognu-backup -f "$SSHKEY"
  printf 'BACKUP_HOST=%s\nBACKUP_PORT=%s\n' "$HOST" "$PORT" > "$CONF"
  PUB=$(cat "$SSHKEY.pub")
  echo "Ставлю приёмник на $HOST — ssh спросит пароль root этого сервера (один раз)."
  ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "root@$HOST" "PUB='$PUB' bash -s" <<'REMOTE'
set -eu
cat > /usr/local/sbin/mognu-backup-recv <<'EOF'
#!/bin/bash
# Приёмник копий Mognu: этим ключом можно только положить архив (put ИМЯ) или получить список (list).
set -eu
D=/root/mognu-backups; mkdir -p "$D"; chmod 700 "$D"
c="${SSH_ORIGINAL_COMMAND:-}"
if [ "$c" = list ]; then ls -lh --time-style=+%Y-%m-%d\ %H:%M "$D" | awk 'NR>1{print $6, $7, $5, $8}'; exit 0; fi
[[ "$c" =~ ^put\ (mognu-[0-9]{8}-[0-9]{6}\.tar\.gz\.enc)$ ]] || { echo "запрещено"; exit 1; }
f="${BASH_REMATCH[1]}"
cat > "$D/$f.part" && mv "$D/$f.part" "$D/$f"
ls -1t "$D"/mognu-*.enc | tail -n +15 | xargs -r rm -f
echo "ok $f $(stat -c %s "$D/$f") байт"
EOF
chmod 755 /usr/local/sbin/mognu-backup-recv
mkdir -p /root/.ssh; chmod 700 /root/.ssh; touch /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys
grep -v "mognu-backup$" /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.tmp || true
echo "command=\"/usr/local/sbin/mognu-backup-recv\",restrict $PUB" >> /root/.ssh/authorized_keys.tmp
mv /root/.ssh/authorized_keys.tmp /root/.ssh/authorized_keys
echo "приёмник готов"
REMOTE
  SELF=/usr/local/sbin/mognu-backup.sh
  install -m 700 "$0" "$SELF"
  { { crontab -l 2>/dev/null || true; } | { grep -v "mognu-backup.sh" || true; }; echo "17 4 * * * $SELF run >> $LOG 2>&1"; } | crontab -
  echo "cron: каждый день в 04:17 UTC. Первая копия — сейчас:"
  exec "$SELF" run
  ;;
run)
  [ -s "$KEY" ] && [ -s "$CONF" ] || { echo "Сначала: bash mognu_backup.sh install СЕРВЕР"; exit 1; }
  TS=$(date -u +%Y%m%d-%H%M%S); NAME="mognu-$TS.tar.gz.enc"
  W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
  mkdir -p "$W/db"
  # снимки баз без остановки служб (sqlite .backup — согласованная копия)
  for db in /etc/x-ui/x-ui.db /root/YadrenoVPN/database/vpn_bot.db $(find /root/pamir-vpn-miniapp -name "*.db" -size +0 2>/dev/null); do
    [ -f "$db" ] || continue
    out="$W/db/$(echo "$db" | sed 's#^/##; s#/#__#g')"
    sqlite3 "$db" ".backup '$out'" && sqlite3 "$out" "PRAGMA integrity_check;" | grep -qx ok || { echo "$(date -u +%F\ %T) ОШИБКА снимка $db"; exit 1; }
  done
  # настройки и скрипты (без кэшей, логов и venv)
  tar -czf "$W/files.tar.gz" --ignore-failed-read --warning=no-file-changed \
    --exclude='*/venv/*' --exclude='*/__pycache__/*' --exclude='*.log' --exclude='*/node_modules/*' --exclude='*.bak*' \
    /etc/nginx /etc/letsencrypt /usr/local/x-ui/bin/config.json /etc/x-ui/install-result.env \
    /root/YadrenoVPN/config.py /root/YadrenoVPN/.env /root/YadrenoVPN/custom_extensions \
    /root/pamir-vpn-miniapp/backend/.env /root/*.py /root/*.sh /root/cert \
    /etc/systemd/system/*.service /etc/systemd/system/*.timer /etc/cron.d 2>/dev/null || true
  crontab -l > "$W/crontab.txt" 2>/dev/null || true
  tar -czf - -C "$W" db files.tar.gz crontab.txt | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:"$KEY" -out "$W/$NAME"
  mkdir -p "$LOCAL"; chmod 700 "$LOCAL"; cp "$W/$NAME" "$LOCAL/"
  ls -1t "$LOCAL"/mognu-*.enc | tail -n +4 | xargs -r rm -f
  res=$(remote "put $NAME" < "$W/$NAME") || { echo "$(date -u +%F\ %T) ОШИБКА отправки: $res (копия есть в $LOCAL)"; exit 1; }
  echo "$(date -u +%F\ %T) $res; баз: $(ls "$W/db" | wc -l), локально $LOCAL"
  ;;
list)
  remote list
  ;;
ssh-port)
  # на сервере-приёмнике: принимать ssh ещё и на другом порту (пересылка ядром на 22, переживает перезагрузку)
  P="${2:?Укажите порт: bash mognu_backup.sh ssh-port 2222}"
  R="iptables -t nat -C PREROUTING -p tcp --dport $P -j REDIRECT --to-ports 22 2>/dev/null || iptables -t nat -A PREROUTING -p tcp --dport $P -j REDIRECT --to-ports 22"
  sh -c "$R"
  printf '[Unit]\nDescription=Mognu: ssh also on port %s\nAfter=network-online.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/sh -c "%s"\n[Install]\nWantedBy=multi-user.target\n' "$P" "$R" > /etc/systemd/system/mognu-ssh-port.service
  systemctl daemon-reload && systemctl enable mognu-ssh-port >/dev/null 2>&1
  echo "ssh принимается и на порту $P (и после перезагрузки)."
  ;;
*)
  sed -n 2,19p "$0"
  ;;
esac
