// Mognu для компьютера: окно с интерфейсом (ui/), ядро Xray (core.rs) и системный прокси Windows (sysproxy.rs).
// Сетевые запросы к API и подписке идут отсюда, а не из окна: так нет ограничений браузера (CORS) и можно
// пустить запрос через уже работающее подключение.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod core;
mod elevate;
mod sysproxy;
mod update;

use std::collections::HashMap;
use std::net::TcpListener;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};

struct AppState {
    core: Mutex<core::Core>,
}

/// Пункт меню в трее «Подключить / Отключить» — текст меняется вместе с состоянием.
struct Tray {
    toggle: MenuItem<tauri::Wry>,
}

const TRAY_ON: &[u8] = include_bytes!("../icons/tray-on.png");
const TRAY_OFF: &[u8] = include_bytes!("../icons/tray-off.png");

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// «Выйти» из трея: отключиться, вернуть прокси и закрыть программу совсем (закрытие окна только прячет его).
fn quit(app: &AppHandle) {
    let _ = sysproxy::clear_ours();
    if let Ok(mut c) = app.state::<AppState>().core.lock() {
        c.stop();
    }
    app.exit(0);
}

/// Значок в трее: салатовый — подключено, серый — нет; подсказка с сервером; текст пункта «Подключить/Отключить».
#[tauri::command]
fn tray_state(app: AppHandle, connected: bool, label: String) {
    if let Some(t) = app.tray_by_id("main") {
        if let Ok(img) = Image::from_bytes(if connected { TRAY_ON } else { TRAY_OFF }) {
            let _ = t.set_icon(Some(img));
        }
        let tip = if connected { format!("Mognu — подключено · {label}") } else { "Mognu — не подключено".to_string() };
        let _ = t.set_tooltip(Some(tip));
    }
    if let Some(tray) = app.try_state::<Tray>() {
        let _ = tray.toggle.set_text(if connected { "Отключить" } else { "Подключить" });
    }
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Открыть Mognu", true, None::<&str>)?;
    let toggle = MenuItem::with_id(app, "toggle", "Подключить", true, None::<&str>)?;
    let exit = MenuItem::with_id(app, "quit", "Выйти", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &toggle, &PredefinedMenuItem::separator(app)?, &exit])?;
    TrayIconBuilder::with_id("main")
        .icon(Image::from_bytes(TRAY_OFF)?)
        .tooltip("Mognu — не подключено")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, e| match e.id.as_ref() {
            "open" => show_main(app),
            // подключение живёт в окне (ui/app.js): просим его нажать большую кнопку
            "toggle" => {
                let _ = app.emit("tray-toggle", ());
            }
            "quit" => quit(app),
            _ => {}
        })
        .on_tray_icon_event(|tray, e| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = e {
                show_main(tray.app_handle());
            }
        })
        .build(app)?;
    app.manage(Tray { toggle });
    Ok(())
}

#[derive(Serialize)]
struct Ports {
    socks: u16,
    http: u16,
}

/// Два свободных порта на 127.0.0.1 для входов ядра.
#[tauri::command]
fn free_ports() -> Result<Ports, String> {
    let a = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let b = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    Ok(Ports { socks: a.local_addr().map_err(|e| e.to_string())?.port(), http: b.local_addr().map_err(|e| e.to_string())?.port() })
}

#[tauri::command]
fn core_start(app: tauri::AppHandle, state: State<AppState>, config: String) -> Result<(), String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    state.core.lock().map_err(|e| e.to_string())?.start(&dir, &config)
}

#[tauri::command]
fn core_stop(state: State<AppState>) -> Result<(), String> {
    let _ = sysproxy::clear_ours();
    state.core.lock().map_err(|e| e.to_string())?.stop();
    Ok(())
}

#[tauri::command]
fn core_running(state: State<AppState>) -> bool {
    state.core.lock().map(|mut c| c.running()).unwrap_or(false)
}

#[tauri::command]
fn core_note(state: State<AppState>, text: String) {
    if let Ok(c) = state.core.lock() {
        c.note(text);
    }
}

#[tauri::command]
fn core_log(state: State<AppState>) -> String {
    state.core.lock().map(|c| c.log_tail()).unwrap_or_default()
}

#[tauri::command]
fn proxy_set(port: Option<u16>) -> Result<(), String> {
    match port {
        Some(p) => sysproxy::set(p),
        None => sysproxy::clear_ours(),
    }
}

#[derive(Deserialize)]
struct HttpReq {
    url: String,
    #[serde(default)]
    method: Option<String>,
    #[serde(default)]
    headers: HashMap<String, String>,
    #[serde(default)]
    body: Option<String>,
    /// порт HTTP-входа работающего ядра: запрос пойдёт через подключение
    #[serde(default)]
    proxy: Option<u16>,
    #[serde(default)]
    timeout_ms: Option<u64>,
}

#[derive(Serialize)]
struct HttpRes {
    status: u16,
    body: String,
}

