# DelagR

A lightweight Windows utility that reduces gaming lag spikes by disabling common Windows background features that interfere with low-latency network traffic. One file, one click, no manual setup required.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

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

## Installation

1. **Download** `DelagR.bat` from the [latest release](../../releases) (or clone this repo)
2. **Double-click** `DelagR.bat`

That's it. On first run, the app will automatically:
- Install Python if it's not already on your system
- Install the required UI framework (pywebview)
- Request administrator privileges (needed for network changes)
- Launch the app

Every subsequent launch is instant — it skips the setup steps.

## Usage

1. Double-click `DelagR.bat` before you start gaming
2. Toggle **Game Mode** ON to apply all optimizations at once, or toggle individual features as needed
3. When you're done gaming, toggle everything back OFF (or just close the app — changes persist until you revert them)

### Tips

- **Single-file app** — the icon is bundled inside `DelagR.bat`, so no companion icon file is required
- **Run as Admin** — The app auto-requests admin privileges, but if something isn't working, right-click the `.bat` file and select "Run as administrator"
- **Wi-Fi interface detection** — The app automatically detects your Wi-Fi adapter name, so it works regardless of whether Windows calls it "Wi-Fi", "WLAN", or something else
- **Process Boost** — Type your game's process name (without .exe) and click Boost while the game is running

## Screenshots

The app features a dark, modern UI with smooth animations, toggle switches for each optimization, and toast notifications for feedback.

## Requirements

- Windows 10 or 11
- Internet connection (first run only, for dependency installation)
- Administrator privileges

## How It Works

DelagR is a single batch file with an embedded Python application. The batch header handles dependency bootstrapping, then extracts and runs the Python code which uses pywebview to render a native window with a modern web-based UI. All optimizations are applied via standard Windows commands (`netsh`, `reg`, `powercfg`, `powershell`) and are fully reversible.

## Made with love by Fletcher Holt
