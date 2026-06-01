from __future__ import annotations

import base64
import ctypes
import datetime as dt
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import webview

try:
    import winreg
except ImportError:  # Non-Windows development environment
    winreg = None


APP_NAME = "DelagR"
APP_VERSION = "2.1.2"

GITHUB_OWNER = "fletcherholt"
GITHUB_REPO = "DelagR"
GITHUB_LATEST_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# Per-OS release asset names used by the in-app updater (must match CI uploads).
ASSET_FOR_OS = {
    "windows": "DelagR.exe",
    "macos": "DelagR-macos",
    "linux": "DelagR-linux",
}


def current_os() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


OS = current_os()
OS_LABEL = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}[OS]
OS_SHORT = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}


# Which OSes have a real, safe equivalent for each tweak. Features not supported
# on the current OS are still shown in the UI but greyed with an honest badge.
SUPPORT: dict[str, set[str]] = {
    "wifi_autoscan": {"windows"},
    "tcp_autotuning": {"windows", "linux"},
    "nagle": {"windows", "macos"},
    "net_throttle": {"windows"},
    "wifi_power_save": {"windows", "linux"},
    "optimize_dns": {"windows", "macos", "linux"},
    "game_bar": {"windows"},
    "delivery_optimization": {"windows", "macos"},  # macOS Content Caching
    "location_tracking": {"windows"},
}

ICON_ICO_BASE64 = (
    "AAABAAEAEBAAAAAAIABYAgAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAh9JREFUeJyNks+L"
    "EmEcxp/3nVFw2mQWDNsI2iIiRKg9lRgESngeNg+BiFfTS/+BCF63S3TrUBv9Mli2H3uIQNYlNvTSJfEQGgSRNdAPMWzm"
    "nfeN9123HLLaB76XmXk+PN/nOwAgCCAwmXPGnLgdnBf26n0hxV0m/iVKJk4dBNfNKG7MH8Jr7uKl8x1SXL39u3QKgILg"
    "SSSKIQfOfnyLz8zBNfZjAgCoECCEwHVdBAIBH4B6AKrhMJaCYXxFAGPugoBgH9XgcQ7mOMpcq9XQ6XR2oJz/BiRCBqy5"
    "ME7Z7/CNhLB18CQMCNiOA41ShAxDGfv9PmKxmDJTKnNPdJNo4spUiRXzqNjaf1hkEwnxbHNTPFpfF/l8XrRaLVWa67q"
    "+Eol9a1W8GI/xiQD37t7B8+1tXDIO4NWXDzhfvoxjCwt40+vBNE1kMhmkUilfCiIpu2kGgwGurqwgeuI4zpxewvteH08"
    "3NpBOp2FZFsrlMnK5nIJIm4RQwRg8xlTDkUgERxYXcTF9AY8f1JU5Ho9jOByiUqmoIrvdrir1V4lE16HpujqPpBaLRTX"
    "cW4O1vIxgMKjiFgoFBWq32yiVSvA8b/YKUru3rtfraDabSCaT6grVahWMMWia5kuA6UY552ps2xbZbFaMRiP13PM8NTN"
    "/ZUxJxpX0RqOhSjMMA47j7JQ1ffsp/bGClIyq67rqxBd3r4DJav81S83OJcl7MMsPfwLqBlh+rBKLnQAAAABJRU5ErkJ"
    "ggg=="
)


# --------------------------------------------------------------------------- #
# Privilege + command execution
# --------------------------------------------------------------------------- #
def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0  # type: ignore[attr-defined]


def is_admin() -> bool:
    if OS == "windows":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return is_root()


def relaunch_as_admin() -> bool:
    """Relaunch elevated on Windows.

    Returns True if a new elevated process was started (the caller should close
    this instance), or False if elevation was unavailable or declined.
    """
    if OS != "windows" or is_admin():
        return False

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        executable = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(__file__), *sys.argv[1:]])

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    except Exception:
        return False
    return int(rc) > 32


def run_command(command: str, timeout: int = 25, elevate: bool = False) -> dict[str, object]:
    """Run a shell command. When elevate=True on macOS/Linux (and not already
    root), wrap it in the native auth prompt (osascript / pkexec)."""
    try:
        if elevate and OS != "windows" and not is_root():
            if OS == "macos":
                script = command.replace("\\", "\\\\").replace('"', '\\"')
                args = ["osascript", "-e", f'do shell script "{script}" with administrator privileges']
            else:  # linux
                args = ["pkexec", "/bin/sh", "-lc", command]
            completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        else:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                # No-op on non-Windows; stops a console flashing on the windowed exe.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        return {
            "ok": completed.returncode == 0,
            "out": completed.stdout.strip(),
            "err": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "out": "", "err": str(exc)}


def _unsupported(key: str) -> dict[str, object]:
    return {"ok": False, "out": "", "err": f"{TITLES.get(key, key)} is not available on {OS_LABEL}."}


# --------------------------------------------------------------------------- #
# System detection
# --------------------------------------------------------------------------- #
def detect_primary_interface() -> str:
    if OS == "windows":
        command = (
            'powershell -NoProfile -Command "'
            "Get-NetAdapter | "
            "Where-Object {$_.Status -eq 'Up' -and ($_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN|802.11')} | "
            "Select-Object -First 1 -ExpandProperty Name"
            '"'
        )
        result = run_command(command, timeout=10)
        return str(result["out"]) if result["ok"] and result["out"] else "Wi-Fi"

    if OS == "macos":
        # networksetup uses the *service* name (e.g. "Wi-Fi") for DNS changes.
        result = run_command("networksetup -listallnetworkservices", timeout=10)
        if result["ok"] and result["out"]:
            for line in str(result["out"]).splitlines():
                line = line.strip()
                if "wi-fi" in line.lower() or "airport" in line.lower():
                    return line
        return "Wi-Fi"

    # linux: device name of the default route (e.g. wlan0).
    result = run_command("ip route show default 2>/dev/null | awk '/default/{print $5; exit}'", timeout=10)
    return str(result["out"]) if result["ok"] and result["out"] else "wlan0"