#[tauri::command]
async fn http(req: HttpReq) -> Result<HttpRes, String> {
    let mut b = reqwest::Client::builder()
        .timeout(Duration::from_millis(req.timeout_ms.unwrap_or(15_000)))
        .connect_timeout(Duration::from_secs(8));
    b = match req.proxy {
        Some(p) => b.proxy(reqwest::Proxy::all(format!("http://127.0.0.1:{p}")).map_err(|e| e.to_string())?),
        None => b.no_proxy(),
    };
    let client = b.build().map_err(|e| e.to_string())?;
    let method = reqwest::Method::from_bytes(req.method.as_deref().unwrap_or("GET").as_bytes()).map_err(|e| e.to_string())?;
    let mut r = client.request(method, &req.url);
    for (k, v) in &req.headers {
        r = r.header(k, v);
    }
    if let Some(body) = req.body {
        r = r.body(body);
    }
    let res = r.send().await.map_err(|e| e.to_string())?;
    let status = res.status().as_u16();
    let body = res.text().await.map_err(|e| e.to_string())?;
    Ok(HttpRes { status, body })
}

/// Время TCP-подключения к серверу, мс; None — не ответил за 3 секунды.
#[tauri::command]
async fn tcp_ping(host: String, port: u16) -> Option<u32> {
    let started = Instant::now();
    match tokio::time::timeout(Duration::from_secs(3), tokio::net::TcpStream::connect((host.as_str(), port))).await {
        Ok(Ok(_)) => Some(started.elapsed().as_millis() as u32),
        _ => None,
    }
}

#[derive(Serialize)]
struct Demo {
    sub: String,
    connect: bool,
    tun: bool,
}

/// Проверочный запуск на GitHub (desktop-build.yml): MOGNU_DEMO_SUB — тестовая подписка вместо входа в аккаунт,
/// MOGNU_DEMO_CONNECT=1 — сразу подключиться. У обычного человека этих переменных нет, и команда возвращает None.
#[tauri::command]
fn demo() -> Option<Demo> {
    let sub = std::env::var("MOGNU_DEMO_SUB").ok().filter(|s| s.starts_with("https://"))?;
    let on = |k: &str| std::env::var(k).map(|v| v == "1").unwrap_or(false);
    Some(Demo { sub, connect: on("MOGNU_DEMO_CONNECT"), tun: on("MOGNU_DEMO_TUN") })
}

#[derive(Serialize)]
struct Launch {
    /// у программы есть права администратора (нужны для режима «весь трафик»)
    elevated: bool,
    /// это перезапуск с правами ради режима — окно сразу подключается
    handoff: bool,
}

#[tauri::command]
fn launch_info() -> Launch {
    Launch { elevated: elevate::is_elevated(), handoff: std::env::args().any(|a| a == elevate::HANDOFF) }
}

/// Перезапуск с правами администратора: Windows спросит разрешение. Если человек согласился — эта копия
/// отключается и закрывается, новая подключится сама. false — человек отказался, всё остаётся как было.
#[tauri::command]
fn relaunch_elevated(app: AppHandle) -> Result<bool, String> {
    let ok = elevate::relaunch()?;
    if ok {
        quit(&app);
    }
    Ok(ok)
}

/// Есть ли новая версия Mognu для Windows; proxy — порт HTTP-входа ядра, если подключены.
#[tauri::command]
async fn update_check(proxy: Option<u16>) -> Result<Option<update::Update>, String> {
    update::check(proxy).await
}

/// Скачать и проверить новую версию, затем выйти: установка пройдёт тихо и откроет обновлённый Mognu.
#[tauri::command]
async fn update_install(app: AppHandle, u: update::Update, proxy: Option<u16>) -> Result<(), String> {
    let setup = update::download(&u, proxy).await?;
    update::install_after_exit(&setup)?;
    quit(&app);
    Ok(())
}

#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("tg://")) {
        return Err("только https и tg ссылки".into());
    }
    open::that_detached(url).map_err(|e| e.to_string())
}

fn main() {
    // если в прошлый раз программу закрыли аварийно, прокси мог остаться включённым на наш порт — без ядра
    // интернет у человека тогда не работает
    let _ = sysproxy::clear_ours();

    // перезапуск с правами: прежняя копия ещё закрывается — подождём, иначе защита от второго окна закроет эту
    if std::env::args().any(|a| a == elevate::HANDOFF) {
        std::thread::sleep(Duration::from_millis(2500));
    }

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(AppState { core: Mutex::new(core::Core::default()) })
        .setup(|app| {
            build_tray(app)?;
            Ok(())
        })
        // крестик окна не выходит из программы и не отключает: окно прячется, Mognu остаётся в трее
        .on_window_event(|w, e| {
            if let WindowEvent::CloseRequested { api, .. } = e {
                api.prevent_close();
                let _ = w.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![free_ports, core_start, core_stop, core_running, core_log, core_note, proxy_set, http, tcp_ping, open_url, demo, tray_state, launch_info, relaunch_elevated, update_check, update_install])
        .build(tauri::generate_context!())
        .expect("Mognu не запустился");

    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            let _ = sysproxy::clear_ours();
            if let Ok(mut c) = handle.state::<AppState>().core.lock() {
                c.stop();
            }
        }
    });
}
