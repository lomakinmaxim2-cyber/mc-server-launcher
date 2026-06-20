# MC Server Launcher

> A one-click GUI for setting up, managing, and running modded Minecraft servers — no command line needed.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![Releases](https://img.shields.io/github/v/release/lomakinmaxim2-cyber/mc-server-launcher)](https://github.com/lomakinmaxim2-cyber/mc-server-launcher/releases)

---

## Download

**No Python or Java required.**
Grab the latest `MCServerLauncher.exe` from the [Releases page](https://github.com/lomakinmaxim2-cyber/mc-server-launcher/releases) and run it directly.

---

## Features

### Server Setup
- **Guided 7-step wizard** — walks you from folder selection to a running server
- **One-click install** — downloads and runs the NeoForge / Forge / Fabric installer automatically
- **Add existing server** — points the launcher at an already-set-up folder and auto-detects loader + MC version
- **Persistent settings** — all fields (folders, loader, RAM, Chunky config) are saved to `launcher_config.json` and restored on next launch

### Modpacks & Mods
- **Modpack import** — Modrinth `.mrpack` (full auto-download) and CurseForge `.zip` (overrides + mod list)
- **Modrinth mod search** — search by name, filter by MC version and loader, install directly to your server's `mods/` folder
- **Mod sync** — copies mods from your client folder, skipping client-only mods automatically
- **Client-mod filter** — detects and removes mods like Sodium, Iris, OptiFine, and Xaero's that crash a dedicated server

### Java
- **Bundled Java download** — fetches a portable Temurin JDK from Adoptium into `runtime/jdk-<major>/`. Auto-picks Java 8 / 17 / 21 based on the MC version. Cached on disk — only downloaded once
- **Safe kill** — stops only the tracked server process (`taskkill /F /T /PID`), never your Minecraft client or other Java apps

### Tools
- **Chunky pre-generation** — built-in panel to configure and send Chunky commands (world, shape, radius, center). Buttons for Start, Pause, Resume, Cancel, Trim, Status
- **Server icon** — pick any image (PNG, JPG, WEBP, etc.); auto-resized and converted to the required 64x64 PNG and saved as `server-icon.png`
- **Vanilla server.jar fetcher** — downloads from Mojang with SHA1 verification and 3 retries (fixes Fabric's "Missing game jar" error)
- **Built-in console** — live server output + command input, no separate terminal needed
- **SSL auto-fallback** — handles broken cert stores common with DPI bypass tools on Windows
- **Hidden subprocesses** — no CMD windows pop up when running installers or the server

---

## Running from Source

```bash
pip install -r requirements.txt
python mc_server_launcher_9.py
```

### Building the exe locally

```bash
pip install -r dev-requirements.txt
python build.py
# output: dist/MCServerLauncher.exe
```

Releases are built automatically by GitHub Actions on every `v*` tag push.

---

## Quick Start (Wizard)

1. Click **Browse** and pick a server folder
2. Click **Import Modpack** or set a Mods folder
3. Confirm loader and MC version
4. Tick **Accept EULA** and set RAM
5. Click **Install Server** and wait
6. Click **Sync Mods** if using a mods folder
7. Click **Start Server**

Or use the **Guided Setup** bar to step through automatically.

---

## Supported Loaders

| Loader | Install method | Modpack formats |
|--------|---------------|-----------------|
| NeoForge | Maven installer | `.mrpack` |
| Forge | Maven installer | `.mrpack`, `.zip` |
| Fabric | Fabric installer + Mojang `server.jar` | `.mrpack` |

---

## License

MIT — see [LICENSE](LICENSE).
