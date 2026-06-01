# DelagR

A proper Windows desktop app for reducing gaming lag spikes with a polished glass-style UI, a first-run setup wizard, and a real `.exe` build pipeline.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Version](https://img.shields.io/badge/version-2.0.1-blueviolet)

## What's New in 2.0

- Animated **"Made for Josh"** intro splash on launch
- Reworked liquid-glass UI with staggered card entrances, hover micro-interactions, and a pulsing status glow
- Smoother toggles, an animated heartbeat footer, and `prefers-reduced-motion` support
- Fixed a launch crash caused by passing an unsupported `icon` argument to the WebView2 window
- Trimmed redundant system probes at startup for a faster first paint

## What It Does

When you're gaming on Wi-Fi, Windows runs background tasks that cause sudden lag spikes — scanning for nearby networks, uploading updates to other PCs, throttling your connection, and more. DelagR gives you a clean, modern UI to disable all of these with a single toggle, and re-enable them when you're done gaming.

## Use Case

DelagR is designed for players who get random ping spikes, jitter, or brief connection hiccups while gaming on Windows, especially over Wi-Fi. Instead of memorizing command-line tweaks or digging through registry edits, you can apply the most useful latency-focused changes from one interface and roll them back when your session is over.

### Optimizations

| Feature | What It Fixes |
|---------|--------------|
| **Game Mode** | Master toggle — applies all optimizations below at once |
| **Wi-Fi Auto-Scan** | Stops Windows from scanning for nearby networks every 30-60 seconds, which causes 50-500ms lag spikes |
| **TCP Auto-Tuning** | Locks TCP receive window to a consistent value, reducing jitter |
| **Nagle's Algorithm** | Disables TCP packet batching for instant packet delivery instead of buffered sends |
| **Network Throttling** | Removes the Windows multimedia network throttle that limits bandwidth during games |
| **Wi-Fi Power Saving** | Keeps your Wi-Fi adapter at full power instead of entering low-power mode |
| **Fast DNS (Cloudflare)** | Switches to Cloudflare's 1.1.1.1 DNS for faster server lookups |
| **Game Bar / DVR** | Disables Xbox Game Bar and background recording that eat CPU, GPU, and disk I/O |
| **Delivery Optimization** | Stops Windows from uploading updates to other PCs via peer-to-peer |
| **Location Tracking** | Disables background location pings that generate network chatter |

### Quick Actions

- **Flush DNS** — Clears cached DNS entries to fix stale lookups
- **Kill Bandwidth Hogs** — Closes OneDrive, Teams, Spotify, Dropbox, and other background uploaders
- **Reset Network Stack** — Full Winsock/IP reset for persistent connection issues
- **Process Priority Boost** — Set any running game to High priority for better CPU scheduling

## What Changed

DelagR is no longer built around a self-extracting batch file. The project is now structured as a packaged desktop app that builds into `DelagR.exe`.

- Native first-run setup wizard before the main UI opens
- WebView2 runtime detection and repair flow
- Build script for generating a proper Windows executable
- GitHub Actions workflow that can build the `.exe` on Windows
- Cleaner liquid-glass main interface with smoother motion and layout

## Installation

### End Users

1. Download `DelagR.exe` from the latest GitHub Release.
2. Launch `DelagR.exe`.
3. Let the setup wizard check your machine.
4. If WebView2 is missing, let DelagR install it automatically.
5. Enter the main app once the wizard shows everything as ready.

### GitHub Delivery

- Pushes to `main` build a Windows artifact automatically in GitHub Actions.
- Running `Build Windows EXE` manually with `release_version` set, for example `v0.1.1`, builds the app and publishes a GitHub Release in the same workflow.
- That release includes a single downloadable `DelagR.exe` asset.

### Building The EXE

1. Clone this repository on a Windows machine.
2. Install Python 3.12 or newer.
3. Run `./build_windows.ps1` from PowerShell.
4. The packaged app will be output as `dist/DelagR.exe`.

## Usage

1. Launch `DelagR.exe` before you start gaming.
2. Toggle **Game Mode** ON to apply all optimizations at once, or toggle individual features as needed
3. When you're done gaming, toggle everything back OFF (or just close the app — changes persist until you revert them)

### Tips

- **Proper desktop build** — the executable is generated with PyInstaller rather than shipped as a batch file
- **System dependency check** — the setup wizard verifies administrator access and the WebView2 runtime before launching the main UI
- **Run as Admin** — The app should request elevation when needed, but if Windows blocks that flow, right-click `DelagR.exe` and choose "Run as administrator"
- **Wi-Fi interface detection** — The app automatically detects your Wi-Fi adapter name, so it works regardless of whether Windows calls it "Wi-Fi", "WLAN", or something else
- **Process Boost** — Type your game's process name (without .exe) and click Boost while the game is running
- **Diagnostics export** — use Export Diagnostics to save a support snapshot to your desktop if something looks wrong
- **Whisky / Wine** — DelagR targets native Windows and is not expected to launch reliably under Whisky, Wine, or other compatibility layers

## Screenshots

The app features a dark, modern UI with smooth animations, toggle switches for each optimization, and toast notifications for feedback.

## Requirements

- Windows 10 or 11
- Internet connection (first run only, for dependency installation)
- Administrator privileges

## How It Works

DelagR now has two stages:

1. A native startup wizard checks the machine for the minimum Windows-side requirements, especially administrator access and the Microsoft Edge WebView2 runtime.
2. Once the system is ready, the main DelagR window opens using `pywebview`, rendering the glass-style interface and running the network/system optimizations via standard Windows commands such as `netsh`, `reg`, `powercfg`, and `powershell`.

The repo also includes a Windows build script and a GitHub Actions workflow so the app can be packaged as a real `DelagR.exe`.

## Made with love by Fletcher Holt
