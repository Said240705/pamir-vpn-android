#!/bin/bash
# Вход для третьего LTE-сервера через Beget CDN: CDN ходит на o-bg.pamirlink.ru:443,
# правило 443 отдаёт это имя сайтам (127.0.0.1:8443), nginx по пути /api/stream/ передаёт в Xray 127.0.0.1:2058.
# Яндекс (yacdn/o-ya → 2056) и Билайн (o-bee → 2057) не трогает. При любой ошибке всё откатывает.
#   bash setup_beget_cdn.sh            сделать
#   bash setup_beget_cdn.sh --check    только проверить, ничего не меняя
exec > >(tee /root/beget_cdn.log) 2>&1
echo "старт: $(date)"
D=o-bg.pamirlink.ru; IP=78.17.158.230; PORT=2058; P=/api/stream/
CONF=/etc/nginx/sites-enabled/$D

check() {
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 --resolve $D:443:127.0.0.1 https://$D/); echo "$D (главная): $c"
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 --resolve $D:443:127.0.0.1 https://$D$P); echo "$D$P: $c (502 — входа $PORT в панели ещё нет; 400/404 — вход есть)"
  echo "Xray на $PORT: $(ss -tln | grep -c "127.0.0.1:$PORT ") (1 — слушает)"
}
[ "$1" = "--check" ] && { check; exit 0; }

B=/root/merge_backup_$(date +%Y%m%d)/before_beget; mkdir -p $B; cp -a /etc/nginx/nginx.conf $B/
rollback() { echo "!!! ОТКАТ: $1"; rm -f $CONF; cp -a $B/nginx.conf /etc/nginx/nginx.conf; nginx -t && systemctl reload nginx; echo "nginx после отката: $(systemctl is-active nginx)"; exit 1; }

[ -e $CONF ] && { echo "$CONF уже есть — ничего не делаю. Проверка:"; check; exit 0; }
r=$(getent ahostsv4 $D | awk '{print $1}' | head -1); echo "$D → $r"
[ "$r" = "$IP" ] || { echo "!!! $D ещё не указывает на $IP — создай A-запись (без оранжевого облака), подожди 5–15 минут и запусти снова"; exit 1; }
ss -tln | grep -q "127.0.0.1:$PORT " && echo "порт $PORT уже слушает Xray — ок" || echo "порт $PORT пока свободен — вход в панели создашь после"

W=$(awk '/root /{gsub(";","",$2); print $2; exit}' /etc/nginx/sites-enabled/default); W=${W:-/var/www/html}; mkdir -p $W
certbot certonly --webroot -w $W -d $D --cert-name $D --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring \
  || certbot certonly --nginx -d $D --cert-name $D --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring \
  || { echo "!!! не удалось получить сертификат — ничего не менял"; exit 1; }

cat > $CONF <<NG
# mognu: Beget CDN -> xhttp ($P -> 127.0.0.1:$PORT)
server {
    listen 127.0.0.1:8443 ssl http2;
    server_name $D *.begetcdn.cloud;
    ssl_certificate /etc/letsencrypt/live/$D/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$D/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location $P {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate" always;
        add_header X-Accel-Buffering no always;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        gzip off;
        proxy_connect_timeout 60s;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        client_max_body_size 0;
    }
    location / {
        default_type text/html;
        return 200 '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>Media Gateway</title></head><body><h1>Media Gateway</h1><p>Content delivery endpoint.</p></body></html>';
    }
}
NG

python3 - <<PY || rollback "не удалось поправить правило 443"
p = '/etc/nginx/nginx.conf'; s = open(p).read()
if '$D' not in s:
    anchor = "        default               pamir_xray;"
    assert anchor in s, 'нет правила 443 (pamir-443-router)'
    s = s.replace(anchor, "        $D     pamir_web;\n" + anchor, 1)
    open(p, 'w').write(s)
print('правило 443: $D -> сайты')
PY
nginx -t || rollback "ошибка в конфиге nginx"
systemctl reload nginx; sleep 2

ok=1
for d in origin.mognu.app app.pamirlink.ru; do c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 --resolve $d:443:127.0.0.1 https://$d/); echo "сайт $d: $c"; [ "$c" = "000" ] && ok=0; done
c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 --resolve $D:443:127.0.0.1 https://$D/); echo "$D (главная): $c"; [ "$c" = "200" ] || ok=0
v=$(echo | timeout 8 openssl s_client -connect 127.0.0.1:443 -servername www.amazon.com 2>/dev/null | grep -ci amazon); echo "VPN Испании через 443: $v"; [ "$v" -gt 0 ] || ok=0
[ $ok = 1 ] || rollback "что-то не отвечает"
check
echo "ГОТОВО: $(date). Бэкап nginx.conf: $B"
