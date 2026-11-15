#!/usr/bin/env bash
# Платёжные API (ЮKassa) с основного сервера — через Финляндию.
#
# IP основного сервера заблокирован в России, и трафик Испания → российские сервисы не проходит: бот получал
# «Connection timeout to host https://api.yookassa.ru» — оплата СБП/картой не создавалась. С 15.11 ЮKassa не
# отвечает и Финляндии, поэтому цепочка: основной → Финляндия → российский сервер → ЮKassa. Основной сервер
# подменяет адрес назначения (iptables OUTPUT DNAT) на порт Финляндии, Финляндия пересылает на тот же порт
# российского сервера, а он — на настоящий адрес ЮKassa (всё — setup_relay.sh с NAME=mognu-relay-pay*).
# TLS, сертификат и имя сайта не меняются — бот ничего не замечает. Переживает перезагрузку.
#
#   на российском сервере (адреса — из getent ahostsv4 api.yookassa.ru):
#     NAME=mognu-relay-pay1 MAIN=185.71.78.133  MAP="8447:443" bash setup_relay.sh
#     NAME=mognu-relay-pay2 MAIN=109.235.165.99 MAP="8448:443" bash setup_relay.sh
#   на Финляндии:
#     NAME=mognu-relay-pay1 MAIN=185.198.152.202 MAP="8447:8447" bash setup_relay.sh
#     NAME=mognu-relay-pay2 MAIN=185.198.152.202 MAP="8448:8448" bash setup_relay.sh
#   на основном сервере:
#     bash setup_pay_via_relay.sh            включить (повторный запуск ничего не дублирует)
#     bash setup_pay_via_relay.sh --undo     убрать
# Если ЮKassa сменит адреса (getent ahostsv4 api.yookassa.ru покажет новые) — добавить их в PAIRS, на Финляндии
# и на российском сервере.
set -eu
RELAY="${RELAY:-31.77.6.71}"
PAIRS="${PAIRS:-185.71.78.133:8447 109.235.165.99:8448}"   # адрес ЮKassa : порт на Финляндии
UNIT=/etc/systemd/system/mognu-pay-via-relay.service
SELF=/usr/local/sbin/mognu-pay-via-relay.sh

rules() {  # $1 = -A или -D
  for pair in $PAIRS; do
    ip="${pair%%:*}"; port="${pair##*:}"
    set -- -p tcp -d "$ip" --dport 443 -j DNAT --to-destination "$RELAY:$port"
    if [ "$op" = "-A" ]; then iptables -t nat -C OUTPUT "$@" 2>/dev/null || iptables -t nat -A OUTPUT "$@"
    else while iptables -t nat -C OUTPUT "$@" 2>/dev/null; do iptables -t nat -D OUTPUT "$@"; done; fi
  done
}

if [ "${1:-}" = "--undo" ]; then
  op=-D; rules
  systemctl disable --now mognu-pay-via-relay 2>/dev/null || true
  rm -f "$UNIT" "$SELF"; systemctl daemon-reload
  echo "Убрано: ЮKassa снова напрямую."
  exit 0
fi

if [ "${1:-}" != "--apply-only" ]; then
  for pair in $PAIRS; do
    port="${pair##*:}"
    timeout 5 bash -c "</dev/tcp/$RELAY/$port" 2>/dev/null || { echo "Финляндия $RELAY:$port не отвечает — сначала пересылка на Финляндии (см. начало файла)"; exit 1; }
  done
fi
op=-A; rules

if [ "${1:-}" != "--apply-only" ]; then
  install -m 755 "$0" "$SELF"
  cat > "$UNIT" <<EOF
[Unit]
Description=Mognu: payment APIs via relay $RELAY
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
Environment=RELAY=$RELAY
Environment="PAIRS=$PAIRS"
ExecStart=/bin/bash $SELF --apply-only
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl enable --now mognu-pay-via-relay >/dev/null 2>&1
  curl -so /dev/null -m 8 -w "проверка: api.yookassa.ru → %{http_code} за %{time_total}s (401 — ЮKassa отвечает)\n" https://api.yookassa.ru/v3/payments || true
fi
