//! Обновление Mognu для Windows: новые версии — пре-релизы desktop-v<версия> на GitHub с установщиком Mognu-Setup-*.exe.
//! Проверка — список релизов GitHub; скачивание — установщик с проверкой размера и SHA-256 из самого GitHub (поле digest).
//! Пока Mognu подключён, всё идёт через подключение — так обновление работает и там, где GitHub закрыт.
//! Установка — после выхода программы: маленький командный файл ждёт, пока mognu.exe закроется, тихо ставит новую
//! версию поверх (ключ и настройки остаются) и запускает её снова.

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

/// Новая версия, если она есть; None — эта самая свежая.
pub async fn check(proxy: Option<u16>) -> Result<Option<Update>, String> {
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
pub async fn download(u: &Update, proxy: Option<u16>) -> Result<std::path::PathBuf, String> {
    let bytes = client(proxy, Duration::from_secs(600))?
        .get(&u.url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .bytes()
        .await
        .map_err(|e| e.to_string())?;
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

/// Запускает тихую установку, которая дождётся выхода этой копии и потом откроет новую версию.
/// Сама программа после этого должна выйти (main.rs: quit).
#[cfg(windows)]
pub fn install_after_exit(setup: &std::path::Path) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let pid = std::process::id();
    let script = std::env::temp_dir().join("mognu-update.cmd");
    // ждём, пока закроется эта копия (иначе файлы программы заняты), ставим тихо (/S) и запускаем новую
    let body = format!(
        "@echo off\r\n:wait\r\ntasklist /FI \"PID eq {pid}\" | find \"{pid}\" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n\"{setup}\" /S\r\nstart \"\" \"{exe}\"\r\ndel \"%~f0\"\r\n",
        setup = setup.display(),
        exe = exe.display(),
    );
    std::fs::write(&script, body).map_err(|e| e.to_string())?;
    std::process::Command::new("cmd")
        .arg("/C")
        .arg(&script)
        .creation_flags(CREATE_NO_WINDOW | DETACHED_PROCESS)
        .spawn()
        .map_err(|e| format!("не удалось запустить установку: {e}"))?;
    Ok(())
}

#[cfg(not(windows))]
pub fn install_after_exit(_setup: &std::path::Path) -> Result<(), String> {
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
