//! Обновление Mognu для Windows: новые версии — пре-релизы desktop-v<версия> на GitHub с установщиком Mognu-Setup-*.exe.
//! Проверка — список релизов GitHub; скачивание — установщик с проверкой размера и SHA-256 из самого GitHub (поле digest).
//! Пока Mognu подключён, всё идёт через подключение — так обновление работает и там, где GitHub закрыт.
//! Установка: программа сама снимает прокси и останавливает ядро, запускает установщик тихо (/S) с /MOGNURUN и выходит.
//! Установщик закрывает оставшуюся копию, ставит новую версию поверх (ключ и настройки остаются) и по /MOGNURUN
//! открывает её снова (installer/hooks.nsh). До 0.4.3 это делал командный файл .cmd: cmd читает его в кодировке OEM,
//! и при русских буквах в имени пользователя (а значит, и в пути к TEMP) путь к установщику ломался — обновление
//! тихо не ставилось. Установщик теперь запускается напрямую, с путём в Юникоде.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::time::Duration;

const RELEASES: &str = "https://api.github.com/repos/Said240705/pamir-vpn-android/releases?per_page=30";

#[derive(Serialize, Deserialize, Clone)]
pub struct Update {
    pub version: String,
    pub url: String,
    pub size: u64,
    pub sha256: String,
}

#[derive(Deserialize)]
struct Release {
    tag_name: String,
    #[serde(default)]
    draft: bool,
    #[serde(default)]
    assets: Vec<Asset>,
}

#[derive(Deserialize)]
struct Asset {
    name: String,
    browser_download_url: String,
    size: u64,
    #[serde(default)]
    digest: Option<String>,
}

fn client(proxy: Option<u16>, timeout: Duration) -> Result<reqwest::Client, String> {
    let mut b = reqwest::Client::builder()
        .timeout(timeout)
        .connect_timeout(Duration::from_secs(10))
        .user_agent(concat!("Mognu-Desktop/", env!("CARGO_PKG_VERSION")));
    b = match proxy {
        Some(p) => b.proxy(reqwest::Proxy::all(format!("http://127.0.0.1:{p}")).map_err(|e| e.to_string())?),
        None => b.no_proxy(),
    };
    b.build().map_err(|e| e.to_string())
}

fn parse_version(v: &str) -> Option<(u32, u32, u32)> {
    let mut it = v.trim_start_matches('v').split('.').map(|p| p.parse::<u32>().ok());
    Some((it.next()??, it.next()??, it.next().flatten().unwrap_or(0)))
}

/// Зеркала на наших сайтах (sync-release.py кладёт туда установщик и windows.json) — если GitHub не открывается.
const MIRRORS: [&str; 2] = ["https://mognu.app", "https://app.pamirlink.ru"];

#[derive(Deserialize)]
struct MirrorMeta {
    version: String,
    file: String,
    size: u64,
    sha256: String,
}

/// Новая версия, если она есть; None — эта самая свежая. Сначала GitHub, при ошибке — зеркала.
pub async fn check(proxy: Option<u16>) -> Result<Option<Update>, String> {
    let err = match check_github(proxy).await {
        Ok(u) => return Ok(u),
        Err(e) => e,
    };
    let current = parse_version(env!("CARGO_PKG_VERSION")).ok_or("версия программы")?;
    for host in MIRRORS {
        let Ok(res) = client(proxy, Duration::from_secs(12))?.get(format!("{host}/download/windows.json")).send().await else { continue };
        let Ok(text) = res.text().await else { continue };
        let Ok(m) = serde_json::from_str::<MirrorMeta>(&text) else { continue };
        let Some(v) = parse_version(&m.version) else { continue };
        // имя файла только из букв, цифр, точек и дефисов — без путей
        if m.sha256.len() != 64 || !m.file.chars().all(|c| c.is_ascii_alphanumeric() || ".-_".contains(c)) {
            continue;
        }
        if v <= current {
            return Ok(None);
        }
        let version = format!("{}.{}.{}", v.0, v.1, v.2);
        return Ok(Some(Update { version, url: format!("{host}/download/{}", m.file), size: m.size, sha256: m.sha256.to_lowercase() }));
    }
    Err(err)
}

