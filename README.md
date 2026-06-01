<div align="center">

# ⚡ DelagR

**A cross-platform, low-latency control room for gaming.**
Toggle packet-friendly network tweaks, clear background interference, and flip it all back when you're done.

![Windows](https://img.shields.io/badge/Windows-0D1B2A?logo=windows&logoColor=778DA9)
![macOS](https://img.shields.io/badge/macOS-1B263B?logo=apple&logoColor=778DA9)
![Linux](https://img.shields.io/badge/Linux-415A77?logo=linux&logoColor=E0E1DD)
![Version](https://img.shields.io/badge/version-2.1.1-778DA9)
![License](https://img.shields.io/badge/license-MIT-E0E1DD)

</div>

---

## Highlights

- **Runs natively on Windows, macOS & Linux** — one app, OS-aware tweaks.
- **Animated glass UI** with an intro splash, navy theme, and toast feedback.
- **Built-in updater** — a bar appears when a newer release lands on GitHub; one click downloads, swaps the binary, and relaunches.
- **Honest about platforms** — every tweak with a real equivalent works everywhere; the handful that are genuinely Windows-only stay visible but greyed.
- **Setup wizard** checks privileges and the renderer before launch.

## What each tweak does — and where it works

| Tweak | Windows | macOS | Linux | Notes |
|------|:------:|:----:|:----:|------|
| **Fast DNS (Cloudflare)** | ✅ | ✅ | ✅ | `netsh` / `networksetup` / `resolvectl` |
| **Flush DNS** | ✅ | ✅ | ✅ | resolver cache clear |
| **Kill bandwidth hogs** | ✅ | ✅ | ✅ | closes OneDrive, Dropbox, Spotify… |
| **Process priority boost** | ✅ | ✅ | ✅ | High priority / `renice` |
| **Reset network stack** | ✅ | ✅ | ✅ | heavier reset for stubborn issues |
| **Nagle's algorithm** | ✅ | ✅ | — | macOS uses `delayed_ack` sysctl |
| **TCP auto-tuning** | ✅ | — | ✅ | Linux uses `tcp_moderate_rcvbuf` |
| **Wi-Fi power saving** | ✅ | — | ✅ | Linux uses `iw … power_save` |
| **Delivery Optimization** | ✅ | ✅ | — | macOS maps to **Content Caching** |
| **Wi-Fi auto-scan** | ✅ | — | — | no safe equivalent elsewhere |
| **Network throttling index** | ✅ | — | — | Windows-only OS subsystem |
| **Game Bar / DVR** | ✅ | — | — | Windows-only OS subsystem |
| **Location tracking** | ✅ | — | — | Windows-only registry consent |

> Greyed (—) tweaks target OS subsystems that don't exist on that platform. They're shown but disabled — nothing fake or no-op.

## Install

Download the build for your OS from the [latest release](https://github.com/fletcherholt/DelagR/releases/latest):

| OS | File | First launch |
|----|------|--------------|
| **Windows** | `DelagR.exe` | Double-click. Approve the UAC prompt for tweaks. |
| **macOS** | `DelagR-macos` | `chmod +x DelagR-macos`, then right-click → **Open** (first time only, to clear Gatekeeper). DelagR asks for your password only when a tweak needs it. |
| **Linux** | `DelagR-linux` | `chmod +x DelagR-linux && ./DelagR-linux`. Privileged tweaks use `pkexec` (needs a polkit agent). |

## Updating

DelagR checks GitHub on launch. When a newer release exists, a bar slides in at the top:

```
┌─────────────────────────────────────┐
│ ⬆ DelagR v2.2.0 is available  [ Update now ] [ Later ] │
└─────────────────────────────────────┘
```

**Update now** downloads the right asset for your OS, replaces the running binary, and relaunches — no manual steps.

## Building from source

```bash
# Windows (PowerShell)
./build_windows.ps1        # -> dist/DelagR.exe

# macOS
./build_macos.sh           # -> dist/DelagR-macos

# Linux
./build_linux.sh           # -> dist/DelagR-linux
```

Pushes to `main` build all three via GitHub Actions. Running the **Build DelagR** workflow with a `release_version` (e.g. `v2.1.0`) publishes a release with all three binaries attached.

## How it works

A small setup wizard verifies privileges and the renderer, then the main window opens via [`pywebview`](https://pywebview.flowlib.org/) — EdgeChromium on Windows, Cocoa WebKit on macOS, QtWebEngine on Linux. Tweaks run through native commands (`netsh`/`reg`/`powercfg`, `networksetup`/`sysctl`/`AssetCacheManagerUtil`, `resolvectl`/`iw`/`nmcli`), elevating per-action via UAC, the macOS auth dialog, or `pkexec`.

---

<div align="center">

**♥ Made with love by Fletcher Holt**

</div>
