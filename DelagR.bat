@echo off
title DelagR
color 0A

:: Auto-elevate to admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

:: ---- Check Python ----
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [DelagR] Python not found - installing...
    echo.
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    if not exist "%TEMP%\python_installer.exe" (
        echo  ERROR: Failed to download Python. Check your internet.
        pause
        exit /b 1
    )
    start /wait "" "%TEMP%\python_installer.exe" /passive InstallAllUsers=1 PrependPath=1 Include_pip=1
    del "%TEMP%\python_installer.exe" 2>nul
    set "PATH=%ProgramFiles%\Python312\;%ProgramFiles%\Python312\Scripts\;%LocalAppData%\Programs\Python\Python312\;%LocalAppData%\Programs\Python\Python312\Scripts\;%PATH%"
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo  Python installed but not in PATH. Restart your PC and run this again.
        pause
        exit /b 1
    )
    echo  Python installed.
)

:: ---- Check pywebview ----
python -c "import webview" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [DelagR] Installing UI framework...
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install "pywebview>=4.0" >nul 2>&1
    python -c "import webview" >nul 2>&1
    if %errorlevel% neq 0 (
        echo  ERROR: Failed to install pywebview. Run: pip install pywebview
        pause
        exit /b 1
    )
    echo  Done.
    echo.
)

:: ---- Extract embedded Python and run ----
powershell -NoProfile -Command "$c = Get-Content '%~f0' -Raw -Encoding UTF8; $m = '#PYTHON_START'; $i = $c.IndexOf($m); if($i -ge 0){ $c.Substring($i + $m.Length + 2) | Set-Content '%TEMP%\game_optimizer_app.py' -Encoding UTF8 }"
python "%TEMP%\game_optimizer_app.py"
exit /b

#PYTHON_START
"""
DelagR - Kill lag spikes while gaming.
Run as Administrator for full functionality.
Made with love by Fletcher Holt.
"""

import base64
import subprocess
import ctypes
import sys
import webview


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


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    if not is_admin():
        script = subprocess.list2cmdline(sys.argv)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, script, None, 1
        )
        sys.exit()


def detect_wifi_interface():
    try:
        r = subprocess.run(
            'powershell -Command "Get-NetAdapter | Where-Object {$_.Status -eq \'Up\' -and ($_.InterfaceDescription -match \'Wi-Fi|Wireless|WLAN|802.11\')} | Select-Object -First 1 -ExpandProperty Name"',
            shell=True, capture_output=True, text=True, timeout=10,
        )
        name = r.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return "Wi-Fi"


def ensure_embedded_icon():
    import os
    import tempfile

    icon_path = os.path.join(tempfile.gettempdir(), "delagr_icon.ico")
    try:
        if not os.path.exists(icon_path):
            with open(icon_path, "wb") as f:
                f.write(base64.b64decode(ICON_ICO_BASE64))
        return icon_path
    except Exception:
        return None


