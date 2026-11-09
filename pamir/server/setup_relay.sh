#!/usr/bin/env bash
# Ретранслятор: когда IP основного сервера заблокирован в России, другой сервер с незаблокированным IP
# просто пересылает соединения на основной (ядром, iptables DNAT — без лишних программ). Люди подключаются
# к ретранслятору, трафик по-прежнему выходит с основного сервера. Свой VPN ретранслятора (порт 443) не трогает.
#
#   65535 → основной:65535   «Испания-1»
#   4443  → основной:4443    «Испания-2»
#   8443  → основной:443     сайт mognu.app и источник для CDN «LTE Обход» (nginx основного сервера, по SNI)
#   2097  → основной:2096    подписка (на будущее; 2096 здесь занят своей панелью)
#
#   bash setup_relay.sh            включить или проверить (повторный запуск ничего не дублирует)
#   bash setup_relay.sh --undo     убрать пересылку
set -eu
MAIN="${MAIN:-78.17.158.230}"
MAP="65535:65535 4443:4443 8443:443 2097:2096"
UNIT=/etc/systemd/system/mognu-relay.service
SELF=/usr/local/sbin/mognu-relay.sh

rules() {  # $1 = -A (добавить, если нет) или -D (убрать)
  local op="$1" from to
  for pair in $MAP; do
    from="${pair%%:*}"; to="${pair##*:}"
    for spec in "nat PREROUTING -p tcp --dport $from -j DNAT --to-destination $MAIN:$to" \
                "filter FORWARD -p tcp -d $MAIN --dport $to -j ACCEPT" \
                "filter FORWARD -p tcp -s $MAIN --sport $to -j ACCEPT"; do
      set -- $spec; local table="$1"; shift
      if [ "$op" = "-A" ]; then
        iptables -t "$table" -C "$@" 2>/dev/null || { [ "$table" = filter ] && iptables -t filter -I "$@" || iptables -t "$table" -A "$@"; }
      else
        while iptables -t "$table" -C "$@" 2>/dev/null; do iptables -t "$table" -D "$@"; done
      fi
    done
  done
  local m="nat POSTROUTING -p tcp -d $MAIN -j MASQUERADE"
  set -- $m; shift
  if [ "$op" = "-A" ]; then iptables -t nat -C "$@" 2>/dev/null || iptables -t nat -A "$@"
  else while iptables -t nat -C "$@" 2>/dev/null; do iptables -t nat -D "$@"; done; fi
}

if [ "${1:-}" = "--undo" ]; then
  rules -D
  systemctl disable --now mognu-relay 2>/dev/null || true
  rm -f "$UNIT" "$SELF"; systemctl daemon-reload
  echo "Пересылка убрана."
  exit 0
fi

if [ "${1:-}" != "--apply-only" ]; then
  for pair in $MAP; do
    from="${pair%%:*}"
    if ss -ltn | awk '{print $4}' | grep -qE "[:.]$from\$"; then echo "Порт $from уже занят на этом сервере — ничего не меняю."; exit 1; fi
  done
fi

sysctl -qw net.ipv4.ip_forward=1
grep -qs '^net.ipv4.ip_forward *= *1' /etc/sysctl.d/99-mognu-relay.conf || echo 'net.ipv4.ip_forward = 1' > /etc/sysctl.d/99-mognu-relay.conf
rules -A

if [ "${1:-}" != "--apply-only" ]; then
  # после перезагрузки правила ставятся заново
  install -m 755 "$0" "$SELF"
  cat > "$UNIT" <<EOF
[Unit]
Description=Mognu relay to main server
After=network-online.target ufw.service
Wants=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
Environment=MAIN=$MAIN
ExecStart=/bin/bash $SELF --apply-only
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable mognu-relay >/dev/null 2>&1
  echo "Готово: пересылка включена и переживёт перезагрузку."
  echo "Проверка с другого сервера:  for p in 65535 4443 8443; do timeout 5 bash -c \"</dev/tcp/$(hostname -I | awk '{print $1}')/\$p\" && echo \$p ok || echo \$p нет; done"
fi
