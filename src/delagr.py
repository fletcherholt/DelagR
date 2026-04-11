from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

import webview

try:
    import winreg
except ImportError:  # Non-Windows development environment
    winreg = None


APP_NAME = "DelagR"
WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
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


def is_windows() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if not is_windows() or is_admin():
        return

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        executable = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(__file__), *sys.argv[1:]])

    ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    sys.exit()


def ensure_runtime_icon() -> str | None:
    icon_path = Path(tempfile.gettempdir()) / "delagr_icon.ico"
    try:
        if not icon_path.exists():
            icon_path.write_bytes(base64.b64decode(ICON_ICO_BASE64))
        return str(icon_path)
    except Exception:
        return None


def run_command(command: str, timeout: int = 20) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "out": completed.stdout.strip(),
            "err": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "out": "", "err": str(exc)}


def detect_wifi_interface() -> str:
    command = (
        'powershell -NoProfile -Command "'
        "Get-NetAdapter | "
        "Where-Object {$_.Status -eq 'Up' -and ($_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN|802.11')} | "
        "Select-Object -First 1 -ExpandProperty Name"
        '"'
    )
    result = run_command(command, timeout=10)
    return result["out"] if result["ok"] and result["out"] else "Wi-Fi"


def detect_webview2() -> tuple[bool, str]:
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

    return False, "Not installed"


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


@dataclass
class SystemSnapshot:
    admin: bool
    wifi: str
    webview2_installed: bool
    webview2_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "admin": self.admin,
            "wifi": self.wifi,
            "webview2_installed": self.webview2_installed,
            "webview2_version": self.webview2_version,
        }


def collect_system_snapshot() -> SystemSnapshot:
    installed, version = detect_webview2()
    return SystemSnapshot(
        admin=is_admin(),
        wifi=detect_wifi_interface(),
        webview2_installed=installed,
        webview2_version=version,
    )