async fn check_github(proxy: Option<u16>) -> Result<Option<Update>, String> {
    let current = parse_version(env!("CARGO_PKG_VERSION")).ok_or("версия программы")?;
    let text = client(proxy, Duration::from_secs(20))?
        .get(RELEASES)
        .header("Accept", "application/vnd.github+json")
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .text()
        .await
        .map_err(|e| e.to_string())?;
    let releases: Vec<Release> = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let mut best: Option<((u32, u32, u32), Update)> = None;
    for r in releases.into_iter().filter(|r| !r.draft) {
        let Some(v) = r.tag_name.strip_prefix("desktop-v").and_then(parse_version) else { continue };
        if v <= current || best.as_ref().is_some_and(|(b, _)| v <= *b) {
            continue;
        }
        // установщик и его сумма из GitHub; без суммы не обновляем — нечем проверить, что скачалось именно оно
        let Some(a) = r.assets.into_iter().find(|a| a.name.starts_with("Mognu-Setup-") && a.name.ends_with(".exe")) else { continue };
        let Some(sha) = a.digest.as_deref().and_then(|d| d.strip_prefix("sha256:")).map(str::to_lowercase) else { continue };
        let version = format!("{}.{}.{}", v.0, v.1, v.2);
        best = Some((v, Update { version, url: a.browser_download_url, size: a.size, sha256: sha }));
    }
    Ok(best.map(|(_, u)| u))
}

/// Скачивает установщик во временную папку и проверяет размер и SHA-256. Возвращает путь к файлу.
/// progress(скачано, всего) вызывается по ходу — для полоски в окне.
pub async fn download(u: &Update, proxy: Option<u16>, progress: impl Fn(u64, u64)) -> Result<std::path::PathBuf, String> {
    let mut res = client(proxy, Duration::from_secs(600))?
        .get(&u.url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?;
    let mut bytes: Vec<u8> = Vec::with_capacity(u.size as usize);
    let mut last = 0u64;
    while let Some(chunk) = res.chunk().await.map_err(|e| e.to_string())? {
        bytes.extend_from_slice(&chunk);
        let done = bytes.len() as u64;
        // не чаще, чем раз в ~100 КБ: окну хватает, а событий не тысячи
        if done - last >= 100_000 || done == u.size {
            last = done;
            progress(done, u.size);
        }
    }
    if bytes.len() as u64 != u.size {
        return Err(format!("скачалось не полностью ({} из {} байт)", bytes.len(), u.size));
    }
    let sum = Sha256::digest(&bytes).iter().map(|b| format!("{b:02x}")).collect::<String>();
    if sum != u.sha256 {
        return Err("контрольная сумма не совпала — файл повреждён или подменён".into());
    }
    let path = std::env::temp_dir().join(format!("Mognu-Setup-{}.exe", u.version));
    std::fs::write(&path, &bytes).map_err(|e| e.to_string())?;
    Ok(path)
}

/// Запускает тихую установку с повторным открытием программы (/MOGNURUN, installer/hooks.nsh).
/// Перед этим программа уже сняла прокси и остановила ядро; сразу после — выходит (main.rs: update_apply).
#[cfg(windows)]
pub fn run_installer(setup: &std::path::Path) -> Result<(), String> {
    std::process::Command::new(setup)
        .args(["/S", "/MOGNURUN"])
        .spawn()
        .map_err(|e| format!("не удалось запустить установку: {e}"))?;
    Ok(())
}

#[cfg(not(windows))]
pub fn run_installer(_setup: &std::path::Path) -> Result<(), String> {
    Err("только для Windows".into())
}

#[cfg(test)]
mod tests {
    use super::parse_version;

    #[test]
    fn versions_compare_as_numbers() {
        assert!(parse_version("desktop-v0.10.0".trim_start_matches("desktop-")) > parse_version("0.9.9"));
        assert_eq!(parse_version("v1.2"), Some((1, 2, 0)));
        assert_eq!(parse_version("x"), None);
    }
}
