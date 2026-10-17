#!/bin/bash
# Проверка LTE-сервера через CDN из России: временный клиент Xray с конфигом, сохранённым на основном сервере
# (python3 mognu_cdn_test.py 2058 --dump /root/lte3_client.json → скопировать сюда). Открывает YouTube, качает 5 МБ,
# меряет пинг и отдачу, потом выключает клиент. Ничего не меняет, Xray кладёт в /root/xray-test.
#   bash mognu_ru_client_test.sh /root/lte3_client.json
CFG=${1:-/root/lte3_client.json}; D=/root/xray-test; X=$D/xray; VER=v26.6.27
[ -f "$CFG" ] || { echo "нет конфига $CFG — сначала скопируй его с основного сервера"; exit 1; }
if [ ! -x $X ]; then
  mkdir -p $D && echo "качаю Xray $VER…"
  curl -fsSL -o $D/x.zip "https://github.com/XTLS/Xray-core/releases/download/$VER/Xray-linux-64.zip" || { echo "!!! не скачался Xray"; exit 1; }
  python3 -c "import zipfile;zipfile.ZipFile('$D/x.zip').extract('xray','$D')" && chmod +x $X && rm -f $D/x.zip
fi
$X version | head -1
$X run -c "$CFG" > $D/log.txt 2>&1 & P=$!; sleep 2
S="--socks5-hostname 127.0.0.1:10899"
for i in 1 2 3 4 5; do curl -s -o /dev/null --max-time 10 $S -w '%{time_total}\n' https://www.google.com/generate_204; done | sort -n | awk '{a[NR]=$1*1000} END{if(NR) printf "пинг: %.0f мс (лучший %.0f)\n", a[int((NR+1)/2)], a[1]; else print "пинг: нет ответа"}'
curl -s -o /dev/null --max-time 25 $S -w 'YouTube: %{http_code} за %{time_total}s\n' https://www.youtube.com/
curl -s -o /dev/null --max-time 30 $S -w '5 МБ: %{http_code} за %{time_total}s (%{speed_download} байт/с)\n' 'https://speed.cloudflare.com/__down?bytes=5000000'
head -c 1000000 /dev/zero | curl -s -o /dev/null --max-time 30 $S --data-binary @- -w 'отдача 1 МБ: %{http_code} за %{time_total}s (%{speed_upload} байт/с)\n' https://speed.cloudflare.com/__up
kill $P 2>/dev/null; sleep 1
echo "--- ошибки клиента Xray:"; grep -iE 'fail|error|reject|timeout' $D/log.txt | tail -6 | cut -c1-220
