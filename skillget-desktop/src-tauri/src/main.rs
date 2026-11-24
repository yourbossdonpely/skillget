// Tauri shell: starts the bundled Node engine on a free loopback port, then
// shows the UI once /api/health answers. The Node process is killed on exit.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

struct Engine {
    child: Mutex<Option<Child>>,
}

/// Startup trace at %TEMP%\skillget-desktop.log (the release build has no console).
fn trace(msg: &str) {
    use std::io::Write as _;
    let path = std::env::temp_dir().join("skillget-desktop.log");
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(file, "{msg}");
    }
}

/// First free loopback port in our range.
fn free_port() -> u16 {
    for port in 5179..5210 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    5179
}

fn health_ok(port: u16) -> bool {
    let addr: SocketAddr = match format!("127.0.0.1:{port}").parse() {
        Ok(addr) => addr,
        Err(_) => return false,
    };
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(400)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    if stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut buf = [0u8; 64];
    match stream.read(&mut buf) {
        Ok(n) if n > 12 => String::from_utf8_lossy(&buf[..n]).contains("200 OK"),
        _ => false,
    }
}

/// Windows hands back verbatim `\\?\C:\...` paths; Node cannot resolve a module
/// argument in that form, so the prefix is stripped before it reaches the engine.
fn plain(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    match text.strip_prefix(r"\\?\") {
        Some(rest) => PathBuf::from(rest),
        None => path,
    }
}

/// In a debug build the engine runs from the project directory with Vite.
fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn main() {
    tauri::Builder::default()
        .manage(Engine {
            child: Mutex::new(None),
        })
        .setup(|app| {
            trace("setup: start");
            let port = free_port();
            let state_dir = app.path().app_local_data_dir()?.join("state");
            std::fs::create_dir_all(&state_dir)?;
            trace(&format!("setup: port={port} state={}", state_dir.display()));

            let dev = cfg!(debug_assertions);
            let (node, script, cwd, frontend) = if dev {
                let root = project_root();
                let node = which_node();
                (
                    node,
                    root.join("server").join("index.mjs"),
                    root,
                    None::<PathBuf>,
                )
            } else {
                // Tauri copies `bundle.resources` entries under `<resource_dir>/resources`.
                let res = plain(app.path().resource_dir()?.join("resources"));
                (
                    res.join("node.exe"),
                    res.join("server").join("index.mjs"),
                    res.clone(),
                    Some(res.join("frontend")),
                )
            };

            let mut cmd = Command::new(&node);
            cmd.arg(&script)
                .current_dir(&cwd)
                .env("SKILLGET_PORT", port.to_string())
                .env("SKILLGET_STATE", &state_dir)
                .stdout(engine_log())
                .stderr(engine_log());
            if !dev {
                cmd.arg("--prod");
            }
            if let Some(dir) = &frontend {
                cmd.env("SKILLGET_FRONTEND", dir);
            }
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x0800_0000;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            trace(&format!("setup: spawn {} {}", node.display(), script.display()));
            let child = match cmd.spawn() {
                Ok(child) => child,
                Err(err) => {
                    trace(&format!("setup: spawn failed: {err}"));
                    return Err(Box::new(err) as Box<dyn std::error::Error>);
                }
            };
            *app.state::<Engine>().child.lock().unwrap() = Some(child);

            let deadline = Instant::now() + Duration::from_secs(45);
            let mut ready = false;
            while Instant::now() < deadline {
                if health_ok(port) {
                    ready = true;
                    break;
                }
                std::thread::sleep(Duration::from_millis(250));
            }
            trace(&format!("setup: engine ready={ready}"));
            if !ready {
                eprintln!("engine did not answer on port {port}");
            }
            let _ = std::fs::write(state_dir.join("port"), port.to_string());

            // Fit the window to the display (logical pixels) so it never opens
            // larger than the screen on scaled desktops.
            let mut width = 1320.0_f64;
            let mut height = 880.0_f64;
            if let Ok(Some(monitor)) = app.primary_monitor() {
                let scale = monitor.scale_factor();
                let size = monitor.size();
                let logical_w = f64::from(size.width) / scale;
                let logical_h = f64::from(size.height) / scale;
                width = width.min(logical_w - 60.0).max(900.0);
                height = height.min(logical_h - 110.0).max(620.0);
                trace(&format!("setup: window {width}x{height} (screen {logical_w}x{logical_h} @ {scale})"));
            }

            let url: Url = format!("http://127.0.0.1:{port}").parse()?;
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("skillget")
                .inner_size(width, height)
                .min_inner_size(900.0, 620.0)
                .build()?;
            trace("setup: window built");
            Ok(())
        })
        .build(tauri::generate_context!())
        .map_err(|err| {
            trace(&format!("build failed: {err}"));
            err
        })
        .expect("failed to build skillget")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Engine>().child.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}

/// Debug builds spawn the `node` already on PATH.
fn which_node() -> PathBuf {
    PathBuf::from("node")
}

/// Engine stdout/stderr, kept beside the install state for support.
fn engine_log() -> Stdio {
    let path = std::env::temp_dir().join("skillget-desktop-engine.log");
    match std::fs::OpenOptions::new().create(true).append(true).open(path) {
        Ok(file) => Stdio::from(file),
        Err(_) => Stdio::null(),
    }
}
