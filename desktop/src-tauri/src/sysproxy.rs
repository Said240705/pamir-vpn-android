//! Системный прокси Windows (те же настройки, что «Параметры → Сеть → Прокси»): браузеры, Telegram и большинство
//! программ сами пойдут через Mognu. Включаем только свой адрес 127.0.0.1 и только на время подключения; при выходе
//! и при следующем запуске (если программу закрыли аварийно) — выключаем, но только если там всё ещё наш адрес.

#[cfg(windows)]
mod imp {
    use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_WRITE};
    use winreg::RegKey;

    const PATH: &str = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings";
    // адреса, которые всегда напрямую: сам компьютер и домашняя сеть
    const BYPASS: &str = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>";

    fn refresh() {
        use windows_sys::Win32::Networking::WinInet::{InternetSetOptionW, INTERNET_OPTION_REFRESH, INTERNET_OPTION_SETTINGS_CHANGED};
        // без этого уже открытые программы узнают о смене прокси только после перезапуска
        unsafe {
            InternetSetOptionW(std::ptr::null(), INTERNET_OPTION_SETTINGS_CHANGED, std::ptr::null(), 0);
            InternetSetOptionW(std::ptr::null(), INTERNET_OPTION_REFRESH, std::ptr::null(), 0);
        }
    }

    pub fn set(port: u16) -> Result<(), String> {
        let key = RegKey::predef(HKEY_CURRENT_USER).open_subkey_with_flags(PATH, KEY_READ | KEY_WRITE).map_err(|e| e.to_string())?;
        key.set_value("ProxyServer", &format!("127.0.0.1:{port}")).map_err(|e| e.to_string())?;
        key.set_value("ProxyOverride", &BYPASS.to_string()).map_err(|e| e.to_string())?;
        key.set_value("ProxyEnable", &1u32).map_err(|e| e.to_string())?;
        refresh();
        Ok(())
    }

    /// Выключает прокси, если он указывает на 127.0.0.1 (наш). Чужой прокси (корпоративный и т. п.) не трогаем.
    pub fn clear_ours() -> Result<(), String> {
        let key = RegKey::predef(HKEY_CURRENT_USER).open_subkey_with_flags(PATH, KEY_READ | KEY_WRITE).map_err(|e| e.to_string())?;
        let server: String = key.get_value("ProxyServer").unwrap_or_default();
        let enabled: u32 = key.get_value("ProxyEnable").unwrap_or(0);
        if enabled == 1 && server.starts_with("127.0.0.1:") {
            key.set_value("ProxyEnable", &0u32).map_err(|e| e.to_string())?;
            refresh();
        }
        Ok(())
    }
}

// на других системах (сборка для проверки на Linux) — ничего не делаем
#[cfg(not(windows))]
mod imp {
    pub fn set(_port: u16) -> Result<(), String> { Ok(()) }
    pub fn clear_ours() -> Result<(), String> { Ok(()) }
}

pub use imp::{clear_ours, set};