class DelagRAPI:
    def __init__(self, snapshot: SystemSnapshot):
        self.snapshot = snapshot

    def system_status(self):
        self.snapshot = collect_system_snapshot()
        return {"ok": True, "out": self.snapshot.as_dict(), "err": ""}

    def wifi_autoscan(self, enable: bool):
        flag = "no" if enable else "yes"
        return run_command(f'netsh wlan set autoconfig enabled={flag} interface="{self.snapshot.wifi}"')

    def flush_dns(self):
        return run_command("ipconfig /flushdns")

    def tcp_autotuning(self, enable: bool):
        level = "disabled" if enable else "normal"
        return run_command(f"netsh int tcp set global autotuninglevel={level}")

    def nagle(self, enable: bool):
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

    def net_throttle(self, enable: bool):
        value = "4294967295" if enable else "10"
        key = "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile"
        return run_command(f'reg add "{key}" /v NetworkThrottlingIndex /t REG_DWORD /d {value} /f')

    def wifi_power_save(self, enable: bool):
        value = "0" if enable else "1"
        command = (
            'powershell -NoProfile -Command "'
            f"powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONNECTIVITY_IN_STANDBY {value}; "
            'powercfg /setactive SCHEME_CURRENT"'
        )
        return run_command(command)

    def optimize_dns(self, enable: bool):
        if enable:
            run_command(f'netsh interface ip set dns "{self.snapshot.wifi}" static 1.1.1.1 primary')
            run_command(f'netsh interface ip add dns "{self.snapshot.wifi}" 1.0.0.1 index=2')
            return {"ok": True, "out": "DNS set to Cloudflare 1.1.1.1", "err": ""}
        run_command(f'netsh interface ip set dns "{self.snapshot.wifi}" dhcp')
        return {"ok": True, "out": "DNS reverted to DHCP", "err": ""}

    def game_bar(self, enable: bool):
        value = "0" if enable else "1"
        run_command(
            f'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\GameDVR" /v AppCaptureEnabled /t REG_DWORD /d {value} /f'
        )
        run_command(
            f'reg add "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d {value} /f'
        )
        return {"ok": True, "out": f"Game Bar/DVR {'disabled' if enable else 'enabled'}", "err": ""}

    def delivery_optimization(self, enable: bool):
        value = "0" if enable else "1"
        return run_command(
            f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\DeliveryOptimization\\Config" /v DODownloadMode /t REG_DWORD /d {value} /f'
        )

    def location_tracking(self, enable: bool):
        value = "Deny" if enable else "Allow"
        return run_command(
            f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location" /v Value /t REG_SZ /d {value} /f'
        )

    def kill_bandwidth_hogs(self):
        candidates = [
            "OneDrive.exe",
            "Dropbox.exe",
            "Teams.exe",
            "Slack.exe",
            "Spotify.exe",
            "EpicWebHelper.exe",
            "GoogleUpdate.exe",
            "MicrosoftEdgeUpdate.exe",
        ]
        killed: list[str] = []
        for proc in candidates:
            result = run_command(f"taskkill /f /im {proc} 2>nul")
            if result["ok"] and "SUCCESS" in str(result["out"]):
                killed.append(proc.replace(".exe", ""))
        return {"ok": True, "out": f"Killed: {', '.join(killed) if killed else 'none running'}", "err": ""}

    def boost_process(self, process_name: str):
        result = run_command(
            'powershell -NoProfile -Command "'
            f"$p = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue; "
            "if ($p) { $p | ForEach-Object { $_.PriorityClass = 'High' }; Write-Output 'BOOSTED' } "
            "else { Write-Output 'NOTFOUND' }"
            '"'
        )
        if "BOOSTED" in str(result["out"]):
            return {"ok": True, "out": f"{process_name} set to High priority", "err": ""}
        return {"ok": False, "out": "", "err": f"Process '{process_name}' was not found."}

    def reset_network(self):
        run_command("netsh winsock reset")
        run_command("netsh int ip reset")
        run_command("ipconfig /flushdns")
        run_command("ipconfig /release")
        run_command("ipconfig /renew")
        return {"ok": True, "out": "Network stack reset. A restart may be required.", "err": ""}

    def game_mode(self, enable: bool):
        actions = [
            ("Wi-Fi Auto-Scan", self.wifi_autoscan(enable)),
            ("TCP Auto-Tuning", self.tcp_autotuning(enable)),
            ("Nagle's Algorithm", self.nagle(enable)),
            ("Network Throttling", self.net_throttle(enable)),
            ("Fast DNS", self.optimize_dns(enable)),
            ("Game Bar", self.game_bar(enable)),
            ("Delivery Optimization", self.delivery_optimization(enable)),
            ("Location Tracking", self.location_tracking(enable)),
        ]
        if enable:
            actions.append(("Flush DNS", self.flush_dns()))
        summary = "; ".join(f"{name}: {'OK' if result['ok'] else 'FAIL'}" for name, result in actions)
        return {"ok": True, "out": summary, "err": ""}


