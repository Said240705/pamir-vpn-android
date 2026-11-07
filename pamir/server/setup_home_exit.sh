#!/usr/bin/env bash
# «🏠 Россия · Домой» — шаг 1: «выход» на российском сервере (AdminVPS).
#
# Ставит Xray, который принимает соединения ТОЛЬКО с основного сервера (Испания) на порту 8443
# (VLESS + Reality) и выпускает трафик в интернет с российского IP. Порт 443, nginx и сайт не трогает.
# Ключи соединения пишет в /root/mognu-home.txt (их нужно перенести на основной сервер; в чат не присылать).
# Торренты и локальные адреса блокируются — чтобы на российский IP не пришли жалобы.
#
#   bash setup_home_exit.sh          установить или проверить
#   bash setup_home_exit.sh --undo   остановить и убрать выход (Xray останется установленным, но выключенным)
set -eu   # без pipefail: «… | head -1» обрывает вывод, и это не ошибка

MAIN_IP="78.17.158.230"
PORT=8443
SNI="www.microsoft.com"
CONF=/usr/local/etc/xray/config.json
OUT=/root/mognu-home.txt
DROPIN=/etc/systemd/system/xray.service.d/mognu-home-firewall.conf

fw_rules() {  # $1 = -I (добавить) или -D (убрать)
  iptables "$1" INPUT -p tcp --dport "$PORT" ! -s "$MAIN_IP" -j DROP 2>/dev/null || true
  ip6tables "$1" INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null || true
}

if [[ "${1:-}" == "--undo" ]]; then
  systemctl disable --now xray 2>/dev/null || true
  rm -f "$DROPIN"; systemctl daemon-reload
  fw_rules -D
  echo "Выход «Домой» остановлен. Конфиг оставлен: $CONF"
  exit 0
fi

if ss -ltn | awk '{print $4}' | grep -qE ":$PORT\$" && ! systemctl is-active --quiet xray; then
  echo "Порт $PORT уже занят другой программой — ничего не меняю."; exit 1
fi

echo "== 1. Xray"
if ! command -v xray >/dev/null; then
  bash -c "$(curl -fsSL --max-time 60 https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
fi
xray version 2>/dev/null | sed -n 1p || true

echo "== 2. Ключи соединения"
if [[ -f "$OUT" ]]; then
  echo "Уже есть $OUT — использую их (повторный запуск ничего не ломает)."
  # shellcheck disable=SC1090
  source "$OUT"
else
  HOME_UUID=$(xray uuid)
  KEYS=$(xray x25519)
  HOME_PRIV=$(echo "$KEYS" | awk -F': *' '/[Pp]rivate/{print $2; exit}')
  HOME_PUB=$(echo "$KEYS" | awk -F': *' '/[Pp]ublic|Password/{print $2; exit}')
  HOME_SID=$(openssl rand -hex 8)
  [[ -n "$HOME_UUID" && -n "$HOME_PRIV" && -n "$HOME_PUB" ]] || { echo "Не получилось создать ключи — ничего не меняю."; exit 1; }
  ( umask 077; cat > "$OUT" ) <<EOF
HOME_ADDR=185.198.152.202
HOME_PORT=$PORT
HOME_SNI=$SNI
HOME_UUID=$HOME_UUID
HOME_PUB=$HOME_PUB
HOME_SID=$HOME_SID
HOME_PRIV=$HOME_PRIV
EOF
fi

echo "== 3. Конфиг"
[[ -f "$CONF" ]] && cp "$CONF" "$CONF.bak-mognu-home-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$(dirname "$CONF")"
( umask 027; cat > "$CONF" ) <<EOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "tag": "from-spain", "listen": "0.0.0.0", "port": $PORT, "protocol": "vless",
    "settings": { "clients": [{ "id": "$HOME_UUID", "flow": "xtls-rprx-vision" }], "decryption": "none" },
    "streamSettings": { "network": "tcp", "security": "reality",
      "realitySettings": { "dest": "$SNI:443", "serverNames": ["$SNI"], "privateKey": "$HOME_PRIV", "shortIds": ["$HOME_SID"] } },
    "sniffing": { "enabled": true, "destOverride": ["http", "tls", "quic"] }
  }],
  "outbounds": [ { "protocol": "freedom", "tag": "direct" }, { "protocol": "blackhole", "tag": "block" } ],
  "routing": { "rules": [
    { "type": "field", "ip": ["geoip:private"], "outboundTag": "block" },
    { "type": "field", "protocol": ["bittorrent"], "outboundTag": "block" }
  ] }
}
EOF
# служба Xray работает от пользователя xray — конфиг (в нём закрытый ключ) читает только он и root
chown root:xray "$CONF" 2>/dev/null || chown root:nogroup "$CONF"
chmod 640 "$CONF"
xray run -test -config "$CONF" >/dev/null && echo "конфиг проверен Xray: ok"

echo "== 4. Только основной сервер может подключиться"
mkdir -p "$(dirname "$DROPIN")"
cat > "$DROPIN" <<EOF
[Service]
ExecStartPre=+/bin/sh -c 'iptables -C INPUT -p tcp --dport $PORT ! -s $MAIN_IP -j DROP 2>/dev/null || iptables -I INPUT -p tcp --dport $PORT ! -s $MAIN_IP -j DROP'
ExecStartPre=+/bin/sh -c 'ip6tables -C INPUT -p tcp --dport $PORT -j DROP 2>/dev/null || ip6tables -I INPUT -p tcp --dport $PORT -j DROP || true'
EOF
systemctl daemon-reload
systemctl enable xray >/dev/null 2>&1
systemctl restart xray
sleep 2
systemctl is-active xray
ss -ltn | grep -q ":$PORT " && echo "слушает порт $PORT: ok"
iptables -C INPUT -p tcp --dport "$PORT" ! -s "$MAIN_IP" -j DROP && echo "чужим порт $PORT закрыт: ok"

echo
echo "Готово. Параметры для основного сервера — в $OUT (строки HOME_ADDR … HOME_SID; HOME_PRIV там не нужен)."
echo "Не присылайте этот файл в чат — перенесите его на основной сервер (шаг 2)."
