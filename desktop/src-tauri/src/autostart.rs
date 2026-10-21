//! Запуск вместе с Windows: строка «Mognu VPN» в HKCU\…\Run (только для этого пользователя, без прав администратора).
//! Программа стартует с --autostart: окно не показывается, Mognu сразу уходит в трей (и подключается, если включено).
//! Имя строки совпадает с названием программы — деинсталлятор Tauri удаляет её сам (installer.nsi, ветка Run).

/// Аргумент запуска «стартовали вместе с Windows»: окно не показывать.
pub const ARG: &str = "--autostart";
#[cfg(windows)]
const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
#[cfg(windows)]
const NAME: &str = "Mognu VPN";

#[cfg(windows)]
pub fn enabled() -> bool {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};
    RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(RUN)
        .and_then(|k| k.get_value::<String, _>(NAME))
        .is_ok()
}

#[cfg(windows)]
pub fn set(on: bool) -> Result<(), String> {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};
    let (key, _) = RegKey::predef(HKEY_CURRENT_USER).create_subkey(RUN).map_err(|e| e.to_string())?;
    if on {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        key.set_value(NAME, &format!("\"{}\" {ARG}", exe.display())).map_err(|e| e.to_string())
    } else {
        match key.delete_value(NAME) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(e.to_string()),
            _ => Ok(()),
        }
    }
}

// сборка для проверки на Linux
#[cfg(not(windows))]
pub fn enabled() -> bool { false }
#[cfg(not(windows))]
pub fn set(_on: bool) -> Result<(), String> { Err("только для Windows".into()) }
