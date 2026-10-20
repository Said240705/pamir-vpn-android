//! Ядро Xray: отдельная программа xray.exe рядом с mognu.exe (externalBin в tauri.conf.json).
//! Запускаем её с готовым конфигом из интерфейса, держим последние строки её вывода для «Отчёта о проблеме»
//! и всегда останавливаем при выходе, чтобы не оставить висящий процесс.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

const LOG_LINES: usize = 400;

#[derive(Default)]
pub struct Core {
    child: Option<Child>,
    log: Arc<Mutex<VecDeque<String>>>,
}

fn xray_path() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().ok_or("нет папки программы")?;
    let name = if cfg!(windows) { "xray.exe" } else { "xray" };
    let p = dir.join(name);
    if p.exists() { Ok(p) } else { Err(format!("не найден {}", p.display())) }
}

impl Core {
    pub fn running(&mut self) -> bool {
        match self.child.as_mut().map(|c| c.try_wait()) {
            Some(Ok(None)) => true,
            _ => false,
        }
    }

    pub fn log_tail(&self) -> String {
        self.log.lock().map(|l| l.iter().cloned().collect::<Vec<_>>().join("\n")).unwrap_or_default()
    }

    fn push(log: &Arc<Mutex<VecDeque<String>>>, line: String) {
        if let Ok(mut l) = log.lock() {
            if l.len() >= LOG_LINES { l.pop_front(); }
            l.push_back(line);
        }
    }

    /// Записывает конфиг в папку данных программы и запускает xray. Если ядро сразу упало
    /// (неверный конфиг, порт занят) — возвращает его последние строки, чтобы показать человеку.
    pub fn start(&mut self, data_dir: &PathBuf, config: &str) -> Result<(), String> {
        self.stop();
        std::fs::create_dir_all(data_dir).map_err(|e| e.to_string())?;
        let cfg = data_dir.join("config.json");
        std::fs::write(&cfg, config).map_err(|e| e.to_string())?;
        let mut cmd = Command::new(xray_path()?);
        cmd.arg("run").arg("-c").arg(&cfg)
            .env("XRAY_LOCATION_ASSET", data_dir)
            .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = cmd.spawn().map_err(|e| format!("не удалось запустить ядро: {e}"))?;
        #[cfg(windows)]
        bind_to_app(&child);
        if let Ok(mut l) = self.log.lock() { l.clear(); }
        for pipe in [child.stdout.take().map(|p| Box::new(p) as Box<dyn std::io::Read + Send>),
                     child.stderr.take().map(|p| Box::new(p) as Box<dyn std::io::Read + Send>)].into_iter().flatten() {
            let log = self.log.clone();
            std::thread::spawn(move || {
                for line in BufReader::new(pipe).lines().map_while(Result::ok) { Core::push(&log, line); }
            });
        }
        self.child = Some(child);
        // ядро, которому не понравился конфиг, выходит сразу
        std::thread::sleep(Duration::from_millis(700));
        if !self.running() {
            let tail = self.log_tail();
            self.child = None;
            return Err(if tail.is_empty() { "ядро сразу остановилось".into() } else { tail });
        }
        Ok(())
    }

    pub fn stop(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}

/// Windows: ядро в «задании» (Job Object) с флагом «убить всех при закрытии». Если mognu.exe упадёт или его снимут
/// через диспетчер задач, Windows сама остановит и xray.exe — иначе он остался бы работать в фоне без окна.
#[cfg(windows)]
fn bind_to_app(child: &Child) {
    use std::os::windows::io::AsRawHandle;
    use std::sync::OnceLock;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    // задание одно на всю программу и живёт до её конца: его закрывает сама Windows вместе с процессом
    static JOB: OnceLock<usize> = OnceLock::new();
    let job = *JOB.get_or_init(|| unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return 0;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const core::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        job as usize
    });
    if job != 0 {
        unsafe { AssignProcessToJobObject(job as _, child.as_raw_handle() as _) };
    }
}

impl Drop for Core {
    fn drop(&mut self) { self.stop(); }
}
