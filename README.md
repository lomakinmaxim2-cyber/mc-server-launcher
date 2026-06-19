# MC Server Launcher

A desktop GUI tool for setting up and running Minecraft modded servers — no command-line knowledge required.

Supports **NeoForge**, **Forge**, and **Fabric** loaders. Import modpacks directly from Modrinth (`.mrpack`) or CurseForge (`.zip`), sync mods from your client folder, and launch the server — all from one window.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Features

- **Guided 7-step setup wizard** — walks you through every step from folder selection to first launch
- **One-click server install** — downloads and runs the NeoForge / Forge / Fabric installer automatically
- **Modpack import** — Modrinth `.mrpack` (full auto-download) and CurseForge `.zip` (overrides + mod list)
- **Mod sync** — copies mods from your client mods folder, skipping client-only mods automatically
- **Client-mod filter** — detects and removes mods like Sodium, Iris, OptiFine, Xaero's that crash a dedicated server
- **Add existing server** — auto-detects loader and MC version from an already-set-up server folder
- **Vanilla server.jar fetcher** — downloads from Mojang with SHA1 verification and retries (fixes Fabric's "Missing game jar" error)
- **Built-in console** — view server output and send commands without opening a terminal
- **Fixes & tools** — Java version check, EULA accept, stale session.lock cleanup, port conflict detection, targeted server kill button
- **Safe "Kill Java" button** — kills only the tracked server process (and its child tree), never your Minecraft client or other Java apps. Falls back to killing by port PID if no tracked process exists
- **SSL auto-fallback** — handles broken system cert stores (common with DPI bypass tools on Windows)

---

## Requirements

- **Python 3.8+** (tkinter included in most distributions)
- **Java 17+** on PATH — Java 21 recommended for MC 1.20.5+
  ```
  winget install Microsoft.OpenJDK.21
  ```
- Optional: `certifi` (`pip install certifi`) for better SSL handling on Windows

---

## Usage

```bash
python mc_server_launcher_9.py
```

### Quick start (wizard)

1. Click **Browse** and pick a folder for your server
2. Click **Import Modpack** to load a `.mrpack` or `.zip`, or set a **Mods folder** from your client
3. Confirm the loader and MC version in the dropdowns
4. Tick **Accept EULA** and set your RAM amount
5. Click **1. Install Server** — wait for it to finish
6. Click **2. Sync Mods** if you're using a separate mods folder
7. Click **3. Start Server**

Or use the **Guided Setup** bar to step through all of the above automatically.

---

## Supported Loaders

| Loader | Install method | Modpack format |
|--------|---------------|----------------|
| NeoForge | Maven installer | `.mrpack` |
| Forge | Maven installer | `.mrpack`, `.zip` |
| Fabric | Fabric installer + Mojang server.jar | `.mrpack` |

---

## License

MIT — see [LICENSE](LICENSE).