class OptimizerAPI:

    def __init__(self, wifi_interface):
        self.wifi = wifi_interface
        self.wizard_dismissed = False

    def run_cmd(self, cmd, shell=True):
        try:
            r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=15)
            ok = r.returncode == 0
            return {"ok": ok, "out": r.stdout.strip(), "err": r.stderr.strip()}
        except Exception as e:
            return {"ok": False, "out": "", "err": str(e)}

    def get_wifi_name(self):
        return {"ok": True, "out": self.wifi, "err": ""}

    def is_wizard_dismissed(self):
        return {"ok": self.wizard_dismissed, "out": "", "err": ""}

    def dismiss_wizard(self):
        self.wizard_dismissed = True
        return {"ok": True, "out": "", "err": ""}

    def wifi_autoscan(self, enable: bool):
        flag = "no" if enable else "yes"
        return self.run_cmd(f'netsh wlan set autoconfig enabled={flag} interface="{self.wifi}"')

    def flush_dns(self):
        return self.run_cmd("ipconfig /flushdns")

    def tcp_autotuning(self, enable: bool):
        level = "disabled" if enable else "normal"
        return self.run_cmd(f"netsh int tcp set global autotuninglevel={level}")

    def nagle(self, enable: bool):
        r = self.run_cmd(
            'powershell -Command "Get-NetAdapter | Where-Object {$_.Status -eq \'Up\'} | Select-Object -ExpandProperty InterfaceGuid"'
        )
        if not r["ok"] or not r["out"]:
            return {"ok": False, "out": "", "err": "Could not find active adapter"}
        guids = r["out"].strip().splitlines()
        count = 0
        for guid in guids:
            guid = guid.strip()
            if not guid:
                continue
            key = f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\{guid}"
            val = "1" if enable else "0"
            self.run_cmd(f'reg add "{key}" /v TcpAckFrequency /t REG_DWORD /d {val} /f')
            self.run_cmd(f'reg add "{key}" /v TCPNoDelay /t REG_DWORD /d {val} /f')
            count += 1
        return {"ok": True, "out": f"Updated {count} adapter(s)", "err": ""}

    def net_throttle(self, enable: bool):
        key = "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile"
        val = "4294967295" if enable else "10"
        return self.run_cmd(f'reg add "{key}" /v NetworkThrottlingIndex /t REG_DWORD /d {val} /f')

    def wifi_power_save(self, enable: bool):
        val = "0" if enable else "1"
        return self.run_cmd(
            f'powershell -Command "'
            f"powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONNECTIVITY_IN_STANDBY {val}; "
            f'powercfg /setactive SCHEME_CURRENT"'
        )

    def optimize_dns(self, enable: bool):
        if enable:
            self.run_cmd(f'netsh interface ip set dns "{self.wifi}" static 1.1.1.1 primary')
            self.run_cmd(f'netsh interface ip add dns "{self.wifi}" 1.0.0.1 index=2')
            return {"ok": True, "out": "DNS set to Cloudflare 1.1.1.1", "err": ""}
        else:
            self.run_cmd(f'netsh interface ip set dns "{self.wifi}" dhcp')
            return {"ok": True, "out": "DNS reverted to DHCP", "err": ""}

    def kill_bandwidth_hogs(self):
        hogs = [
            "OneDrive.exe", "Dropbox.exe", "Teams.exe", "Slack.exe",
            "Spotify.exe", "EpicWebHelper.exe", "Update.exe",
            "MicrosoftEdgeUpdate.exe", "GoogleUpdate.exe", "iCloudServices.exe",
            "BackgroundTransferHost.exe", "SynologyDrive.exe",
        ]
        killed = []
        for proc in hogs:
            r = self.run_cmd(f"taskkill /f /im {proc} 2>nul")
            if r["ok"] and "SUCCESS" in r.get("out", ""):
                killed.append(proc.replace(".exe", ""))
        return {"ok": True, "out": f"Killed: {', '.join(killed) if killed else 'none running'}", "err": ""}

    def reset_network(self):
        self.run_cmd("netsh winsock reset")
        self.run_cmd("netsh int ip reset")
        self.run_cmd("ipconfig /flushdns")
        self.run_cmd("ipconfig /release")
        self.run_cmd("ipconfig /renew")
        return {"ok": True, "out": "Network stack reset. You may need to restart.", "err": ""}

    def game_bar(self, enable: bool):
        val = "0" if enable else "1"
        self.run_cmd(f'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\GameDVR" /v AppCaptureEnabled /t REG_DWORD /d {val} /f')
        self.run_cmd(f'reg add "HKCU\\System\\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d {val} /f')
        return {"ok": True, "out": f"Game Bar/DVR {'disabled' if enable else 'enabled'}", "err": ""}

    def boost_process(self, process_name: str):
        r = self.run_cmd(
            f'powershell -Command "$p = Get-Process -Name \'{process_name}\' -ErrorAction SilentlyContinue; '
            f"if ($p) {{ $p | ForEach-Object {{ $_.PriorityClass = 'High' }}; Write-Output 'BOOSTED' }} "
            f"else {{ Write-Output 'NOTFOUND' }}\""
        )
        out = r.get("out", "")
        if "BOOSTED" in out:
            return {"ok": True, "out": f"{process_name} set to High priority", "err": ""}
        return {"ok": False, "out": "", "err": f"Process '{process_name}' not found - is the game running?"}

    def delivery_optimization(self, enable: bool):
        val = "0" if enable else "1"
        self.run_cmd(f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\DeliveryOptimization\\Config" /v DODownloadMode /t REG_DWORD /d {val} /f')
        return {"ok": True, "out": f"Delivery Optimization {'disabled' if enable else 'enabled'}", "err": ""}

    def location_tracking(self, enable: bool):
        val = "Deny" if enable else "Allow"
        self.run_cmd(f'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location" /v Value /t REG_SZ /d {val} /f')
        return {"ok": True, "out": f"Location tracking {'disabled' if enable else 'enabled'}", "err": ""}

    def game_mode(self, enable: bool):
        results = []
        results.append(("Wi-Fi AutoScan", self.wifi_autoscan(enable)))
        results.append(("TCP AutoTuning", self.tcp_autotuning(enable)))
        results.append(("Nagle's Algorithm", self.nagle(enable)))
        results.append(("Net Throttling", self.net_throttle(enable)))
        results.append(("Fast DNS", self.optimize_dns(enable)))
        results.append(("Game Bar/DVR", self.game_bar(enable)))
        results.append(("Delivery Opt", self.delivery_optimization(enable)))
        results.append(("Location", self.location_tracking(enable)))
        if enable:
            results.append(("Flush DNS", self.flush_dns()))
        summary = "; ".join(f"{n}: {'OK' if r['ok'] else 'FAIL'}" for n, r in results)
        return {"ok": True, "out": summary, "err": ""}


HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DelagR</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --surface-hover: #1a1a26;
    --border: #1e1e2e;
    --text: #e4e4ef;
    --text-dim: #6e6e8a;
    --accent: #6c5ce7;
    --accent-glow: rgba(108, 92, 231, 0.3);
    --green: #00e676;
    --green-glow: rgba(0, 230, 118, 0.25);
    --red: #ff5252;
    --red-glow: rgba(255, 82, 82, 0.25);
    --orange: #ffab40;
    --radius: 16px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
  }

  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: #2a2a3a; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #3a3a4a; }

  body::before {
    content: '';
    position: fixed;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle at 50% 50%, rgba(108,92,231,0.03) 0%, transparent 50%);
    animation: bgPulse 8s ease-in-out infinite;
    pointer-events: none;
    z-index: 0;
  }

  @keyframes bgPulse {
    0%, 100% { transform: scale(1); opacity: 0.5; }
    50% { transform: scale(1.1); opacity: 1; }
  }

  .app {
    position: relative;
    z-index: 1;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 24px 20px;
  }

  .header {
    text-align: center;
    margin-bottom: 40px;
    animation: fadeInDown 0.6s ease-out;
  }

  .header h1 {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #fff 0%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
  }

  .header p { color: var(--text-dim); font-size: 0.9rem; }

  .admin-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-top: 12px;
  }
  .admin-badge.yes { background: var(--green-glow); color: var(--green); }
  .admin-badge.no  { background: var(--red-glow); color: var(--red); }
  .admin-badge .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor;
    animation: blink 2s ease-in-out infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .game-mode {
    background: linear-gradient(135deg, rgba(108,92,231,0.15) 0%, rgba(108,92,231,0.05) 100%);
    border: 1px solid rgba(108,92,231,0.3);
    border-radius: var(--radius);
    padding: 28px;
    margin-bottom: 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    animation: fadeInUp 0.5s ease-out 0.1s both;
    transition: all 0.4s ease;
  }

  .game-mode:hover {
    border-color: rgba(108,92,231,0.5);
    box-shadow: 0 0 40px rgba(108,92,231,0.1);
  }

  .game-mode.active {
    background: linear-gradient(135deg, rgba(0,230,118,0.12) 0%, rgba(0,230,118,0.03) 100%);
    border-color: rgba(0,230,118,0.4);
    box-shadow: 0 0 60px rgba(0,230,118,0.08);
  }

  .game-mode .info h2 { font-size: 1.3rem; font-weight: 700; margin-bottom: 4px; }
  .game-mode .info p { color: var(--text-dim); font-size: 0.85rem; line-height: 1.5; }

  .toggle {
    position: relative;
    width: 56px;
    height: 30px;
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle input { display: none; }

  .toggle .slider {
    position: absolute;
    inset: 0;
    background: #2a2a3a;
    border-radius: 15px;
    transition: all 0.4s cubic-bezier(0.68, -0.15, 0.27, 1.15);
  }

  .toggle .slider::before {
    content: '';
    position: absolute;
    width: 22px; height: 22px;
    left: 4px; top: 4px;
    background: #fff;
    border-radius: 50%;
    transition: all 0.4s cubic-bezier(0.68, -0.15, 0.27, 1.15);
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }

  .toggle input:checked + .slider {
    background: var(--green);
    box-shadow: 0 0 20px var(--green-glow);
  }

  .toggle input:checked + .slider::before { transform: translateX(26px); }

  .toggle.large { width: 68px; height: 36px; }
  .toggle.large .slider { border-radius: 18px; }
  .toggle.large .slider::before { width: 28px; height: 28px; left: 4px; top: 4px; }
  .toggle.large input:checked + .slider::before { transform: translateX(32px); }
  .toggle.disabled { opacity: 0.4; pointer-events: none; }

  .section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-dim);
    margin-bottom: 16px;
    padding-left: 4px;
    animation: fadeInUp 0.5s ease-out 0.2s both;
  }

  .cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 32px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px;
    transition: all 0.35s ease;
    animation: fadeInUp 0.5s ease-out both;
    position: relative;
    overflow: hidden;
  }

  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 3px;
    background: linear-gradient(90deg, var(--accent), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .card:hover {
    background: var(--surface-hover);
    border-color: rgba(108,92,231,0.3);
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
  }

  .card:hover::before { opacity: 1; }
  .card.active { border-color: rgba(0,230,118,0.2); }
  .card.active::before { background: linear-gradient(90deg, var(--green), transparent); opacity: 1; }

  .card .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }

  .card .icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    background: rgba(108,92,231,0.12);
    transition: background 0.3s ease;
  }

  .card.active .icon { background: rgba(0,230,118,0.12); }
  .card h3 { font-size: 0.95rem; font-weight: 600; margin-bottom: 6px; }
  .card p { font-size: 0.78rem; color: var(--text-dim); line-height: 1.5; }

  .actions {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
    margin-bottom: 32px;
  }

  .btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    color: var(--text);
    font-family: inherit;
    cursor: pointer;
    transition: all 0.35s ease;
    animation: fadeInUp 0.5s ease-out both;
    text-align: center;
  }

  .btn:hover {
    background: var(--surface-hover);
    border-color: rgba(108,92,231,0.3);
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
  }

  .btn:active { transform: translateY(0) scale(0.98); }
  .btn .icon { font-size: 1.5rem; margin-bottom: 8px; }
  .btn h3 { font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }
  .btn p { font-size: 0.72rem; color: var(--text-dim); line-height: 1.4; }
  .btn.danger:hover { border-color: rgba(255,82,82,0.4); box-shadow: 0 8px 30px rgba(255,82,82,0.1); }
  .btn.warn:hover { border-color: rgba(255,171,64,0.4); box-shadow: 0 8px 30px rgba(255,171,64,0.1); }

  .toast-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    display: flex;
    flex-direction: column-reverse;
    gap: 8px;
    z-index: 9999;
  }

  .toast {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 20px;
    font-size: 0.82rem;
    font-family: 'Inter', sans-serif;
    color: var(--text);
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    max-width: 340px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .toast.success { border-left: 3px solid var(--green); }
  .toast.error   { border-left: 3px solid var(--red); }
  .toast.info    { border-left: 3px solid var(--accent); }
  .toast.removing { animation: toastOut 0.3s ease-in forwards; }

  @keyframes toastIn {
    from { opacity: 0; transform: translateY(20px) scale(0.95); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  @keyframes toastOut { to { opacity: 0; transform: translateX(40px); } }

  .loading .slider::after {
    content: '';
    position: absolute;
    top: 50%; left: 50%;
    width: 14px; height: 14px;
    margin: -7px 0 0 -7px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .btn.running { pointer-events: none; opacity: 0.7; }
  .btn.running::after {
    content: '';
    display: block;
    width: 18px; height: 18px;
    margin: 8px auto 0;
    border: 2px solid rgba(255,255,255,0.2);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes fadeInDown {
    from { opacity: 0; transform: translateY(-20px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .card:nth-child(1) { animation-delay: 0.15s; }
  .card:nth-child(2) { animation-delay: 0.2s; }
  .card:nth-child(3) { animation-delay: 0.25s; }
  .card:nth-child(4) { animation-delay: 0.3s; }
  .card:nth-child(5) { animation-delay: 0.35s; }
  .card:nth-child(6) { animation-delay: 0.4s; }
  .card:nth-child(7) { animation-delay: 0.45s; }
  .card:nth-child(8) { animation-delay: 0.5s; }
  .card:nth-child(9) { animation-delay: 0.55s; }
  .actions .btn:nth-child(1) { animation-delay: 0.6s; }
  .actions .btn:nth-child(2) { animation-delay: 0.65s; }
  .actions .btn:nth-child(3) { animation-delay: 0.7s; }

  .boost-row {
    display: flex;
    gap: 12px;
    margin-bottom: 32px;
    animation: fadeInUp 0.5s ease-out 0.75s both;
  }

  .boost-input {
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 18px;
    color: var(--text);
    font-family: inherit;
    font-size: 0.85rem;
    outline: none;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
  }

  .boost-input:focus { border-color: var(--accent); box-shadow: 0 0 20px var(--accent-glow); }
  .boost-input::placeholder { color: var(--text-dim); }

  .boost-btn {
    background: linear-gradient(135deg, #6c5ce7, #a855f7);
    border: none;
    border-radius: 12px;
    padding: 14px 24px;
    color: #fff;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    white-space: nowrap;
  }

  .boost-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(108,92,231,0.3); }
  .boost-btn:active { transform: translateY(0) scale(0.98); }
  .boost-btn.running { opacity: 0.7; pointer-events: none; }

  .footer {
    text-align: center;
    padding: 24px 0 8px;
    color: var(--text-dim);
    font-size: 0.75rem;
    animation: fadeInUp 0.5s ease-out 0.8s both;
  }

  .footer span {
    background: linear-gradient(135deg, var(--text-dim), var(--accent));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .footer .heart {
    display: inline-block;
    color: #ff5252;
    -webkit-text-fill-color: #ff5252;
    animation: heartbeat 1.5s ease-in-out infinite;
  }

  @keyframes heartbeat {
    0%, 100% { transform: scale(1); }
    15% { transform: scale(1.25); }
    30% { transform: scale(1); }
    45% { transform: scale(1.15); }
    60% { transform: scale(1); }
  }

  .wizard-overlay {
    position: fixed;
    inset: 0;
    background: var(--bg);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.5s ease, transform 0.5s ease;
  }
  .wizard-overlay.hiding { opacity: 0; transform: scale(1.05); pointer-events: none; }
  .wizard-overlay.hidden { display: none; }

  .wizard {
    text-align: center;
    max-width: 520px;
    padding: 40px;
    animation: fadeInUp 0.6s ease-out;
  }

  .wizard-logo {
    font-size: 3.5rem;
    margin-bottom: 20px;
    animation: float 3s ease-in-out infinite;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }

  .wizard h1 {
    font-size: 1.8rem;
    font-weight: 800;
    background: linear-gradient(135deg, #fff 0%, #6c5ce7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 12px;
  }

  .wizard > p { color: var(--text-dim); font-size: 0.9rem; line-height: 1.6; margin-bottom: 32px; }

  .wizard .steps { text-align: left; margin-bottom: 36px; }

  .wizard .step {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
    animation: fadeInUp 0.4s ease-out both;
  }

  .wizard .step:nth-child(1) { animation-delay: 0.2s; }
  .wizard .step:nth-child(2) { animation-delay: 0.35s; }
  .wizard .step:nth-child(3) { animation-delay: 0.5s; }
  .wizard .step:nth-child(4) { animation-delay: 0.65s; }

  .wizard .step .num {
    width: 32px; height: 32px;
    border-radius: 50%;
    background: rgba(108,92,231,0.15);
    color: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    flex-shrink: 0;
  }

  .wizard .step .check { background: var(--green-glow); color: var(--green); }
  .wizard .step-text h4 { font-size: 0.9rem; font-weight: 600; margin-bottom: 2px; }
  .wizard .step-text p { font-size: 0.78rem; margin-bottom: 0; color: var(--text-dim); }

  .wizard-btn {
    background: linear-gradient(135deg, #6c5ce7, #a855f7);
    border: none;
    border-radius: 12px;
    padding: 14px 40px;
    color: #fff;
    font-family: inherit;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    animation: fadeInUp 0.4s ease-out 0.8s both;
  }
  .wizard-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(108,92,231,0.4); }
  .wizard-btn:active { transform: translateY(0) scale(0.98); }

  @media (max-width: 600px) {
    .cards { grid-template-columns: 1fr; }
    .actions { grid-template-columns: 1fr; }
    .boost-row { flex-direction: column; }
  }
</style>
</head>
<body>
<div class="wizard-overlay" id="wizardOverlay">
  <div class="wizard">
    <div class="wizard-logo">&#127918;</div>
    <h1>Welcome to DelagR</h1>
    <p>Your one-stop toolkit for eliminating lag spikes and maximizing network performance while gaming.</p>
    <div class="steps">
      <div class="step">
        <div class="num check">&#10003;</div>
        <div class="step-text">
          <h4>Python Runtime</h4>
          <p>Installed and running</p>
        </div>
      </div>
      <div class="step">
        <div class="num check">&#10003;</div>
        <div class="step-text">
          <h4>PyWebView Engine</h4>
          <p>UI framework loaded</p>
        </div>
      </div>
      <div class="step">
        <div class="num" id="wiz-admin-icon">3</div>
        <div class="step-text">
          <h4>Administrator Access</h4>
          <p id="wiz-admin-text">Checking permissions...</p>
        </div>
      </div>
      <div class="step">
        <div class="num" id="wiz-wifi-icon">4</div>
        <div class="step-text">
          <h4>Wi-Fi Adapter</h4>
          <p id="wiz-wifi-text">Detecting interface...</p>
        </div>
      </div>
    </div>
    <button class="wizard-btn" onclick="dismissWizard()">Let's Go</button>
  </div>
</div>

<div class="app">
  <div class="header">
    <h1>DelagR</h1>
    <p>Kill lag spikes. Maximize performance.</p>
    <div class="admin-badge" id="adminBadge">
      <span class="dot"></span>
      <span id="adminText">Checking...</span>
    </div>
  </div>

  <div class="game-mode" id="gameModeCard">
    <div class="info">
      <h2>Game Mode</h2>
      <p>One-click: applies all optimizations below &mdash; Wi-Fi scan, Nagle, throttling, auto-tuning, DNS, Game Bar, Delivery Opt &amp; location.</p>
    </div>
    <label class="toggle large" id="gameModeToggle">
      <input type="checkbox" onchange="toggleGameMode(this.checked)">
      <span class="slider"></span>
    </label>
  </div>

  <div class="section-title">Network Tweaks</div>

  <div class="cards">
    <div class="card" id="card-autoscan">
      <div class="top">
        <div class="icon">&#128225;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('wifi_autoscan', this.checked, 'card-autoscan')"><span class="slider"></span></label>
      </div>
      <h3>Wi-Fi Auto-Scan</h3>
      <p>Windows constantly scans for nearby networks, causing 50-500ms lag spikes every 30-60s. Disable while gaming.</p>
    </div>

    <div class="card" id="card-autotuning">
      <div class="top">
        <div class="icon">&#128246;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('tcp_autotuning', this.checked, 'card-autotuning')"><span class="slider"></span></label>
      </div>
      <h3>TCP Auto-Tuning</h3>
      <p>Windows dynamically adjusts TCP receive window size. Disabling locks it to a consistent value, reducing jitter.</p>
    </div>

    <div class="card" id="card-nagle">
      <div class="top">
        <div class="icon">&#128640;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('nagle', this.checked, 'card-nagle')"><span class="slider"></span></label>
      </div>
      <h3>Nagle's Algorithm</h3>
      <p>Buffers small TCP packets to batch them. Great for throughput, terrible for gaming latency. Disable for instant delivery.</p>
    </div>

    <div class="card" id="card-throttle">
      <div class="top">
        <div class="icon">&#9889;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('net_throttle', this.checked, 'card-throttle')"><span class="slider"></span></label>
      </div>
      <h3>Network Throttling</h3>
      <p>Windows throttles network packets when multimedia apps run. Removing the limit gives games full bandwidth priority.</p>
    </div>

    <div class="card" id="card-powersave">
      <div class="top">
        <div class="icon">&#128267;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('wifi_power_save', this.checked, 'card-powersave')"><span class="slider"></span></label>
      </div>
      <h3>Wi-Fi Power Saving</h3>
      <p>Your adapter may enter low-power mode, adding latency. Disable to keep the radio at full power for consistent ping.</p>
    </div>

    <div class="card" id="card-dns">
      <div class="top">
        <div class="icon">&#127760;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('optimize_dns', this.checked, 'card-dns')"><span class="slider"></span></label>
      </div>
      <h3>Fast DNS (Cloudflare)</h3>
      <p>Switch to Cloudflare 1.1.1.1 &mdash; the fastest public DNS resolver. Speeds up server lookups when connecting to games.</p>
    </div>

    <div class="card" id="card-gamebar">
      <div class="top">
        <div class="icon">&#127918;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('game_bar', this.checked, 'card-gamebar')"><span class="slider"></span></label>
      </div>
      <h3>Game Bar / DVR</h3>
      <p>Xbox Game Bar and Game DVR record clips in the background, eating CPU, GPU, and disk I/O. Disable for pure performance.</p>
    </div>

    <div class="card" id="card-delivery">
      <div class="top">
        <div class="icon">&#128230;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('delivery_optimization', this.checked, 'card-delivery')"><span class="slider"></span></label>
      </div>
      <h3>Delivery Optimization</h3>
      <p>Windows uploads updates to other PCs via P2P, silently eating your upload bandwidth. Disable to reclaim it.</p>
    </div>

    <div class="card" id="card-location">
      <div class="top">
        <div class="icon">&#128205;</div>
        <label class="toggle"><input type="checkbox" onchange="toggle('location_tracking', this.checked, 'card-location')"><span class="slider"></span></label>
      </div>
      <h3>Location Tracking</h3>
      <p>Apps constantly ping location services, generating background network chatter. Disable to reduce noise on your connection.</p>
    </div>
  </div>

  <div class="section-title">Quick Actions</div>

  <div class="actions">
    <button class="btn" id="btn-flush" onclick="runAction('flush_dns', 'btn-flush')">
      <div class="icon">&#129529;</div>
      <h3>Flush DNS</h3>
      <p>Clear cached DNS entries to fix stale lookups and connection issues</p>
    </button>

    <button class="btn warn" id="btn-kill" onclick="runAction('kill_bandwidth_hogs', 'btn-kill')">
      <div class="icon">&#128298;</div>
      <h3>Kill Bandwidth Hogs</h3>
      <p>Close OneDrive, Teams, Spotify, Dropbox &amp; other background uploaders</p>
    </button>

    <button class="btn danger" id="btn-reset" onclick="runAction('reset_network', 'btn-reset')">
      <div class="icon">&#128260;</div>
      <h3>Reset Network Stack</h3>
      <p>Nuclear option: resets Winsock, IP config &amp; flushes everything. May require restart.</p>
    </button>
  </div>

  <div class="section-title">Process Priority</div>

  <div class="boost-row">
    <input type="text" id="process-input" class="boost-input" placeholder="e.g. FortniteClient-Win64-Shipping" spellcheck="false">
    <button class="boost-btn" id="btn-boost" onclick="boostProcess()">Boost to High Priority</button>
  </div>

  <div class="footer">
    <span>Made with <span class="heart">&#9829;</span> by Fletcher Holt</span>
  </div>
</div>

<div class="toast-container" id="toasts"></div>

<script>
  function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function toast(msg, type) {
    type = type || 'info';
    const container = document.getElementById('toasts');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    const icons = { success: '\u2705', error: '\u274c', info: '\u2139\ufe0f' };
    el.innerHTML = '<span>' + (icons[type] || '') + '</span><span>' + esc(msg) + '</span>';
    container.appendChild(el);
    setTimeout(function() {
      el.classList.add('removing');
      setTimeout(function() { el.remove(); }, 300);
    }, 4000);
  }

  function setCardActive(id, active) {
    var card = document.getElementById(id);
    if (!card) return;
    if (active) card.classList.add('active');
    else card.classList.remove('active');
  }

  async function call(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    try {
      var result = await window.pywebview.api[method].apply(null, args);
      if (result && result.ok) {
        toast(result.out || 'Done', 'success');
      } else {
        toast(result ? result.err || 'Failed' : 'Failed', 'error');
      }
      return result;
    } catch (e) {
      toast(String(e), 'error');
      return { ok: false };
    }
  }

  async function toggle(method, checked, cardId) {
    await call(method, checked);
    setCardActive(cardId, checked);
  }

  async function toggleGameMode(checked) {
    var card = document.getElementById('gameModeCard');
    var tgl = document.getElementById('gameModeToggle');
    tgl.classList.add('loading');
    document.querySelectorAll('.card .toggle').forEach(function(t) { t.classList.add('disabled'); });

    await call('game_mode', checked);

    tgl.classList.remove('loading');
    document.querySelectorAll('.card .toggle').forEach(function(t) { t.classList.remove('disabled'); });

    if (checked) {
      card.classList.add('active');
      document.querySelectorAll('.card input[type="checkbox"]').forEach(function(cb) { cb.checked = true; });
      document.querySelectorAll('.card').forEach(function(c) { c.classList.add('active'); });
    } else {
      card.classList.remove('active');
      document.querySelectorAll('.card input[type="checkbox"]').forEach(function(cb) { cb.checked = false; });
      document.querySelectorAll('.card').forEach(function(c) { c.classList.remove('active'); });
    }
  }

  async function runAction(method, btnId) {
    var btn = document.getElementById(btnId);
    btn.classList.add('running');
    await call(method);
    btn.classList.remove('running');
  }

  async function boostProcess() {
    var input = document.getElementById('process-input');
    var name = input.value.trim().replace(/\.exe$/i, '');
    if (!name) { toast('Enter a process name', 'error'); return; }
    var btn = document.getElementById('btn-boost');
    btn.classList.add('running');
    await call('boost_process', name);
    btn.classList.remove('running');
  }

  async function dismissWizard() {
    await window.pywebview.api.dismiss_wizard();
    var overlay = document.getElementById('wizardOverlay');
    overlay.classList.add('hiding');
    setTimeout(function() { overlay.classList.add('hidden'); }, 500);
  }

  document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('process-input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') boostProcess();
    });
  });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    relaunch_as_admin()

    wifi_name = detect_wifi_interface()
    api = OptimizerAPI(wifi_name)
    icon_path = ensure_embedded_icon()

    window = webview.create_window(
        "DelagR",
        html=HTML,
        js_api=api,
        width=920,
        height=900,
        min_size=(600, 500),
        background_color="#0a0a0f",
        text_select=False,
        icon=icon_path,
    )

    def on_loaded():
        admin = is_admin()
        badge_cls = "yes" if admin else "no"
        badge_txt = "Running as Admin" if admin else "Not Admin - some features may fail"
        adm_icon_cls = "num check" if admin else "num"
        adm_icon_txt = "\u2713" if admin else "!"
        adm_step_txt = "Elevated privileges granted" if admin else "Run as admin for full access"
        wifi_txt = api.wifi.replace("'", "\\'")

        window.evaluate_js(f"""
            document.getElementById('adminBadge').className = 'admin-badge {badge_cls}';
            document.getElementById('adminText').textContent = '{badge_txt}';
            document.getElementById('wiz-admin-icon').className = '{adm_icon_cls}';
            document.getElementById('wiz-admin-icon').textContent = '{adm_icon_txt}';
            document.getElementById('wiz-admin-text').textContent = '{adm_step_txt}';
            document.getElementById('wiz-wifi-icon').className = 'num check';
            document.getElementById('wiz-wifi-icon').textContent = '\u2713';
            document.getElementById('wiz-wifi-text').textContent = 'Detected: {wifi_txt}';
        """)

        if api.wizard_dismissed:
            window.evaluate_js("document.getElementById('wizardOverlay').classList.add('hidden');")

    window.events.loaded += on_loaded
    webview.start()