def render_html(snapshot: SystemSnapshot) -> str:
    payload = json.dumps(snapshot.as_dict())
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DelagR</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Manrope:wght@400;500;600;700&display=swap');

    :root {{
      --bg: #07111f;
      --bg-2: #09192c;
      --glass: rgba(10, 20, 38, 0.52);
      --glass-strong: rgba(9, 20, 36, 0.82);
      --stroke: rgba(255,255,255,0.12);
      --stroke-soft: rgba(255,255,255,0.08);
      --text: #f5fbff;
      --muted: #9ab2c8;
      --cyan: #79e9ff;
      --blue: #6ba6ff;
      --mint: #87ffc3;
      --red: #ff7b93;
      --shadow: 0 24px 80px rgba(0,0,0,0.35);
      --radius: 24px;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ min-height: 100%; }}
    body {{
      font-family: 'Manrope', sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(121, 233, 255, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(107, 166, 255, 0.14), transparent 34%),
        linear-gradient(160deg, var(--bg), var(--bg-2));
      overflow-x: hidden;
    }}

    body::before, body::after {{
      content: '';
      position: fixed;
      width: 28rem;
      height: 28rem;
      border-radius: 999px;
      filter: blur(28px);
      opacity: 0.22;
      pointer-events: none;
      animation: drift 16s ease-in-out infinite;
    }}

    body::before {{
      top: -8rem;
      left: -6rem;
      background: #5ce6ff;
    }}

    body::after {{
      right: -5rem;
      bottom: -8rem;
      background: #6c8fff;
      animation-delay: -6s;
    }}

    @keyframes drift {{
      0%, 100% {{ transform: translate3d(0, 0, 0) scale(1); }}
      50% {{ transform: translate3d(1.5rem, -1rem, 0) scale(1.08); }}
    }}

    .shell {{
      position: relative;
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px;
      display: grid;
      gap: 20px;
    }}

    .glass {{
      background: var(--glass);
      border: 1px solid var(--stroke);
      box-shadow: var(--shadow);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-radius: var(--radius);
    }}

    .hero {{
      padding: 28px;
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 20px;
      overflow: hidden;
    }}

    .hero-copy {{
      position: relative;
      z-index: 1;
    }}

    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      color: var(--cyan);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      margin-bottom: 16px;
    }}

    h1, h2, h3 {{
      font-family: 'Space Grotesk', sans-serif;
      letter-spacing: -0.03em;
    }}

    h1 {{
      font-size: clamp(2.8rem, 5vw, 4.2rem);
      line-height: 0.96;
      margin-bottom: 14px;
    }}

    .gradient {{
      background: linear-gradient(120deg, #ffffff 0%, var(--cyan) 44%, var(--blue) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .lead {{
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.65;
      max-width: 48rem;
    }}

    .hero-stats {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}

    .mini-card {{
      padding: 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--stroke-soft);
    }}

    .mini-card .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 6px;
    }}

    .mini-card .value {{
      font-size: 1rem;
      font-weight: 700;
    }}

    .layout {{
      display: grid;
      grid-template-columns: 300px 1fr;
      gap: 20px;
    }}

    .sidebar, .main {{
      display: grid;
      gap: 20px;
    }}

    .panel {{
      padding: 20px;
    }}

    .panel h2 {{
      font-size: 1.1rem;
      margin-bottom: 14px;
    }}

    .system-list {{
      display: grid;
      gap: 12px;
    }}

    .system-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--stroke-soft);
    }}

    .system-item small {{
      display: block;
      color: var(--muted);
      margin-top: 4px;
      font-size: 12px;
    }}

    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 88px;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}

    .pill.good {{ background: rgba(135,255,195,0.16); color: var(--mint); }}
    .pill.warn {{ background: rgba(255,123,147,0.16); color: #ffb1bf; }}
    .pill.info {{ background: rgba(121,233,255,0.16); color: var(--cyan); }}

    .game-mode {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 22px;
      border-radius: 22px;
      background: linear-gradient(135deg, rgba(121,233,255,0.11), rgba(107,166,255,0.08));
      border: 1px solid rgba(121,233,255,0.18);
      margin-bottom: 18px;
    }}

    .game-mode.active {{
      background: linear-gradient(135deg, rgba(135,255,195,0.12), rgba(121,233,255,0.10));
      border-color: rgba(135,255,195,0.24);
    }}

    .toggle {{
      position: relative;
      width: 72px;
      height: 40px;
      flex: 0 0 auto;
      cursor: pointer;
    }}

    .toggle input {{ display: none; }}

    .slider {{
      position: absolute;
      inset: 0;
      border-radius: 999px;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.08);
      transition: all 0.35s ease;
      overflow: hidden;
    }}

    .slider::before {{
      content: '';
      position: absolute;
      width: 30px;
      height: 30px;
      top: 4px;
      left: 4px;
      border-radius: 50%;
      background: linear-gradient(180deg, #fff, #d9ebff);
      box-shadow: 0 8px 24px rgba(0,0,0,0.28);
      transition: transform 0.35s cubic-bezier(.2,.9,.3,1.1);
    }}

    .toggle input:checked + .slider {{
      background: linear-gradient(135deg, rgba(135,255,195,0.5), rgba(121,233,255,0.45));
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08), 0 10px 28px rgba(121,233,255,0.18);
    }}

    .toggle input:checked + .slider::before {{
      transform: translateX(31px);
    }}

    .card-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}

    .card {{
      position: relative;
      overflow: hidden;
      padding: 18px;
      border-radius: 20px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--stroke-soft);
      transition: transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease;
      animation: rise 0.55s ease both;
    }}

    .card:hover {{
      transform: translateY(-3px);
      border-color: rgba(121,233,255,0.18);
      box-shadow: 0 16px 40px rgba(0,0,0,0.24);
    }}

    .card.active {{
      border-color: rgba(135,255,195,0.22);
      box-shadow: 0 14px 34px rgba(121,233,255,0.10);
    }}

    .card-top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}

    .icon {{
      width: 40px;
      height: 40px;
      display: grid;
      place-items: center;
      border-radius: 14px;
      background: rgba(121,233,255,0.12);
      font-size: 18px;
    }}

    .card.active .icon {{
      background: rgba(135,255,195,0.12);
    }}

    .card p, .action p, .sub {{
      color: var(--muted);
      line-height: 1.55;
    }}

    .actions {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}

    .action {{
      padding: 18px;
      border-radius: 20px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--stroke-soft);
      cursor: pointer;
      transition: transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease;
      color: inherit;
      text-align: left;
    }}

    .action:hover {{
      transform: translateY(-3px);
      border-color: rgba(121,233,255,0.18);
      box-shadow: 0 16px 40px rgba(0,0,0,0.24);
    }}

    .action.running {{
      opacity: 0.7;
      pointer-events: none;
    }}

    .boost {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      margin-top: 6px;
    }}

    input[type="text"] {{
      width: 100%;
      padding: 15px 16px;
      border-radius: 16px;
      border: 1px solid var(--stroke-soft);
      background: rgba(255,255,255,0.05);
      color: var(--text);
      font: inherit;
      outline: none;
      transition: border-color 0.24s ease, box-shadow 0.24s ease;
    }}

    input[type="text"]:focus {{
      border-color: rgba(121,233,255,0.24);
      box-shadow: 0 0 0 4px rgba(121,233,255,0.10);
    }}

    .primary-btn {{
      border: none;
      border-radius: 16px;
      padding: 15px 20px;
      background: linear-gradient(135deg, #82efff, #6798ff);
      color: #04121e;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 18px 42px rgba(103,152,255,0.25);
      transition: transform 0.24s ease, box-shadow 0.24s ease;
    }}

    .primary-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 20px 44px rgba(121,233,255,0.28);
    }}

    .footer {{
      padding: 6px 0 18px;
      text-align: center;
      color: var(--muted);
      font-size: 14px;
    }}

    .toast-stack {{
      position: fixed;
      right: 24px;
      bottom: 24px;
      display: grid;
      gap: 10px;
      z-index: 999;
    }}

    .toast {{
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(9,20,36,0.88);
      border: 1px solid var(--stroke);
      backdrop-filter: blur(20px);
      min-width: 250px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.28);
      animation: rise 0.28s ease;
    }}

    .toast.success {{ border-color: rgba(135,255,195,0.24); }}
    .toast.error {{ border-color: rgba(255,123,147,0.28); }}

    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(12px) scale(0.98); }}
      to {{ opacity: 1; transform: translateY(0) scale(1); }}
    }}

    @media (max-width: 980px) {{
      .hero, .layout {{ grid-template-columns: 1fr; }}
      .card-grid, .actions {{ grid-template-columns: 1fr; }}
      .boost {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero glass">
      <div class="hero-copy">
        <div class="eyebrow">Windows Gaming Network Optimizer</div>
        <h1><span class="gradient">DelagR</span></h1>
        <p class="lead">
          A polished low-latency control room for gaming on Windows. Toggle packet-friendly network tweaks,
          clear background interference, and flip everything back when your session is over.
        </p>
      </div>
      <div class="hero-stats">
        <div class="mini-card">
          <div class="label">Wi-Fi Adapter</div>
          <div class="value" id="wifiValue">{snapshot.wifi}</div>
        </div>
        <div class="mini-card">
          <div class="label">Admin Access</div>
          <div class="value" id="adminValue">{'Ready' if snapshot.admin else 'Needed'}</div>
        </div>
        <div class="mini-card">
          <div class="label">Renderer</div>
          <div class="value" id="webviewValue">{snapshot.webview2_version}</div>
        </div>
      </div>
    </section>

    <div class="layout">
      <aside class="sidebar">
        <section class="panel glass">
          <h2>System Status</h2>
          <div class="system-list">
            <div class="system-item">
              <div>
                <strong>Administrator</strong>
                <small>Required for network and registry tweaks</small>
              </div>
              <span class="pill {'good' if snapshot.admin else 'warn'}" id="adminPill">{'Ready' if snapshot.admin else 'Missing'}</span>
            </div>
            <div class="system-item">
              <div>
                <strong>WebView2 Runtime</strong>
                <small>Modern renderer used by the glass UI</small>
              </div>
              <span class="pill {'good' if snapshot.webview2_installed else 'warn'}" id="webviewPill">{snapshot.webview2_version}</span>
            </div>
            <div class="system-item">
              <div>
                <strong>Active Adapter</strong>
                <small>Detected automatically for safer command targeting</small>
              </div>
              <span class="pill info" id="wifiPill">{snapshot.wifi}</span>
            </div>
          </div>
        </section>

        <section class="panel glass">
          <h2>Session Notes</h2>
          <p class="sub">
            Game Mode enables the latency-focused switches below in one move. Individual changes remain active
            until you turn them back off, so DelagR is built for before-and-after gaming sessions.
          </p>
        </section>
      </aside>

      <main class="main">
        <section class="panel glass">
          <div class="game-mode" id="gameModeCard">
            <div>
              <h2>Game Mode</h2>
              <p class="sub">Apply all major latency tweaks in one smooth pass.</p>
            </div>
            <label class="toggle">
              <input id="gameModeToggle" type="checkbox" onchange="toggleGameMode(this.checked)">
              <span class="slider"></span>
            </label>
          </div>

          <div class="card-grid">
            {feature_card("card-autoscan", "📡", "Wi-Fi Auto-Scan", "Stops Windows from scanning for nearby access points during gameplay.", "wifi_autoscan")}
            {feature_card("card-autotuning", "📶", "TCP Auto-Tuning", "Locks TCP receive window behavior to reduce jitter spikes.", "tcp_autotuning")}
            {feature_card("card-nagle", "🚀", "Nagle's Algorithm", "Disables TCP batching so smaller packets move immediately.", "nagle")}
            {feature_card("card-throttle", "⚡", "Network Throttling", "Removes the multimedia throttle that can hold back packets.", "net_throttle")}
            {feature_card("card-powersave", "🔋", "Wi-Fi Power Saving", "Keeps the adapter from dropping into lower-power latency states.", "wifi_power_save")}
            {feature_card("card-dns", "🌐", "Fast DNS", "Switches to Cloudflare DNS for faster connection lookups.", "optimize_dns")}
            {feature_card("card-gamebar", "🎮", "Game Bar / DVR", "Turns off Xbox overlays and background recording overhead.", "game_bar")}
            {feature_card("card-delivery", "📦", "Delivery Optimization", "Stops peer-to-peer Windows update uploads while you play.", "delivery_optimization")}
            {feature_card("card-location", "📍", "Location Tracking", "Cuts background location chatter that can create noise.", "location_tracking")}
          </div>
        </section>

        <section class="panel glass">
          <h2>Quick Actions</h2>
          <div class="actions">
            {action_card("btn-flush", "🧹", "Flush DNS", "Clear cached resolver entries.", "flush_dns")}
            {action_card("btn-kill", "🔪", "Kill Bandwidth Hogs", "Close common upload-heavy background apps.", "kill_bandwidth_hogs")}
            {action_card("btn-reset", "🔄", "Reset Network Stack", "Use the heavy reset path for stubborn issues.", "reset_network")}
          </div>

          <h2>Process Priority</h2>
          <div class="boost">
            <input id="processInput" type="text" placeholder="e.g. FortniteClient-Win64-Shipping">
            <button class="primary-btn" id="boostButton" onclick="boostProcess()">Boost To High Priority</button>
          </div>
        </section>
      </main>
    </div>

    <div class="footer">Made with love by Fletcher Holt</div>
  </div>

  <div class="toast-stack" id="toasts"></div>

  <script>
    const snapshot = {payload};

    function toast(message, kind = 'success') {{
      const stack = document.getElementById('toasts');
      const el = document.createElement('div');
      el.className = 'toast ' + kind;
      el.textContent = message;
      stack.appendChild(el);
      setTimeout(() => el.remove(), 3800);
    }}

    async function call(method, ...args) {{
      try {{
        const result = await window.pywebview.api[method](...args);
        if (result.ok) {{
          if (result.out && typeof result.out === 'string') toast(result.out, 'success');
        }} else {{
          toast(result.err || 'Action failed', 'error');
        }}
        return result;
      }} catch (error) {{
        toast(String(error), 'error');
        return {{ ok: false, err: String(error) }};
      }}
    }}

    function setCardState(id, active) {{
      document.getElementById(id)?.classList.toggle('active', active);
    }}

    async function toggleFeature(method, cardId, checked) {{
      const result = await call(method, checked);
      if (result.ok) setCardState(cardId, checked);
    }}

    async function toggleGameMode(checked) {{
      const result = await call('game_mode', checked);
      if (!result.ok) return;
      document.getElementById('gameModeCard').classList.toggle('active', checked);
      document.querySelectorAll('[data-feature-toggle]').forEach((input) => {{
        input.checked = checked;
        setCardState(input.dataset.card, checked);
      }});
    }}

    async function runAction(method, buttonId) {{
      const button = document.getElementById(buttonId);
      button.classList.add('running');
      await call(method);
      button.classList.remove('running');
    }}

    async function boostProcess() {{
      const input = document.getElementById('processInput');
      const button = document.getElementById('boostButton');
      const name = input.value.trim().replace(/\\.exe$/i, '');
      if (!name) {{
        toast('Enter a running process name first.', 'error');
        return;
      }}
      button.disabled = true;
      await call('boost_process', name);
      button.disabled = false;
    }}

    async function refreshSystem() {{
      const result = await call('system_status');
      if (!result.ok) return;
      const status = result.out;
      document.getElementById('wifiValue').textContent = status.wifi;
      document.getElementById('wifiPill').textContent = status.wifi;
      document.getElementById('adminValue').textContent = status.admin ? 'Ready' : 'Missing';
      document.getElementById('adminPill').textContent = status.admin ? 'Ready' : 'Missing';
      document.getElementById('adminPill').className = 'pill ' + (status.admin ? 'good' : 'warn');
      document.getElementById('webviewValue').textContent = status.webview2_version;
      document.getElementById('webviewPill').textContent = status.webview2_version;
      document.getElementById('webviewPill').className = 'pill ' + (status.webview2_installed ? 'good' : 'warn');
    }}

    document.addEventListener('DOMContentLoaded', () => {{
      document.getElementById('processInput').addEventListener('keydown', (event) => {{
        if (event.key === 'Enter') boostProcess();
      }});
      refreshSystem();
    }});
  </script>
</body>
</html>
"""


def feature_card(card_id: str, icon: str, title: str, text: str, method: str) -> str:
    return f"""
    <article class="card" id="{card_id}">
      <div class="card-top">
        <div class="icon">{icon}</div>
        <label class="toggle">
          <input data-feature-toggle="1" data-card="{card_id}" type="checkbox" onchange="toggleFeature('{method}', '{card_id}', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
    """


def action_card(button_id: str, icon: str, title: str, text: str, method: str) -> str:
    return f"""
    <button class="action" id="{button_id}" onclick="runAction('{method}', '{button_id}')">
      <div class="icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </button>
    """


class SetupWizard:
    def __init__(self):
        self.snapshot = collect_system_snapshot()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("720x520")
        self.root.minsize(680, 480)
        self.root.configure(bg="#07111f")

        self.status_vars = {
            "admin": tk.StringVar(value="Checking"),
            "webview": tk.StringVar(value="Checking"),
            "wifi": tk.StringVar(value="Checking"),
            "state": tk.StringVar(value="Inspecting your system..."),
        }
        self.launch_ready = False
        self._build()
        self.refresh_status()

    def _build(self):
        root = self.root

        shell = tk.Frame(root, bg="#07111f", padx=24, pady=24)
        shell.pack(fill="both", expand=True)

        card = tk.Frame(shell, bg="#0d1a2c", highlightbackground="#204067", highlightthickness=1)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg="#0d1a2c", padx=28, pady=24)
        header.pack(fill="x")
        tk.Label(
            header,
            text="DelagR",
            fg="#f6fbff",
            bg="#0d1a2c",
            font=("Segoe UI Semibold", 28),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="First-run setup checks the renderer and system access needed for the full glass UI.",
            fg="#9cb3c8",
            bg="#0d1a2c",
            font=("Segoe UI", 11),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        body = tk.Frame(card, bg="#0d1a2c", padx=28, pady=10)
        body.pack(fill="both", expand=True)

        self._row(body, "Administrator Access", "Needed for network and registry changes.", self.status_vars["admin"])
        self._row(body, "WebView2 Runtime", "Required for the modern DelagR renderer.", self.status_vars["webview"])
        self._row(body, "Wi-Fi Adapter", "Used for interface-specific network commands.", self.status_vars["wifi"])

        footer = tk.Frame(card, bg="#0d1a2c", padx=28, pady=24)
        footer.pack(fill="x")
        tk.Label(
            footer,
            textvariable=self.status_vars["state"],
            fg="#84f0ff",
            bg="#0d1a2c",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")

        actions = tk.Frame(footer, bg="#0d1a2c")
        actions.pack(fill="x", pady=(16, 0))

        self.install_button = tk.Button(
            actions,
            text="Install Missing Components",
            command=self.install_missing,
            relief="flat",
            bg="#87efff",
            fg="#04131f",
            activebackground="#baf7ff",
            activeforeground="#04131f",
            font=("Segoe UI Semibold", 11),
            padx=16,
            pady=10,
            cursor="hand2",
        )
        self.install_button.pack(side="left")

        self.launch_button = tk.Button(
            actions,
            text="Launch DelagR",
            command=self.launch,
            relief="flat",
            bg="#7fb0ff",
            fg="#06101c",
            activebackground="#9ec5ff",
            activeforeground="#06101c",
            font=("Segoe UI Semibold", 11),
            padx=16,
            pady=10,
            cursor="hand2",
            state="disabled",
        )
        self.launch_button.pack(side="right")

    def _row(self, parent, title, description, var):
        frame = tk.Frame(parent, bg="#11213a", padx=16, pady=14, highlightbackground="#1f3d63", highlightthickness=1)
        frame.pack(fill="x", pady=7)
        left = tk.Frame(frame, bg="#11213a")
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, fg="#f6fbff", bg="#11213a", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(left, text=description, fg="#97adc2", bg="#11213a", font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=var, fg="#87ffc3", bg="#11213a", font=("Segoe UI Semibold", 10)).pack(side="right")

    def refresh_status(self):
        self.snapshot = collect_system_snapshot()
        self.status_vars["admin"].set("Ready" if self.snapshot.admin else "Missing")
        self.status_vars["webview"].set(self.snapshot.webview2_version)
        self.status_vars["wifi"].set(self.snapshot.wifi)

        self.launch_ready = self.snapshot.admin and self.snapshot.webview2_installed
        if self.launch_ready:
            self.status_vars["state"].set("Everything is ready. Launch DelagR when you are ready.")
            self.launch_button.config(state="normal")
            self.install_button.config(state="disabled")
        else:
            self.status_vars["state"].set("DelagR needs the missing items above before the main window can open.")
            self.launch_button.config(state="disabled")
            self.install_button.config(state="normal")

    def install_missing(self):
        self.install_button.config(state="disabled")
        self.status_vars["state"].set("Installing missing components. This can take a moment...")

        def worker():
            result_message = None
            if not self.snapshot.admin:
                self.status_vars["state"].set("Restarting as administrator...")
                relaunch_as_admin()
                return

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

    def run(self) -> SystemSnapshot | None:
        self.root.mainloop()
        return self.snapshot if self.launch_ready else None


def start_main_ui(snapshot: SystemSnapshot):
    api = DelagRAPI(snapshot)
    icon_path = ensure_runtime_icon()
    html = render_html(snapshot)

    window = webview.create_window(
        APP_NAME,
        html=html,
        js_api=api,
        width=1360,
        height=920,
        min_size=(900, 680),
        background_color="#07111f",
        text_select=False,
        icon=icon_path,
    )

    try:
        webview.start(gui="edgechromium")
    except Exception:
        webview.start()


def main():
    if not is_windows():
        raise SystemExit("DelagR is a Windows application.")

    wizard = SetupWizard()
    snapshot = wizard.run()
    if snapshot:
        start_main_ui(snapshot)


if __name__ == "__main__":
    main()