def detect_webview2() -> tuple[bool, str]:
    if OS != "windows":
        return True, "System WebView"
    if winreg is None:
        return False, "Windows-only check"

    locations = [
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True, str(version)
        except OSError:
            continue

    # Filesystem fallback so a present runtime with missing EdgeUpdate keys does
    # not falsely block launch.
    for env_var in ("ProgramFiles(x86)", "ProgramW6432", "ProgramFiles"):
        base = os.environ.get(env_var)
        if not base:
            continue
        app_dir = Path(base) / "Microsoft" / "EdgeWebView" / "Application"
        try:
            versions = [p.name for p in app_dir.iterdir() if p.is_dir() and p.name[0].isdigit()]
        except OSError:
            continue
        if versions:
            return True, sorted(versions)[-1]

    return False, "Not installed"


def detect_compat_layer() -> str | None:
    if OS != "windows":
        return None
    try:
        ntdll = ctypes.WinDLL("ntdll")
        wine_get_version = getattr(ntdll, "wine_get_version", None)
        if wine_get_version is None:
            return None
        wine_get_version.restype = ctypes.c_char_p
        version = wine_get_version()
        if version:
            return f"Wine / Whisky ({version.decode('utf-8', errors='ignore')})"
        return "Wine / Whisky"
    except Exception:
        return None


def install_webview2_runtime() -> dict[str, object]:
    bootstrapper = Path(tempfile.gettempdir()) / "MicrosoftEdgeWebView2Setup.exe"
    command = (
        "powershell -NoProfile -ExecutionPolicy Bypass -Command "
        f'"$ProgressPreference = \'SilentlyContinue\'; '
        f"Invoke-WebRequest -Uri '{WEBVIEW2_BOOTSTRAPPER_URL}' -OutFile '{bootstrapper}'; "
        f"Start-Process -FilePath '{bootstrapper}' -ArgumentList '/silent','/install' -Wait\""
    )
    result = run_command(command, timeout=180)
    if not result["ok"]:
        return result
    installed, version = detect_webview2()
    if installed:
        return {"ok": True, "out": f"WebView2 runtime installed ({version})", "err": ""}
    return {"ok": False, "out": "", "err": "Installer finished, but WebView2 still was not detected."}


# --------------------------------------------------------------------------- #
# Updater
# --------------------------------------------------------------------------- #
def parse_version(value: str) -> tuple[int, ...]:
    value = (value or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def fetch_latest_release() -> dict | None:
    req = urllib.request.Request(
        GITHUB_LATEST_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=12, context=ssl.create_default_context()) as resp:
        return json.load(resp)


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _spawn_swap_and_relaunch(new_file: Path, target: Path) -> None:
    """Spawn a detached helper that waits for this process to exit, replaces the
    running binary with the downloaded one, and relaunches it."""
    pid = os.getpid()
    if OS == "windows":
        helper = Path(tempfile.gettempdir()) / "delagr_update.bat"
        helper.write_text(
            "@echo off\r\n"
            ":loop\r\n"
            f'tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
            "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto loop )\r\n"
            f'move /y "{new_file}" "{target}" >nul\r\n'
            f'start "" "{target}"\r\n'
            'del "%~f0"\r\n',
            encoding="utf-8",
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(["cmd", "/c", str(helper)], creationflags=flags, close_fds=True)
    else:
        helper = Path(tempfile.gettempdir()) / "delagr_update.sh"
        helper.write_text(
            "#!/bin/sh\n"
            f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done\n"
            f'cp "{new_file}" "{target}"\n'
            f'chmod +x "{target}"\n'
            f'"{target}" &\n'
            'rm -- "$0"\n'
        )
        os.chmod(helper, 0o755)
        subprocess.Popen(["/bin/sh", str(helper)], start_new_session=True, close_fds=True)


# --------------------------------------------------------------------------- #
# System snapshot
# --------------------------------------------------------------------------- #
@dataclass
class SystemSnapshot:
    os: str
    os_label: str
    privileged: bool
    interface: str
    webview2_installed: bool
    webview2_version: str
    compat_layer: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "os": self.os,
            "os_label": self.os_label,
            "privileged": self.privileged,
            "interface": self.interface,
            "webview2_installed": self.webview2_installed,
            "webview2_version": self.webview2_version,
            "compat_layer": self.compat_layer,
            "version": APP_VERSION,
        }


def collect_system_snapshot() -> SystemSnapshot:
    installed, version = detect_webview2()
    return SystemSnapshot(
        os=OS,
        os_label=OS_LABEL,
        privileged=is_admin(),
        interface=detect_primary_interface(),
        webview2_installed=installed,
        webview2_version=version,
        compat_layer=detect_compat_layer(),
    )


def diagnostics_path() -> Path:
    desktop = Path.home() / "Desktop"
    target_dir = desktop if desktop.exists() else Path.home()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return target_dir / f"DelagR-diagnostics-{stamp}.txt"


def build_diagnostics_report(snapshot: SystemSnapshot) -> str:
    summary = "\n".join(
        [
            f"App: {APP_NAME} {APP_VERSION}",
            f"Timestamp: {dt.datetime.now().isoformat(timespec='seconds')}",
            f"OS: {snapshot.os_label}",
            f"Elevated: {snapshot.privileged}",
            f"Primary Interface: {snapshot.interface}",
            f"WebView2 / Renderer: {snapshot.webview2_version}",
            f"Compatibility Layer: {snapshot.compat_layer or 'Native'}",
            f"Frozen Build: {getattr(sys, 'frozen', False)}",
            f"Executable: {sys.executable}",
        ]
    )

    if OS == "windows":
        probes = [
            ("whoami", "whoami"),
            ("Windows Version", "ver"),
            ("Wi-Fi Interfaces", "netsh wlan show interfaces"),
            ("TCP Global Settings", "netsh int tcp show global"),
        ]
    elif OS == "macos":
        probes = [
            ("whoami", "whoami"),
            ("macOS Version", "sw_vers"),
            ("Network Services", "networksetup -listallnetworkservices"),
            ("Default Route", "route -n get default"),
        ]
    else:
        probes = [
            ("whoami", "whoami"),
            ("Kernel", "uname -a"),
            ("Interfaces", "ip -brief addr"),
            ("Default Route", "ip route show default"),
        ]

    sections = [("Summary", summary)]
    for title, command in probes:
        sections.append((title, str(run_command(command).get("out", ""))))
    return "\n\n".join(f"== {title} ==\n{body.strip() or '(no output)'}" for title, body in sections) + "\n"


# --------------------------------------------------------------------------- #
# Feature / action catalogue (drives both the UI and game mode)
# --------------------------------------------------------------------------- #
FEATURES = [
    ("wifi_autoscan", "\U0001F4E1", "Wi-Fi Auto-Scan", "Stops the OS from scanning for nearby access points mid-session."),
    ("tcp_autotuning", "\U0001F4F6", "TCP Auto-Tuning", "Locks TCP receive-window behaviour to reduce jitter spikes."),
    ("nagle", "\U0001F680", "Nagle's Algorithm", "Disables packet batching so small packets move immediately."),
    ("net_throttle", "⚡", "Network Throttling", "Removes the multimedia network throttle that can hold packets back."),
    ("wifi_power_save", "\U0001F50B", "Wi-Fi Power Saving", "Keeps the wireless adapter from dropping into low-power latency states."),
    ("optimize_dns", "\U0001F310", "Fast DNS", "Switches to Cloudflare 1.1.1.1 for faster lookups."),
    ("game_bar", "\U0001F3AE", "Game Bar / DVR", "Turns off overlays and background recording overhead."),
    ("delivery_optimization", "\U0001F4E6", "Delivery Optimization", "Stops peer-to-peer OS update sharing while you play."),
    ("location_tracking", "\U0001F4CD", "Location Tracking", "Cuts background location chatter that adds noise."),
]

ACTIONS = [
    ("flush_dns", "\U0001F9F9", "Flush DNS", "Clear cached resolver entries."),
    ("kill_bandwidth_hogs", "\U0001F52A", "Kill Bandwidth Hogs", "Close common upload-heavy background apps."),
    ("reset_network", "\U0001F504", "Reset Network Stack", "Use the heavier reset path for stubborn issues."),
    ("export_diagnostics", "\U0001F9FE", "Export Diagnostics", "Save a support snapshot to your desktop."),
]

TITLES = {key: title for key, _icon, title, _desc in FEATURES}
TITLES.update({key: title for key, _icon, title, _desc in ACTIONS})

BANDWIDTH_HOGS = ["OneDrive", "Dropbox", "Teams", "Slack", "Spotify", "EpicWebHelper", "GoogleUpdate", "MicrosoftEdgeUpdate"]


# --------------------------------------------------------------------------- #
# JS-facing API
# --------------------------------------------------------------------------- #
class DelagRAPI:
    def __init__(self, snapshot: SystemSnapshot):
        self.snapshot = snapshot
        self._latest: dict | None = None

    # -- status / updates --------------------------------------------------- #
    def system_status(self):
        self.snapshot = collect_system_snapshot()
        return {"ok": True, "out": self.snapshot.as_dict(), "err": ""}

    def check_update(self):
        try:
            info = fetch_latest_release()
        except Exception as exc:
            return {"ok": False, "out": "", "err": str(exc)}
        if not info:
            return {"ok": True, "out": {"update": False}, "err": ""}

        latest = str(info.get("tag_name", ""))
        asset_url = None
        want = ASSET_FOR_OS.get(OS)
        for asset in info.get("assets", []):
            if asset.get("name") == want:
                asset_url = asset.get("browser_download_url")
                break

        self._latest = {"latest": latest, "url": info.get("html_url"), "asset_url": asset_url}
        return {
            "ok": True,
            "out": {
                "update": is_newer(latest, APP_VERSION) and bool(asset_url),
                "latest": latest,
                "current": APP_VERSION,
                "url": info.get("html_url"),
            },
            "err": "",
        }

    def apply_update(self):
        info = self._latest
        if not info:
            check = self.check_update()
            info = self._latest if check.get("ok") else None
        if not info:
            return {"ok": False, "out": "", "err": "Could not reach GitHub to fetch the update."}

        if not info.get("asset_url"):
            if info.get("url"):
                webbrowser.open(info["url"])
                return {"ok": True, "out": "Opened the release page (no auto-update build for this OS).", "err": ""}
            return {"ok": False, "out": "", "err": "No downloadable build was found for this OS."}

        if not getattr(sys, "frozen", False):
            webbrowser.open(info.get("url") or "")
            return {"ok": True, "out": "Running from source — opened the release page instead.", "err": ""}

        try:
            suffix = ".exe" if OS == "windows" else ""
            tmp = Path(tempfile.gettempdir()) / f"DelagR-update{suffix}"
            _download(info["asset_url"], tmp)
            _spawn_swap_and_relaunch(tmp, Path(sys.executable))
        except Exception as exc:
            return {"ok": False, "out": "", "err": f"Update failed: {exc}"}

        threading.Timer(0.6, lambda: os._exit(0)).start()
        return {"ok": True, "out": f"Updating to {info.get('latest')} — DelagR will restart.", "err": ""}

    def export_diagnostics(self):
        self.snapshot = collect_system_snapshot()
        target = diagnostics_path()
        try:
            target.write_text(build_diagnostics_report(self.snapshot), encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "out": "", "err": str(exc)}
        return {"ok": True, "out": f"Saved diagnostics to {target}", "err": ""}

    # -- feature toggles ---------------------------------------------------- #
    def wifi_autoscan(self, enable: bool):
        if OS not in SUPPORT["wifi_autoscan"]:
            return _unsupported("wifi_autoscan")
        flag = "no" if enable else "yes"
        return run_command(f'netsh wlan set autoconfig enabled={flag} interface="{self.snapshot.interface}"')

    def tcp_autotuning(self, enable: bool):
        if OS not in SUPPORT["tcp_autotuning"]:
            return _unsupported("tcp_autotuning")
        if OS == "windows":
            level = "disabled" if enable else "normal"
            return run_command(f"netsh int tcp set global autotuninglevel={level}")
        # linux: lock the receive buffer (disable kernel autotuning) when enabled.
        value = "0" if enable else "1"
        return run_command(f"sysctl -w net.ipv4.tcp_moderate_rcvbuf={value}", elevate=True)

    def nagle(self, enable: bool):
        if OS not in SUPPORT["nagle"]:
            return _unsupported("nagle")
        if OS == "windows":
            result = run_command(
                'powershell -NoProfile -Command "'
                "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty InterfaceGuid"
                '"'
            )
            if not result["ok"] or not result["out"]:
                return {"ok": False, "out": "", "err": "Could not find an active network adapter."}
            value = "1" if enable else "0"
            updated = 0
            for guid in str(result["out"]).splitlines():
                guid = guid.strip()
                if not guid:
                    continue
                key = f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\{guid}"
                run_command(f'reg add "{key}" /v TcpAckFrequency /t REG_DWORD /d {value} /f')
                run_command(f'reg add "{key}" /v TCPNoDelay /t REG_DWORD /d {value} /f')
                updated += 1
            return {"ok": True, "out": f"Updated {updated} adapter(s)", "err": ""}
        # macOS: delayed ACK off lowers latency for small packets.
        value = "0" if enable else "3"
        result = run_command(f"sysctl -w net.inet.tcp.delayed_ack={value}", elevate=True)
        if result["ok"]:
            result["out"] = f"Delayed ACK set to {value}"
        return result

    def net_throttle(self, enable: bool):
        if OS not in SUPPORT["net_throttle"]:
            return _unsupported("net_throttle")
        value = "4294967295" if enable else "10"
        key = "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile"
        return run_command(f'reg add "{key}" /v NetworkThrottlingIndex /t REG_DWORD /d {value} /f')

    def wifi_power_save(self, enable: bool):
        if OS not in SUPPORT["wifi_power_save"]:
            return _unsupported("wifi_power_save")
        if OS == "windows":
            value = "0" if enable else "1"
            command = (
                'powershell -NoProfile -Command "'
                f"powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONNECTIVITY_IN_STANDBY {value}; "
                'powercfg /setactive SCHEME_CURRENT"'
            )
            return run_command(command)
        # linux: toggle adapter power saving via iw.
        state = "off" if enable else "on"
        return run_command(f"iw dev {self.snapshot.interface} set power_save {state}", elevate=True)

    def optimize_dns(self, enable: bool):
        if OS not in SUPPORT["optimize_dns"]:
            return _unsupported("optimize_dns")
        iface = self.snapshot.interface
        if OS == "windows":
            if enable:
                run_command(f'netsh interface ip set dns "{iface}" static 1.1.1.1 primary')
                run_command(f'netsh interface ip add dns "{iface}" 1.0.0.1 index=2')
                return {"ok": True, "out": "DNS set to Cloudflare 1.1.1.1", "err": ""}
            run_command(f'netsh interface ip set dns "{iface}" dhcp')
            return {"ok": True, "out": "DNS reverted to DHCP", "err": ""}
        if OS == "macos":
            if enable:
                return run_command(f'networksetup -setdnsservers "{iface}" 1.1.1.1 1.0.0.1', elevate=True)
            return run_command(f'networksetup -setdnsservers "{iface}" empty', elevate=True)
        # linux
        if enable:
            return run_command(f"resolvectl dns {iface} 1.1.1.1 1.0.0.1", elevate=True)
        return run_command(f"resolvectl revert {iface}", elevate=True)

    def game_bar(self, enable: bool):
        if OS not in SUPPORT["game_bar"]:
            return _unsupported("game_bar")
        value = "0" if enable else "1"
        run_command(
            f'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\GameDVR" /v AppCaptureEnabled /t REG_DWORD /d {value} /f'
        )
        run_command(f'reg add "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d {value} /f')
        return {"ok": True, "out": f"Game Bar/DVR {'disabled' if enable else 'enabled'}", "err": ""}

    def delivery_optimization(self, enable: bool):
        if OS not in SUPPORT["delivery_optimization"]:
            return _unsupported("delivery_optimization")
        if OS == "windows":
            value = "0" if enable else "1"
            return run_command(
                f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\DeliveryOptimization\\Config" /v DODownloadMode /t REG_DWORD /d {value} /f'
            )
        # macOS Content Caching is the LAN P2P update-sharing analogue.
        verb = "deactivate" if enable else "activate"
        result = run_command(f"AssetCacheManagerUtil {verb}", elevate=True)
        if result["ok"]:
            result["out"] = f"Content Caching {'disabled' if enable else 'enabled'}"
        return result

    def location_tracking(self, enable: bool):
        if OS not in SUPPORT["location_tracking"]:
            return _unsupported("location_tracking")
        value = "Deny" if enable else "Allow"
        return run_command(
            f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location" /v Value /t REG_SZ /d {value} /f'
        )

    # -- quick actions ------------------------------------------------------ #
    def flush_dns(self):
        if OS == "windows":
            return run_command("ipconfig /flushdns")
        if OS == "macos":
            return run_command("dscacheutil -flushcache; killall -HUP mDNSResponder", elevate=True)
        return run_command("resolvectl flush-caches || systemd-resolve --flush-caches", elevate=True)

    def kill_bandwidth_hogs(self):
        killed: list[str] = []
        for proc in BANDWIDTH_HOGS:
            if OS == "windows":
                result = run_command(f"taskkill /f /im {proc}.exe 2>nul")
                if result["ok"] and "SUCCESS" in str(result["out"]):
                    killed.append(proc)
            else:
                # Bracket the first char so the pattern doesn't match this very
                # command's argv (pgrep/pkill -f self-match trap).
                pattern = f"[{proc[0]}]{proc[1:]}"
                result = run_command(f'pkill -if "{pattern}"')
                if result["ok"]:
                    killed.append(proc)
        return {"ok": True, "out": f"Killed: {', '.join(killed) if killed else 'none running'}", "err": ""}

    def reset_network(self):
        if OS == "windows":
            run_command("netsh winsock reset")
            run_command("netsh int ip reset")
            run_command("ipconfig /flushdns")
            run_command("ipconfig /release")
            run_command("ipconfig /renew")
            return {"ok": True, "out": "Network stack reset. A restart may be required.", "err": ""}
        if OS == "macos":
            return run_command(
                f'dscacheutil -flushcache; killall -HUP mDNSResponder; ipconfig set "{self.snapshot.interface}" DHCP',
                elevate=True,
            )
        return run_command("resolvectl flush-caches; nmcli networking off; nmcli networking on", elevate=True)

    def boost_process(self, process_name: str):
        if OS == "windows":
            result = run_command(
                'powershell -NoProfile -Command "'
                f"$p = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue; "
                "if ($p) { $p | ForEach-Object { $_.PriorityClass = 'High' }; Write-Output 'BOOSTED' } "
                "else { Write-Output 'NOTFOUND' }"
                '"'
            )
        else:
            # Match on the process name (no -f) so we don't self-match the
            # wrapper shell whose argv contains the search string.
            result = run_command(
                f'pids=$(pgrep -i "{process_name}"); '
                'if [ -n "$pids" ]; then renice -n -10 -p $pids >/dev/null 2>&1 && echo BOOSTED; else echo NOTFOUND; fi',
                elevate=True,
            )
        if "BOOSTED" in str(result.get("out", "")):
            return {"ok": True, "out": f"{process_name} set to high priority", "err": ""}
        return {"ok": False, "out": "", "err": f"Process '{process_name}' was not found."}

    # -- master toggle ------------------------------------------------------ #
    def game_mode(self, enable: bool):
        results: list[tuple[str, dict]] = []
        for key, _icon, title, _desc in FEATURES:
            if OS not in SUPPORT[key]:
                continue
            method = getattr(self, key)
            results.append((title, method(enable)))
        if enable:
            results.append(("Flush DNS", self.flush_dns()))
        summary = "; ".join(f"{name}: {'OK' if res.get('ok') else 'FAIL'}" for name, res in results)
        return {"ok": True, "out": summary or "No applicable tweaks on this OS.", "err": ""}


# --------------------------------------------------------------------------- #
# HTML / CSS / JS
# --------------------------------------------------------------------------- #
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Manrope:wght@400;500;600;700&display=swap');

:root {
  --bg: #0D1B2A;
  --bg-2: #1B263B;
  --surface: rgba(27, 38, 59, 0.62);
  --surface-2: rgba(27, 38, 59, 0.42);
  --surface-strong: rgba(13, 27, 42, 0.86);
  --line: rgba(120, 141, 169, 0.30);
  --line-soft: rgba(120, 141, 169, 0.16);
  --text: #E0E1DD;
  --muted: #9FB0C6;
  --slate: #415A77;
  --accent: #778DA9;
  --accent-soft: rgba(119, 141, 169, 0.16);
  --danger: #cf8a93;
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.40);
  --radius: 22px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { min-height: 100%; }
body {
  font-family: 'Manrope', sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(65, 90, 119, 0.30), transparent 34%),
    radial-gradient(circle at top right, rgba(119, 141, 169, 0.22), transparent 36%),
    linear-gradient(160deg, var(--bg), var(--bg-2));
  overflow-x: hidden;
}

body::before, body::after {
  content: '';
  position: fixed;
  width: 28rem;
  height: 28rem;
  border-radius: 999px;
  filter: blur(30px);
  opacity: 0.20;
  pointer-events: none;
  animation: drift 16s ease-in-out infinite;
}
body::before { top: -8rem; left: -6rem; background: #415A77; }
body::after { right: -5rem; bottom: -8rem; background: #778DA9; animation-delay: -6s; }

@keyframes drift {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(1.5rem, -1rem, 0) scale(1.08); }
}

.shell { position: relative; max-width: 1180px; margin: 0 auto; padding: 26px; display: grid; gap: 18px; animation: shellIn 0.9s ease 0.1s both; }
@keyframes shellIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.glass {
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  border-radius: var(--radius);
}

/* update bar */
.update-bar {
  display: none;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(119,141,169,0.22), rgba(65,90,119,0.20));
  border: 1px solid rgba(119,141,169,0.40);
}
.update-bar.show { display: flex; animation: rise 0.4s ease; }
.update-bar .u-left { display: flex; align-items: center; gap: 10px; font-weight: 600; }
.update-bar .u-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 0 rgba(119,141,169,0.6); animation: ping 1.8s ease-in-out infinite; }
@keyframes ping { 0%,100% { box-shadow: 0 0 0 0 rgba(119,141,169,0.5); } 50% { box-shadow: 0 0 0 7px rgba(119,141,169,0); } }
.update-actions { display: flex; gap: 8px; }
.update-btn { border: none; border-radius: 12px; padding: 9px 16px; background: linear-gradient(135deg, #778DA9, #415A77); color: #0D1B2A; font: inherit; font-weight: 800; cursor: pointer; transition: transform 0.2s ease; }
.update-btn:hover { transform: translateY(-1px); }
.update-btn:disabled { opacity: 0.6; cursor: default; transform: none; }
.update-x { border: 1px solid var(--line); border-radius: 12px; padding: 9px 14px; background: transparent; color: var(--muted); font: inherit; cursor: pointer; }

.hero { padding: 28px; display: grid; grid-template-columns: 1.5fr 1fr; gap: 20px; overflow: hidden; }
.eyebrow { display: inline-flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 12px; text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 16px; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.03em; }
h1 { font-size: clamp(2.8rem, 5vw, 4.2rem); line-height: 0.96; margin-bottom: 14px; }
.gradient { background: linear-gradient(120deg, #E0E1DD 0%, #778DA9 55%, #415A77 100%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.lead { color: var(--muted); font-size: 1rem; line-height: 1.65; max-width: 48rem; }
.hero-stats { display: grid; gap: 12px; align-content: start; }
.mini-card { padding: 16px; border-radius: 16px; background: var(--surface-2); border: 1px solid var(--line-soft); }
.mini-card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px; }
.mini-card .value { font-size: 1rem; font-weight: 700; }

.layout { display: grid; grid-template-columns: 300px 1fr; gap: 18px; }
.sidebar, .main { display: grid; gap: 18px; }
.panel { padding: 20px; }
.panel h2 { font-size: 1.1rem; margin-bottom: 14px; }
.system-list { display: grid; gap: 12px; }
.system-item { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 14px; background: var(--surface-2); border: 1px solid var(--line-soft); }
.system-item small { display: block; color: var(--muted); margin-top: 4px; font-size: 12px; }
.pill { display: inline-flex; align-items: center; justify-content: center; min-width: 88px; padding: 8px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; }
.pill.good { background: var(--accent-soft); color: #cfe0f2; }
.pill.warn { background: rgba(207,138,147,0.16); color: #f0c3c9; }
.pill.info { background: rgba(65,90,119,0.30); color: #cfe0f2; }

.game-mode { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 22px; border-radius: 20px; background: linear-gradient(135deg, rgba(119,141,169,0.16), rgba(65,90,119,0.12)); border: 1px solid rgba(119,141,169,0.24); margin-bottom: 18px; }
.game-mode.active { animation: glowPulse 3.4s ease-in-out infinite; border-color: rgba(119,141,169,0.5); }
@keyframes glowPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(119,141,169,0); } 50% { box-shadow: 0 0 36px rgba(119,141,169,0.22); } }

.toggle { position: relative; width: 72px; height: 40px; flex: 0 0 auto; cursor: pointer; }
.toggle input { display: none; }
.slider { position: absolute; inset: 0; border-radius: 999px; background: rgba(120,141,169,0.18); border: 1px solid var(--line-soft); transition: all 0.35s ease; overflow: hidden; }
.slider::before { content: ''; position: absolute; width: 30px; height: 30px; top: 4px; left: 4px; border-radius: 50%; background: linear-gradient(180deg, #E0E1DD, #b9c4d2); box-shadow: 0 8px 24px rgba(0,0,0,0.30); transition: transform 0.35s cubic-bezier(.2,.9,.3,1.1); }
.toggle input:checked + .slider { background: linear-gradient(135deg, #778DA9, #415A77); box-shadow: inset 0 0 0 1px rgba(224,225,221,0.12), 0 10px 28px rgba(119,141,169,0.24); }
.toggle input:checked + .slider::before { transform: translateX(31px); }

.card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 18px; }
.card { position: relative; overflow: hidden; padding: 18px; border-radius: 18px; background: var(--surface-2); border: 1px solid var(--line-soft); transition: transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease; animation: rise 0.55s ease both; }
.card:hover { transform: translateY(-3px); border-color: rgba(119,141,169,0.28); box-shadow: 0 16px 40px rgba(0,0,0,0.26); }
.card.active { border-color: rgba(119,141,169,0.40); box-shadow: 0 14px 34px rgba(119,141,169,0.14); }
.card.disabled { opacity: 0.46; filter: saturate(0.45); }
.card.disabled:hover { transform: none; box-shadow: none; border-color: var(--line-soft); }
.card.disabled .toggle { pointer-events: none; opacity: 0.6; }
.card-grid .card:nth-child(1) { animation-delay: 0.04s; }
.card-grid .card:nth-child(2) { animation-delay: 0.09s; }
.card-grid .card:nth-child(3) { animation-delay: 0.14s; }
.card-grid .card:nth-child(4) { animation-delay: 0.19s; }
.card-grid .card:nth-child(5) { animation-delay: 0.24s; }
.card-grid .card:nth-child(6) { animation-delay: 0.29s; }
.card-grid .card:nth-child(7) { animation-delay: 0.34s; }
.card-grid .card:nth-child(8) { animation-delay: 0.39s; }
.card-grid .card:nth-child(9) { animation-delay: 0.44s; }

.card-top { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 12px; align-items: flex-start; }
.icon { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px; background: var(--accent-soft); font-size: 18px; transition: transform 0.3s ease; }
.card:hover .icon, .action:hover .icon { transform: translateY(-2px) scale(1.08); }
.card.active .icon { background: rgba(119,141,169,0.26); }
.badge { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; padding: 5px 9px; border-radius: 999px; background: rgba(120,141,169,0.16); color: var(--muted); border: 1px solid var(--line-soft); }
.card p, .action p, .sub { color: var(--muted); line-height: 1.55; }
.card h3, .action h3 { margin-bottom: 4px; }

.actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 18px; }
.action { padding: 18px; border-radius: 18px; background: var(--surface-2); border: 1px solid var(--line-soft); cursor: pointer; transition: transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease; color: inherit; text-align: left; animation: rise 0.5s ease both; }
.action:hover { transform: translateY(-3px); border-color: rgba(119,141,169,0.28); box-shadow: 0 16px 40px rgba(0,0,0,0.26); }
.action.running { opacity: 0.7; pointer-events: none; }
.actions .action:nth-child(1) { animation-delay: 0.05s; }
.actions .action:nth-child(2) { animation-delay: 0.12s; }
.actions .action:nth-child(3) { animation-delay: 0.19s; }
.actions .action:nth-child(4) { animation-delay: 0.26s; }

.boost { display: grid; grid-template-columns: 1fr auto; gap: 14px; margin-top: 6px; }
input[type="text"] { width: 100%; padding: 15px 16px; border-radius: 14px; border: 1px solid var(--line-soft); background: var(--surface-2); color: var(--text); font: inherit; outline: none; transition: border-color 0.24s ease, box-shadow 0.24s ease; }
input[type="text"]:focus { border-color: rgba(119,141,169,0.40); box-shadow: 0 0 0 4px rgba(119,141,169,0.14); }
.primary-btn { border: none; border-radius: 14px; padding: 15px 20px; background: linear-gradient(135deg, #778DA9, #415A77); color: #0D1B2A; font: inherit; font-weight: 800; cursor: pointer; box-shadow: 0 18px 42px rgba(65,90,119,0.30); transition: transform 0.24s ease, box-shadow 0.24s ease; }
.primary-btn:hover { transform: translateY(-2px); box-shadow: 0 20px 44px rgba(119,141,169,0.32); }

.footer { padding: 6px 0 18px; text-align: center; color: var(--muted); font-size: 14px; }
.heart { color: var(--danger); display: inline-block; animation: beat 1.6s ease-in-out infinite; }
@keyframes beat { 0%,100% { transform: scale(1); } 30% { transform: scale(1.22); } 45% { transform: scale(1.05); } }
.footer-sub { margin-top: 6px; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(159,176,198,0.6); }

.toast-stack { position: fixed; right: 24px; bottom: 24px; display: grid; gap: 10px; z-index: 999; }
.toast { padding: 14px 16px; border-radius: 14px; background: var(--surface-strong); border: 1px solid var(--line); backdrop-filter: blur(20px); min-width: 250px; box-shadow: 0 18px 40px rgba(0,0,0,0.30); animation: rise 0.28s ease; }
.toast.success { border-color: rgba(119,141,169,0.40); }
.toast.error { border-color: rgba(207,138,147,0.42); }

@keyframes rise { from { opacity: 0; transform: translateY(12px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }

/* intro splash */
.intro { position: fixed; inset: 0; z-index: 9999; display: grid; place-items: center; background: radial-gradient(circle at 50% 38%, #1B263B, #0D1B2A 72%); transition: opacity 0.8s ease, transform 0.8s ease, visibility 0.8s; }
.intro.hide { opacity: 0; transform: scale(1.06); visibility: hidden; pointer-events: none; }
.intro-brand { font-family: 'Space Grotesk', sans-serif; letter-spacing: 0.42em; text-transform: uppercase; font-size: 13px; color: var(--accent); text-align: center; margin-bottom: 18px; opacity: 0; animation: introFade 0.8s ease 0.1s forwards; }
.intro-made { display: flex; gap: 0.32em; justify-content: center; font-family: 'Space Grotesk', sans-serif; font-weight: 700; letter-spacing: -0.02em; font-size: clamp(2.4rem, 8vw, 5.2rem); line-height: 1; }
.intro-made span { display: inline-block; opacity: 0; transform: translateY(26px); animation: introWord 0.9s cubic-bezier(.2,.8,.2,1) forwards; }
.intro-made span:nth-child(1) { animation-delay: 0.28s; }
.intro-made span:nth-child(2) { animation-delay: 0.46s; }
.intro-made .name { background: linear-gradient(120deg, #E0E1DD, #778DA9 50%, #415A77); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; text-shadow: 0 0 44px rgba(119,141,169,0.40); animation-delay: 0.7s; }
.intro-bar { width: 180px; height: 3px; margin: 30px auto 0; border-radius: 999px; background: rgba(224,225,221,0.12); overflow: hidden; }
.intro-bar::after { content: ''; display: block; height: 100%; width: 0; border-radius: 999px; background: linear-gradient(90deg, #778DA9, #415A77); animation: introBar 2.3s ease 0.3s forwards; }
@keyframes introFade { to { opacity: 1; } }
@keyframes introWord { to { opacity: 1; transform: translateY(0); } }
@keyframes introBar { to { width: 100%; } }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .intro { display: none; }
}
@media (max-width: 980px) {
  .hero, .layout { grid-template-columns: 1fr; }
  .card-grid, .actions { grid-template-columns: 1fr; }
  .boost { grid-template-columns: 1fr; }
}
"""


JS = r"""
const snapshot = __PAYLOAD__;

function toast(message, kind) {
  const stack = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || 'success');
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

async function call(method) {
  const args = Array.prototype.slice.call(arguments, 1);
  try {
    const result = await window.pywebview.api[method].apply(null, args);
    if (result.ok) {
      if (result.out && typeof result.out === 'string') toast(result.out, 'success');
    } else {
      toast(result.err || 'Action failed', 'error');
    }
    return result;
  } catch (error) {
    toast(String(error), 'error');
    return { ok: false, err: String(error) };
  }
}

function setCardState(id, active) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('active', active);
}

async function toggleFeature(method, cardId, checked) {
  const result = await call(method, checked);
  if (result.ok) setCardState(cardId, checked);
  else { const input = document.querySelector('#' + cardId + ' input'); if (input) input.checked = !checked; }
}

async function toggleGameMode(checked) {
  const result = await call('game_mode', checked);
  if (!result.ok) return;
  document.getElementById('gameModeCard').classList.toggle('active', checked);
  document.querySelectorAll('[data-feature-toggle]:not([disabled])').forEach((input) => {
    input.checked = checked;
    setCardState(input.dataset.card, checked);
  });
}

async function runAction(method, buttonId) {
  const button = document.getElementById(buttonId);
  button.classList.add('running');
  await call(method);
  button.classList.remove('running');
}

async function boostProcess() {
  const input = document.getElementById('processInput');
  const button = document.getElementById('boostButton');
  const name = input.value.trim().replace(/\.exe$/i, '');
  if (!name) { toast('Enter a running process name first.', 'error'); return; }
  button.disabled = true;
  await call('boost_process', name);
  button.disabled = false;
}

async function refreshSystem() {
  const result = await call('system_status');
  if (!result.ok) return;
  const s = result.out;
  document.getElementById('ifaceValue').textContent = s.interface;
  document.getElementById('ifacePill').textContent = s.interface;
  const privTxt = s.privileged ? 'Ready' : (s.os === 'windows' ? 'Missing' : 'On demand');
  document.getElementById('privValue').textContent = privTxt;
  const privPill = document.getElementById('privPill');
  privPill.textContent = privTxt;
  privPill.className = 'pill ' + (s.privileged ? 'good' : (s.os === 'windows' ? 'warn' : 'info'));
  document.getElementById('rendererValue').textContent = s.webview2_version;
  const rPill = document.getElementById('rendererPill');
  rPill.textContent = s.webview2_version;
  rPill.className = 'pill ' + (s.webview2_installed ? 'good' : 'warn');
}

function dismissIntro() {
  const intro = document.getElementById('intro');
  if (!intro) return;
  intro.classList.add('hide');
  setTimeout(() => intro.remove(), 850);
}

async function checkForUpdate() {
  try {
    const r = await window.pywebview.api.check_update();
    if (r && r.ok && r.out && r.out.update) {
      document.getElementById('updateText').textContent =
        'DelagR ' + r.out.latest + ' is available — you are on ' + r.out.current + '.';
      document.getElementById('updateBar').classList.add('show');
    }
  } catch (e) { /* offline: stay quiet */ }
}

async function doUpdate() {
  const go = document.getElementById('updateGo');
  go.disabled = true;
  document.getElementById('updateText').textContent = 'Downloading update…';
  const r = await call('apply_update');
  if (!r.ok) {
    go.disabled = false;
    document.getElementById('updateText').textContent = 'Update failed. Try again or use the release page.';
  }
}

function dismissUpdate() {
  document.getElementById('updateBar').classList.remove('show');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('processInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') boostProcess();
  });
  setTimeout(dismissIntro, 2600);
  refreshSystem();
  setTimeout(checkForUpdate, 1200);
});
"""


def feature_card(key: str, icon: str, title: str, text: str) -> str:
    supported = OS in SUPPORT[key]
    card_id = f"card-{key}"
    if supported:
        badge = ""
        toggle = (
            f'<label class="toggle"><input data-feature-toggle="1" data-card="{card_id}" type="checkbox" '
            f"onchange=\"toggleFeature('{key}', '{card_id}', this.checked)\"><span class=\"slider\"></span></label>"
        )
        klass = "card"
    else:
        names = ", ".join(OS_SHORT[o] for o in ("windows", "macos", "linux") if o in SUPPORT[key])
        badge = f'<span class="badge">{names} only</span>'
        toggle = (
            f'<label class="toggle"><input data-feature-toggle="1" data-card="{card_id}" type="checkbox" disabled>'
            f'<span class="slider"></span></label>'
        )
        klass = "card disabled"
    top_right = badge if badge else toggle
    extra = toggle if badge else ""
    return f"""
    <article class="{klass}" id="{card_id}">
      <div class="card-top">
        <div class="icon">{icon}</div>
        {top_right}
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {extra}
    </article>
    """


def action_card(key: str, icon: str, title: str, text: str) -> str:
    button_id = f"btn-{key}"
    return f"""
    <button class="action" id="{button_id}" onclick="runAction('{key}', '{button_id}')">
      <div class="icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </button>
    """


def render_html(snapshot: SystemSnapshot) -> str:
    features_html = "\n".join(feature_card(k, i, t, d) for k, i, t, d in FEATURES)
    actions_html = "\n".join(action_card(k, i, t, d) for k, i, t, d in ACTIONS)
    payload = json.dumps(snapshot.as_dict())

    priv_label = "Ready" if snapshot.privileged else ("Missing" if OS == "windows" else "On demand")
    priv_class = "good" if snapshot.privileged else ("warn" if OS == "windows" else "info")
    priv_hint = "Required for network and registry tweaks" if OS == "windows" else "DelagR asks for the system password only when a tweak needs it"
    renderer_label = "WebView2 Runtime" if OS == "windows" else "System WebView"

    body = f"""
  <div class="intro" id="intro">
    <div>
      <div class="intro-brand">DelagR</div>
      <div class="intro-made"><span>Made</span><span>for</span><span class="name">Josh</span></div>
      <div class="intro-bar"></div>
    </div>
  </div>

  <div class="shell">
    <div class="update-bar" id="updateBar">
      <span class="u-left"><span class="u-dot"></span><span id="updateText">A new version is available.</span></span>
      <span class="update-actions">
        <button class="update-btn" id="updateGo" onclick="doUpdate()">Update now</button>
        <button class="update-x" onclick="dismissUpdate()">Later</button>
      </span>
    </div>

    <section class="hero glass">
      <div class="hero-copy">
        <div class="eyebrow">Gaming Network Optimizer &middot; {snapshot.os_label} &middot; v{APP_VERSION}</div>
        <h1><span class="gradient">DelagR</span></h1>
        <p class="lead">A polished low-latency control room for gaming. Toggle packet-friendly network tweaks,
        clear background interference, and flip everything back when your session is over.</p>
      </div>
      <div class="hero-stats">
        <div class="mini-card"><div class="label">Interface</div><div class="value" id="ifaceValue">{snapshot.interface}</div></div>
        <div class="mini-card"><div class="label">Privileges</div><div class="value" id="privValue">{priv_label}</div></div>
        <div class="mini-card"><div class="label">Renderer</div><div class="value" id="rendererValue">{snapshot.webview2_version}</div></div>
        <div class="mini-card"><div class="label">Platform</div><div class="value">{snapshot.os_label}</div></div>
      </div>
    </section>

    <div class="layout">
      <aside class="sidebar">
        <section class="panel glass">
          <h2>System Status</h2>
          <div class="system-list">
            <div class="system-item">
              <div><strong>Privileges</strong><small>{priv_hint}</small></div>
              <span class="pill {priv_class}" id="privPill">{priv_label}</span>
            </div>
            <div class="system-item">
              <div><strong>{renderer_label}</strong><small>Renderer powering the glass UI</small></div>
              <span class="pill {'good' if snapshot.webview2_installed else 'warn'}" id="rendererPill">{snapshot.webview2_version}</span>
            </div>
            <div class="system-item">
              <div><strong>Active Interface</strong><small>Detected automatically for safer targeting</small></div>
              <span class="pill info" id="ifacePill">{snapshot.interface}</span>
            </div>
            <div class="system-item">
              <div><strong>Platform</strong><small>Tweaks adapt to your operating system</small></div>
              <span class="pill good">{snapshot.os_label}</span>
            </div>
          </div>
        </section>

        <section class="panel glass">
          <h2>Session Notes</h2>
          <p class="sub">Game Mode enables every latency tweak supported on your OS in one move. Greyed cards are
          features that only exist on another platform.</p>
          <p class="sub" style="margin-top: 12px;">If anything looks off, Export Diagnostics saves a support snapshot to your desktop.</p>
        </section>
      </aside>

      <main class="main">
        <section class="panel glass">
          <div class="game-mode" id="gameModeCard">
            <div><h2>Game Mode</h2><p class="sub">Apply every supported latency tweak in one smooth pass.</p></div>
            <label class="toggle"><input id="gameModeToggle" type="checkbox" onchange="toggleGameMode(this.checked)"><span class="slider"></span></label>
          </div>
          <div class="card-grid">{features_html}</div>
        </section>

        <section class="panel glass">
          <h2>Quick Actions</h2>
          <div class="actions">{actions_html}</div>
          <h2>Process Priority</h2>
          <div class="boost">
            <input id="processInput" type="text" placeholder="e.g. {'FortniteClient-Win64-Shipping' if OS == 'windows' else 'process name'}">
            <button class="primary-btn" id="boostButton" onclick="boostProcess()">Boost To High Priority</button>
          </div>
        </section>
      </main>
    </div>

    <div class="footer">
      <span class="heart">&#9829;</span> Made with love by Fletcher Holt
      <div class="footer-sub">DelagR v{APP_VERSION} &middot; {snapshot.os_label}</div>
    </div>
  </div>

  <div class="toast-stack" id="toasts"></div>
"""

    js = JS.replace("__PAYLOAD__", payload)
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>{APP_NAME}</title><style>{CSS}</style></head><body>"
        f"{body}<script>{js}</script></body></html>"
    )


# --------------------------------------------------------------------------- #
# Setup wizard (cross-platform)
# --------------------------------------------------------------------------- #
COL_BG = "#0D1B2A"
COL_CARD = "#1B263B"
COL_LINE = "#415A77"
COL_TEXT = "#E0E1DD"
COL_MUTED = "#778DA9"
COL_ACCENT = "#778DA9"


class SetupWizard:
    def __init__(self):
        self.snapshot: SystemSnapshot | None = None
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("720x520")
        self.root.minsize(680, 480)
        self.root.configure(bg=COL_BG)

        self.status_vars = {
            "priv": tk.StringVar(value="Checking"),
            "renderer": tk.StringVar(value="Checking"),
            "iface": tk.StringVar(value="Checking"),
            "platform": tk.StringVar(value=OS_LABEL),
            "state": tk.StringVar(value="Inspecting your system..."),
        }
        self.launch_ready = False
        self._build()
        self.refresh_status()

    def _build(self):
        shell = tk.Frame(self.root, bg=COL_BG, padx=24, pady=24)
        shell.pack(fill="both", expand=True)
        card = tk.Frame(shell, bg=COL_CARD, highlightbackground=COL_LINE, highlightthickness=1)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=COL_CARD, padx=28, pady=24)
        header.pack(fill="x")
        tk.Label(header, text="DelagR", fg=COL_TEXT, bg=COL_CARD, font=("Helvetica", 28, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text=f"First-run setup for {OS_LABEL}. Checks the renderer and access DelagR needs.",
            fg=COL_MUTED, bg=COL_CARD, font=("Helvetica", 11), wraplength=560, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        body = tk.Frame(card, bg=COL_CARD, padx=28, pady=10)
        body.pack(fill="both", expand=True)
        priv_desc = "Needed for network and registry changes." if OS == "windows" else "Granted per-action via the system password prompt."
        renderer_desc = "Required for the DelagR renderer." if OS == "windows" else "Built into your OS — nothing to install."
        self._row(body, "Privileges", priv_desc, self.status_vars["priv"])
        self._row(body, "Renderer", renderer_desc, self.status_vars["renderer"])
        self._row(body, "Network Interface", "Used for interface-specific commands.", self.status_vars["iface"])
        self._row(body, "Platform", "Tweaks adapt to your operating system.", self.status_vars["platform"])

        footer = tk.Frame(card, bg=COL_CARD, padx=28, pady=24)
        footer.pack(fill="x")
        tk.Label(footer, textvariable=self.status_vars["state"], fg=COL_ACCENT, bg=COL_CARD, font=("Helvetica", 10, "bold")).pack(anchor="w")

        actions = tk.Frame(footer, bg=COL_CARD)
        actions.pack(fill="x", pady=(16, 0))
        self.install_button = tk.Button(
            actions, text="Install Missing Components", command=self.install_missing, relief="flat",
            bg=COL_ACCENT, fg=COL_BG, activebackground="#8fa3bc", activeforeground=COL_BG,
            font=("Helvetica", 11, "bold"), padx=16, pady=10, cursor="hand2",
        )
        self.install_button.pack(side="left")
        self.launch_button = tk.Button(
            actions, text="Launch DelagR", command=self.launch, relief="flat",
            bg=COL_LINE, fg=COL_TEXT, activebackground="#4f6c8c", activeforeground=COL_TEXT,
            font=("Helvetica", 11, "bold"), padx=16, pady=10, cursor="hand2", state="disabled",
        )
        self.launch_button.pack(side="right")
        self.export_button = tk.Button(
            actions, text="Save Diagnostics", command=self.export_diagnostics, relief="flat",
            bg="#22324a", fg=COL_TEXT, activebackground="#2c3f5c", activeforeground=COL_TEXT,
            font=("Helvetica", 11, "bold"), padx=16, pady=10, cursor="hand2",
        )
        self.export_button.pack(side="right", padx=(0, 10))

    def _row(self, parent, title, description, var):
        frame = tk.Frame(parent, bg="#142133", padx=16, pady=14, highlightbackground=COL_LINE, highlightthickness=1)
        frame.pack(fill="x", pady=7)
        left = tk.Frame(frame, bg="#142133")
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, fg=COL_TEXT, bg="#142133", font=("Helvetica", 12, "bold")).pack(anchor="w")
        tk.Label(left, text=description, fg=COL_MUTED, bg="#142133", font=("Helvetica", 10)).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=var, fg=COL_ACCENT, bg="#142133", font=("Helvetica", 10, "bold")).pack(side="right")

    def refresh_status(self):
        self.snapshot = collect_system_snapshot()
        self.status_vars["priv"].set("Ready" if self.snapshot.privileged else ("Missing" if OS == "windows" else "On demand"))
        self.status_vars["renderer"].set(self.snapshot.webview2_version)
        self.status_vars["iface"].set(self.snapshot.interface)
        self.status_vars["platform"].set(self.snapshot.os_label + (f" ({self.snapshot.compat_layer})" if self.snapshot.compat_layer else ""))

        if OS == "windows":
            self.launch_ready = self.snapshot.privileged and self.snapshot.webview2_installed and not self.snapshot.compat_layer
        else:
            # macOS/Linux need no install step; elevation happens per-action.
            self.launch_ready = True

        if self.snapshot.compat_layer:
            self.status_vars["state"].set(f"Detected {self.snapshot.compat_layer}. DelagR targets native Windows and may not launch correctly.")
            self.launch_button.config(state="disabled")
            self.install_button.config(state="disabled")
        elif self.launch_ready:
            self.status_vars["state"].set("Everything is ready. Launch DelagR when you are.")
            self.launch_button.config(state="normal")
            self.install_button.config(state="disabled")
        else:
            self.status_vars["state"].set("DelagR needs the missing items above before the main window can open.")
            self.launch_button.config(state="disabled")
            self.install_button.config(state="normal")

    def install_missing(self):
        if OS != "windows":
            self.refresh_status()
            return
        if not self.snapshot.privileged:
            self.status_vars["state"].set("Restarting as administrator...")
            if relaunch_as_admin():
                self.root.destroy()
            else:
                self.status_vars["state"].set("Administrator access was declined. Right-click DelagR and choose 'Run as administrator'.")
            return

        self.install_button.config(state="disabled")
        self.status_vars["state"].set("Installing missing components. This can take a moment...")

        def worker():
            result_message = None
            if not self.snapshot.webview2_installed:
                result = install_webview2_runtime()
                result_message = result["out"] if result["ok"] else result["err"]
            self.root.after(0, lambda: self._finish_install(result_message))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_install(self, result_message):
        self.refresh_status()
        if result_message:
            self.status_vars["state"].set(result_message if self.launch_ready else f"{result_message} Check status above.")
        self.install_button.config(state="normal" if not self.launch_ready else "disabled")

    def launch(self):
        self.root.destroy()

    def export_diagnostics(self):
        self.snapshot = collect_system_snapshot()
        try:
            target = diagnostics_path()
            target.write_text(build_diagnostics_report(self.snapshot), encoding="utf-8")
        except Exception as exc:
            self.status_vars["state"].set(f"Failed to save diagnostics: {exc}")
            return
        self.status_vars["state"].set(f"Saved diagnostics to {target}")

    def run(self) -> SystemSnapshot | None:
        self.root.mainloop()
        return self.snapshot if self.launch_ready else None


def start_main_ui(snapshot: SystemSnapshot):
    api = DelagRAPI(snapshot)
    html = render_html(snapshot)

    # The window/taskbar icon comes from the packaged build's icon resource.
    webview.create_window(
        APP_NAME,
        html=html,
        js_api=api,
        width=1360,
        height=920,
        min_size=(900, 680),
        background_color="#0D1B2A",
        text_select=False,
    )

    if OS == "windows":
        try:
            webview.start(gui="edgechromium")
            return
        except Exception:
            pass
    elif OS == "linux":
        # Only the Qt backend is bundled; don't let pywebview try GTK first.
        try:
            webview.start(gui="qt")
            return
        except Exception:
            pass
    webview.start()


def selftest() -> int:
    """Headless smoke test: build the snapshot, render the UI, and import the
    GUI backend for this OS. Used by CI to verify the packaged build actually
    runs on each platform. Returns a process exit code."""
    snapshot = SystemSnapshot(
        os=OS, os_label=OS_LABEL, privileged=False, interface="selftest",
        webview2_installed=True, webview2_version="selftest", compat_layer=None,
    )
    html = render_html(snapshot)
    assert "<!DOCTYPE html>" in html and "DelagR" in html and len(html) > 8000, "render failed"

    import importlib
    backend = {
        "windows": "webview.platforms.edgechromium",
        "macos": "webview.platforms.cocoa",
        "linux": "webview.platforms.qt",
    }[OS]
    importlib.import_module(backend)  # raises if the GUI stack is not bundled

    # Exercise the read-only update version logic too.
    assert is_newer("v99.0.0", APP_VERSION) and not is_newer(APP_VERSION, APP_VERSION)
    print(f"DelagR {APP_VERSION} selftest OK on {OS_LABEL}: render + {backend} import + version logic")
    return 0


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())

    wizard = SetupWizard()
    snapshot = wizard.run()
    if snapshot:
        start_main_ui(snapshot)


if __name__ == "__main__":
    main()
