//! Права администратора для режима «весь трафик»: адаптер Mognu (wintun) Windows создаёт только с ними.
//! Программа обычно работает без них; когда человек включает режим, она один раз перезапускается через окно
//! подтверждения Windows (UAC) — новая копия с правами сразу подключается, старая закрывается.

/// Аргумент запуска «это перезапуск с правами»: подождать, пока закроется прежняя копия, и сразу подключиться.
pub const HANDOFF: &str = "--handoff";

#[cfg(windows)]
pub fn is_elevated() -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::Security::{GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY};
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};
    unsafe {
        let mut token: HANDLE = std::ptr::null_mut();
        if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) == 0 {
            return false;
        }
        let mut el = TOKEN_ELEVATION { TokenIsElevated: 0 };
        let mut len = 0u32;
        let ok = GetTokenInformation(
            token,
            TokenElevation,
            &mut el as *mut _ as *mut core::ffi::c_void,
            std::mem::size_of::<TOKEN_ELEVATION>() as u32,
            &mut len,
        );
        CloseHandle(token);
        ok != 0 && el.TokenIsElevated != 0
    }
}

/// Запускает эту же программу с правами администратора. Ok(false) — человек нажал «Нет» в окне Windows.
/// hidden — окно не показывать (стартовали вместе с Windows и ещё сидим в трее).
#[cfg(windows)]
pub fn relaunch(hidden: bool) -> Result<bool, String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::Shell::{ShellExecuteExW, SHELLEXECUTEINFOW};
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    let wide = |s: &std::ffi::OsStr| s.encode_wide().chain(Some(0)).collect::<Vec<u16>>();
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let file = wide(exe.as_os_str());
    let verb = wide(std::ffi::OsStr::new("runas"));
    let args = if hidden { format!("{HANDOFF} {}", crate::autostart::ARG) } else { HANDOFF.to_string() };
    let args = wide(std::ffi::OsStr::new(&args));
    unsafe {
        let mut info: SHELLEXECUTEINFOW = std::mem::zeroed();
        info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
        info.lpVerb = verb.as_ptr();
        info.lpFile = file.as_ptr();
        info.lpParameters = args.as_ptr();
        info.nShow = SW_SHOWNORMAL;
        if ShellExecuteExW(&mut info) != 0 {
            return Ok(true);
        }
    }
    // ERROR_CANCELLED (1223) — отказ в окне подтверждения, это не ошибка
    let err = std::io::Error::last_os_error();
    if err.raw_os_error() == Some(1223) { Ok(false) } else { Err(err.to_string()) }
}

// сборка для проверки на Linux: режима «весь трафик» там нет
#[cfg(not(windows))]
pub fn is_elevated() -> bool { false }
#[cfg(not(windows))]
pub fn relaunch(_hidden: bool) -> Result<bool, String> { Err("только для Windows".into()) }
