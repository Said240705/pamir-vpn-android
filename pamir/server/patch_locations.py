#!/usr/bin/env python3
"""Статус каждой локации (подключения панели) на странице статуса сайта.

Меняет bot/services/mini_app_api.py:
- _check_all_servers_health() после проверки панели берёт её включённые подключения
  и узлы и сохраняет состояние каждой локации в таблицу location_health;
- _public_status_handler() отдаёт локации вместо одной строки на панель (для серверов
  без сохранённых локаций — как раньше).
Перед изменением кладёт копию рядом: mini_app_api.py.bak-locations.
"""
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN/bot/services/mini_app_api.py")
src = PATH.read_text(encoding="utf-8")
if "_collect_locations" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

EDITS = [
    # 1. После проверки панели — собрать её локации
    (
        """        try:
            client = get_client_from_server_data(full_servers[server_id])
            await asyncio.wait_for(client.get_online_client_emails(), timeout=SERVER_HEALTH_TIMEOUT)
            is_up = True
        except Exception:
            is_up = False
""",
        """        client = None
        try:
            client = get_client_from_server_data(full_servers[server_id])
            await asyncio.wait_for(client.get_online_client_emails(), timeout=SERVER_HEALTH_TIMEOUT)
            is_up = True
        except Exception:
            is_up = False

        locations = None
        if is_up:
            try:
                locations = await asyncio.wait_for(_collect_locations(client), timeout=SERVER_HEALTH_TIMEOUT)
            except Exception:
                logger.warning('server_health: не удалось получить локации сервера %s', server_id, exc_info=True)
""",
    ),
    # 2. После записи статуса панели — записать локации
    (
        """                    (server_id, new_status, new_status),
                )
            conn.commit()
""",
        """                    (server_id, new_status, new_status),
                )
            conn.commit()

        _store_locations(server_id, locations, is_up)
""",
    ),
    # 3. Вспомогательные функции перед обработчиком публичного статуса
    (
        """async def _public_status_handler(request: web.Request) -> web.Response:
""",
        '''LOCATION_HEALTH_DDL = (
    "CREATE TABLE IF NOT EXISTS location_health ("
    "server_id INTEGER NOT NULL, "
    "inbound_id INTEGER NOT NULL, "
    "name TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'unknown', "
    "sort INTEGER NOT NULL DEFAULT 0, "
    "checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "PRIMARY KEY (server_id, inbound_id)"
    ")"
)


def _flag(value, default=True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


async def _collect_locations(client) -> list:
    """
    Локации панели для страницы статуса: включённые подключения (inbound) с их
    названием. Подключение на узле — состояние узла (online/offline), иначе
    подключение работает на самой панели, и раз она ответила — 'up'.
    """
    inbounds = await client.get_inbounds()
    nodes = {}
    get_nodes = getattr(client, 'get_nodes', None)
    if get_nodes is not None:
        try:
            for node in await get_nodes():
                try:
                    nodes[int(node.get('id'))] = node
                except (AttributeError, TypeError, ValueError):
                    continue
        except Exception:
            logger.warning('server_health: не удалось получить узлы панели', exc_info=True)

    locations = []
    for inbound in inbounds:
        if not _flag(inbound.get('enable'), True):
            continue
        status = 'up'
        node_id = inbound.get('nodeId', inbound.get('node_id'))
        if node_id not in (None, 0, '', '0'):
            try:
                node = nodes.get(int(node_id))
            except (TypeError, ValueError):
                node = None
            if node is None:
                status = 'unknown'
            elif not _flag(node.get('enable'), True):
                continue
            else:
                status = 'up' if str(node.get('status') or '').lower() == 'online' else 'down'
        try:
            inbound_id = int(inbound.get('id'))
        except (TypeError, ValueError):
            continue
        name = ' '.join(str(inbound.get('remark') or '').split()) or f'Локация {inbound_id}'
        try:
            sort = int(inbound.get('subSortIndex') or 0)
        except (TypeError, ValueError):
            sort = 0
        locations.append({'inbound_id': inbound_id, 'name': name, 'status': status, 'sort': sort})
    return locations


def _store_locations(server_id: int, locations, is_up: bool) -> None:
    """
    Сохраняет локации сервера одной транзакцией. Панель не ответила — все её
    локации 'down'; локации не получили — оставляем прошлые.
    """
    from database.connection import get_db

    with get_db() as conn:
        try:
            conn.execute(LOCATION_HEALTH_DDL)
            if not is_up:
                conn.execute(
                    "UPDATE location_health SET status = 'down', checked_at = CURRENT_TIMESTAMP "
                    "WHERE server_id = ?",
                    (server_id,),
                )
            elif locations is not None:
                conn.execute("DELETE FROM location_health WHERE server_id = ?", (server_id,))
                conn.executemany(
                    "INSERT INTO location_health (server_id, inbound_id, name, status, sort, checked_at) "
                    "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    [(server_id, l['inbound_id'], l['name'], l['status'], l['sort']) for l in locations],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception('server_health: не удалось сохранить локации сервера %s', server_id)


async def _public_status_handler(request: web.Request) -> web.Response:
''',
    ),
    # 4. Публичный статус: прочитать локации
    (
        """                "WHERE s.is_active = 1 ORDER BY s.id"
            ).fetchall()
""",
        """                "WHERE s.is_active = 1 ORDER BY s.id"
            ).fetchall()
            conn.execute(LOCATION_HEALTH_DDL)
            location_rows = conn.execute(
                "SELECT l.server_id, l.name, l.status, l.checked_at "
                "FROM location_health l JOIN servers s ON s.id = l.server_id "
                "WHERE s.is_active = 1 ORDER BY l.server_id, l.sort, l.inbound_id"
            ).fetchall()
""",
    ),
    # 5. Публичный статус: локации вместо строки панели
    (
        """        servers = [
            {
                'name': r['name'],
                'status': r['status'] or 'unknown',
                'checked_at': r['checked_at'],
            }
            for r in rows
        ]
""",
        """        locations_by_server = {}
        for l in location_rows:
            locations_by_server.setdefault(l['server_id'], []).append({
                'name': l['name'],
                'status': l['status'] or 'unknown',
                'checked_at': l['checked_at'],
            })
        servers = []
        for r in rows:
            if r['id'] in locations_by_server:
                servers.extend(locations_by_server[r['id']])
            else:
                servers.append({
                    'name': r['name'],
                    'status': r['status'] or 'unknown',
                    'checked_at': r['checked_at'],
                })
""",
    ),
]

for old, new in EDITS:
    count = src.count(old)
    if count != 1:
        sys.exit(f"Не нашёл нужное место в файле (найдено {count} раз), ничего не меняю:\n{old[:200]}")
    src = src.replace(old, new)

backup = PATH.with_name(PATH.name + ".bak-locations")
shutil.copy2(PATH, backup)
PATH.write_text(src, encoding="utf-8")
print(f"Готово. Копия старого файла: {backup}")
