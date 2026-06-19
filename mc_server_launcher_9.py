#!/usr/bin/env python3
"""
Minecraft Server Launcher - GUI
Manages mods from a folder, picks loader (NeoForge / Forge / Fabric) and version,
installs the server, and launches it.

Requires: Java 17+ installed and on PATH.
Run: python mc_server_launcher.py
"""

import os
import sys
import ssl
import json
import shutil
import zipfile
import threading
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ---------- Endpoints ----------
NEOFORGE_META = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
FABRIC_GAME = "https://meta.fabricmc.net/v2/versions/game"
FABRIC_LOADER = "https://meta.fabricmc.net/v2/versions/loader"
FABRIC_INSTALLER = "https://meta.fabricmc.net/v2/versions/installer"
FORGE_META = "https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"
MC_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"

APP = "MC Server Launcher"

# Allow disabling cert verification when the system cert store is broken/expired
# (common on Windows + DPI bypass tools). Off by default; flipped on automatically
# after the first CERTIFICATE_VERIFY_FAILED, or via the checkbox in the UI.
INSECURE_SSL = False


def _ssl_context():
    """Prefer a verified context (using certifi if available), fall back to
    unverified if INSECURE_SSL is on."""
    if INSECURE_SSL:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mc-launcher"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY" in str(e) and not INSECURE_SSL:
            globals()["INSECURE_SSL"] = True
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
                return json.loads(r.read().decode())
        raise


def download(url, dest, log):
    log(f"Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "mc-launcher"})
    try:
        with urllib.request.urlopen(url=req, timeout=120, context=_ssl_context()) as r, \
                open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.URLError as e:
        # auto-fallback once on expired/failed cert verification
        if "CERTIFICATE_VERIFY" in str(e) and not INSECURE_SSL:
            globals()["INSECURE_SSL"] = True
            log("  SSL cert verify failed -> retrying without verification.")
            with urllib.request.urlopen(url=req, timeout=120, context=_ssl_context()) as r, \
                    open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
        else:
            raise
    log(f"Saved -> {dest}")


class Launcher(tk.Tk):
    # mods that only work on the client and crash a dedicated server
    CLIENT_ONLY = ["iris", "sodium", "xaero", "entityculling", "entity-culling",
                   "indium", "reeses", "betterf3", "modmenu", "mod-menu",
                   "optifine", "oculus", "rubidium", "embeddium", "continuity",
                   "lambdynamiclights", "lambdynamic", "3dskinlayers", "skinlayers",
                   "physicsmod", "iris-flw", "notenoughanimations", "soundphysics",
                   "dynamicfps", "fullbright", "zoomify", "cit-resewn", "citresewn",
                   "blur", "drippyloadingscreen", "screenshot", "controlling",
                   "fancymenu", "betterhud", "raised", "shouldersurfing"]

    def __init__(self):
        super().__init__()
        self.title(APP)
        self.geometry("820x720")
        self.minsize(760, 640)

        self.server_dir = tk.StringVar(value=os.path.abspath("./server"))
        self.mods_src = tk.StringVar(value="")
        self.loader = tk.StringVar(value="NeoForge")
        self.mc_version = tk.StringVar()
        self.loader_version = tk.StringVar()
        self.ram = tk.StringVar(value="4G")
        self.eula = tk.BooleanVar(value=False)
        self.online_mode = tk.BooleanVar(value=False)
        self.insecure_ssl = tk.BooleanVar(value=INSECURE_SSL)

        self.proc = None
        self._versions_cache = {}
        self._wiz_step = 0
        self._wiz_busy = False

        self._build_ui()
        self.refresh_versions()
        self.wizard_show()

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        # Server dir
        ttk.Label(top, text="Install / server folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.server_dir, width=54).grid(row=0, column=1, sticky="we")
        ttk.Button(top, text="Browse", command=self.pick_server_dir).grid(row=0, column=2, padx=2)

        # Mods source
        ttk.Label(top, text="Mods folder").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.mods_src, width=58).grid(row=1, column=1, sticky="we")
        ttk.Button(top, text="...", width=3, command=self.pick_mods_dir).grid(row=1, column=2)

        top.columnconfigure(1, weight=1)

        # Loader + versions
        mid = ttk.LabelFrame(self, text="Loader & Version")
        mid.pack(fill="x", **pad)

        ttk.Label(mid, text="Loader").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        cb = ttk.Combobox(mid, textvariable=self.loader, state="readonly",
                          values=["NeoForge", "Forge", "Fabric"], width=14)
        cb.grid(row=0, column=1, sticky="w", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_versions())

        ttk.Label(mid, text="MC version").grid(row=0, column=2, sticky="w", padx=6)
        self.mc_cb = ttk.Combobox(mid, textvariable=self.mc_version, state="readonly", width=14)
        self.mc_cb.grid(row=0, column=3, sticky="w", padx=6)
        self.mc_cb.bind("<<ComboboxSelected>>", lambda e: self.update_loader_versions())

        ttk.Label(mid, text="Loader version").grid(row=0, column=4, sticky="w", padx=6)
        self.lv_cb = ttk.Combobox(mid, textvariable=self.loader_version, state="readonly", width=18)
        self.lv_cb.grid(row=0, column=5, sticky="w", padx=6)

        ttk.Button(mid, text="Refresh", command=self.refresh_versions).grid(row=0, column=6, padx=6)

        # Options
        opt = ttk.LabelFrame(self, text="Options")
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="RAM").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        ttk.Combobox(opt, textvariable=self.ram, width=8, state="readonly",
                     values=["1G", "2G", "3G", "4G", "6G", "8G", "12G", "16G"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(opt, text="Accept EULA", variable=self.eula).grid(row=0, column=2, padx=12)
        ttk.Checkbutton(opt, text="online-mode", variable=self.online_mode).grid(row=0, column=3, padx=6)
        ttk.Checkbutton(opt, text="Skip SSL verify", variable=self.insecure_ssl,
                        command=self._toggle_ssl).grid(row=0, column=4, padx=6)

        # Actions
        # Guided setup wizard
        wiz = ttk.LabelFrame(self, text="Guided Setup")
        wiz.pack(fill="x", **pad)
        self.step_label = ttk.Label(wiz, text="", font=("Segoe UI", 10, "bold"))
        self.step_label.pack(side="left", padx=8, pady=6)
        self.wiz_btn = ttk.Button(wiz, text="Start Setup", command=self.wizard_next)
        self.wiz_btn.pack(side="right", padx=8)
        ttk.Button(wiz, text="Reset", command=self.wizard_reset).pack(side="right", padx=2)

        act = ttk.Frame(self)
        act.pack(fill="x", **pad)
        ttk.Button(act, text="Import Modpack", command=self.run_import_pack).pack(side="left", padx=4)
        ttk.Button(act, text="Add Existing Server", command=self.add_existing_server).pack(side="left", padx=4)
        ttk.Separator(act, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(act, text="1. Install Server", command=self.run_install).pack(side="left", padx=4)
        ttk.Button(act, text="2. Sync Mods", command=self.run_sync_mods).pack(side="left", padx=4)
        ttk.Button(act, text="3. Start Server", command=self.run_start).pack(side="left", padx=4)
        ttk.Button(act, text="Stop", command=self.stop_server).pack(side="left", padx=4)

        # Fixes & tools
        fix = ttk.LabelFrame(self, text="Fixes & Tools")
        fix.pack(fill="x", **pad)
        ttk.Button(fix, text="Fix: Download server.jar",
                   command=self.run_fix_serverjar).pack(side="left", padx=4, pady=4)
        ttk.Button(fix, text="Fix: Accept EULA",
                   command=self.fix_eula).pack(side="left", padx=4)
        ttk.Button(fix, text="Fix: Java check",
                   command=self.run_java_check).pack(side="left", padx=4)
        ttk.Button(fix, text="Check Mods",
                   command=self.run_check_mods).pack(side="left", padx=4)
        ttk.Button(fix, text="Open Install Log",
                   command=self.open_install_log).pack(side="left", padx=4)
        ttk.Button(fix, text="Kill Java",
                   command=self._kill_java).pack(side="left", padx=4)
        ttk.Button(fix, text="Delete Client Mods",
                   command=self.delete_client_mods).pack(side="left", padx=4)
        ttk.Separator(fix, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(fix, text="Delete Server",
                   command=self.delete_server).pack(side="left", padx=4)

        # Console
        con = ttk.LabelFrame(self, text="Console")
        con.pack(fill="both", expand=True, **pad)
        self.console = scrolledtext.ScrolledText(con, height=16, bg="#101418", fg="#d6e2ee",
                                                 insertbackground="#d6e2ee", font=("Consolas", 9))
        self.console.pack(fill="both", expand=True, padx=4, pady=4)

        cmd = ttk.Frame(con)
        cmd.pack(fill="x", padx=4, pady=4)
        self.cmd_entry = ttk.Entry(cmd)
        self.cmd_entry.pack(side="left", fill="x", expand=True)
        self.cmd_entry.bind("<Return>", lambda e: self.send_command())
        ttk.Button(cmd, text="Send", command=self.send_command).pack(side="left", padx=4)

    # ---------- guided wizard ----------
    # Each step: (label shown to user, method to run, whether it runs in a thread)
    def _wiz_steps(self):
        return [
            ("Step 1/7: Pick your install folder (click Browse), then Next",
             self._wiz_check_folder, False),
            ("Step 2/7: Import a modpack OR pick a mods folder, then Next",
             self._wiz_check_pack, False),
            ("Step 3/7: Confirm loader + MC version are correct, then Next",
             self._wiz_check_version, False),
            ("Step 4/7: Accept EULA + set RAM (doing it now)",
             self._wiz_eula_ram, False),
            ("Step 5/7: Installing the server (this can take a minute)",
             self._install, True),
            ("Step 6/7: Checking mods for problems",
             self._wiz_check_mods, True),
            ("Step 7/7: Starting the server",
             self._start, True),
        ]

    def wizard_show(self, done_step=None):
        steps = self._wiz_steps()
        if done_step:
            # briefly show the completed step, then advance the label
            self.step_label.config(text=f"Step {done_step} Done", foreground="green")
            self.after(900, lambda: self._wiz_show_current())
            return
        self._wiz_show_current()

    def _wiz_show_current(self):
        steps = self._wiz_steps()
        self.step_label.config(foreground="")
        if self._wiz_step >= len(steps):
            self.step_label.config(text="All steps Done. Server running (or check console).")
            self.wiz_btn.config(text="Done", state="disabled")
            return
        label = steps[self._wiz_step][0]
        self.step_label.config(text=label)
        self.wiz_btn.config(text="Next  >", state="normal")

    def wizard_reset(self):
        self._wiz_step = 0
        self.wiz_btn.config(state="normal", text="Start Setup")
        self.wizard_show()
        self.log("Wizard reset to step 1.")

    def wizard_next(self):
        if self._wiz_busy:
            return
        steps = self._wiz_steps()
        if self._wiz_step >= len(steps):
            return
        label, fn, threaded = steps[self._wiz_step]
        step_no = self._wiz_step + 1
        self.log(f">>> {label}")

        if threaded:
            self._wiz_busy = True
            self.wiz_btn.config(state="disabled", text="Working...")

            def run():
                ok = True
                try:
                    fn()
                except Exception as e:
                    self.log(f"Step error: {e}")
                    ok = False
                self.after(0, lambda: self._wiz_done(ok, step_no))
            self.threaded(run)
        else:
            # validation steps run inline and return True/False
            ok = fn()
            if ok:
                self.log(f"--- Step {step_no} Done ---")
                self._wiz_step += 1
                self.wizard_show(done_step=step_no)

    def _wiz_done(self, ok, step_no):
        self._wiz_busy = False
        if ok:
            self.log(f"--- Step {step_no} Done ---")
            self._wiz_step += 1
            self.wizard_show(done_step=step_no)
        else:
            self.wizard_show()

    # --- individual wizard step checks ---
    def _wiz_check_folder(self):
        sd = self.server_dir.get().strip()
        if not sd:
            self.log("Pick a folder first (Browse).")
            return False
        try:
            sd.encode("ascii")
        except UnicodeEncodeError:
            self.log("Folder has non-English letters (e.g. Cyrillic). Rename it first.")
            return False
        os.makedirs(sd, exist_ok=True)
        self.log(f"Folder OK: {sd}")
        return True

    def _wiz_check_pack(self):
        # pass if a modpack was imported (mods exist) or a source mods folder is set
        sd = self.server_dir.get()
        mods_dir = os.path.join(sd, "mods")
        has_mods = os.path.isdir(mods_dir) and any(
            f.lower().endswith(".jar") for f in os.listdir(mods_dir))
        src = self.mods_src.get()
        has_src = src and os.path.isdir(src)
        if has_mods or has_src:
            self.log("Mods source OK.")
            return True
        self.log("No mods yet. Click 'Import Modpack' or set a Mods folder, then Next.")
        return False

    def _wiz_check_version(self):
        if not self.mc_version.get() or not self.loader_version.get():
            self.log("Pick MC version and loader version first.")
            return False
        self.log(f"Using {self.loader.get()} {self.loader_version.get()} "
                 f"for MC {self.mc_version.get()}.")
        return True

    def _wiz_eula_ram(self):
        self.eula.set(True)
        self.fix_eula()
        self.log(f"EULA accepted. RAM = {self.ram.get()}.")
        return True

    def _wiz_check_mods(self):
        # sync from source if provided, then run the normal check
        src = self.mods_src.get()
        if src and os.path.isdir(src):
            self._sync_mods()
        self._check_mods()

    # ---------- helpers ----------
    def log(self, msg):
        self.console.insert("end", str(msg) + "\n")
        self.console.see("end")
        self.update_idletasks()

    def _log_install(self, dest, note=""):
        """Append an installed-file record to install_log.txt in the server folder."""
        import datetime
        sd = self.server_dir.get()
        if not sd or not os.path.isdir(sd):
            return
        try:
            rel = os.path.relpath(dest, sd)
        except Exception:
            rel = dest
        try:
            size = os.path.getsize(dest)
            size_str = f"{round(size/1024,1)} KB"
        except Exception:
            size_str = "?"
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {rel}  ({size_str})" + (f"  {note}" if note else "")
        try:
            with open(os.path.join(sd, "install_log.txt"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _install_log_header(self, title):
        import datetime
        sd = self.server_dir.get()
        if not sd or not os.path.isdir(sd):
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(os.path.join(sd, "install_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n===== {title} @ {ts} =====\n")
        except Exception:
            pass

    def _download(self, url, dest, note=""):
        """Wrapper around download() that also records the file to install_log.txt."""
        download(url, dest, self.log)
        self._log_install(dest, note)

    def pick_server_dir(self):
        d = filedialog.askdirectory()
        if d:
            d = os.path.normpath(d)
            self.server_dir.set(d)
            self._warn_non_ascii(d)

    def pick_mods_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.mods_src.set(os.path.normpath(d))

    def _warn_non_ascii(self, path):
        try:
            path.encode("ascii")
        except UnicodeEncodeError:
            bad = [c for c in path if ord(c) > 127]
            self.log(f"WARNING: path contains non-English letters {bad} "
                     f"(e.g. Cyrillic С vs Latin C). This can break Java. "
                     f"Rename the folder using English letters only.")

    def _toggle_ssl(self):
        globals()["INSECURE_SSL"] = self.insecure_ssl.get()
        state = "ON" if INSECURE_SSL else "OFF"
        self.log(f"Skip SSL verify: {state}")

    def threaded(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # ---------- version fetching ----------
    def refresh_versions(self):
        self.threaded(self._refresh_versions)

    def _refresh_versions(self):
        loader = self.loader.get()
        self.log(f"Fetching {loader} versions...")
        try:
            if loader == "NeoForge":
                data = http_json(NEOFORGE_META)
                vers = data.get("versions", [])
                # neoforge versions look like 21.1.73 -> MC 1.21.1
                mapping = {}
                for v in vers:
                    parts = v.split(".")
                    if len(parts) >= 2:
                        mc = f"1.{parts[0]}.{parts[1]}" if parts[1] != "0" else f"1.{parts[0]}"
                        mapping.setdefault(mc, []).append(v)
                self._versions_cache = {k: sorted(set(val), reverse=True) for k, val in mapping.items()}

            elif loader == "Fabric":
                games = http_json(FABRIC_GAME)
                stable = [g["version"] for g in games if g.get("stable")]
                loaders = http_json(FABRIC_LOADER)
                lvers = [l["version"] for l in loaders][:30]
                self._versions_cache = {mc: lvers for mc in stable}

            elif loader == "Forge":
                data = http_json(FORGE_META)
                # { "1.20.1": ["1.20.1-47.2.0", ...], ... }
                mapping = {}
                for entry in data.get("1.0", []) if isinstance(data, dict) and "1.0" in data else []:
                    pass
                # forge maven-metadata.json structure: top keys = mc versions
                mapping = {}
                for mc, builds in data.items():
                    short = [b.split("-", 1)[1] if "-" in b else b for b in builds]
                    mapping[mc] = sorted(set(short), reverse=True)
                self._versions_cache = mapping

            mc_versions = sorted(self._versions_cache.keys(),
                                 key=lambda s: [int(x) for x in s.replace("1.", "").split(".") if x.isdigit()],
                                 reverse=True)
            self.mc_cb["values"] = mc_versions
            if mc_versions:
                self.mc_version.set(mc_versions[0])
                self.update_loader_versions()
            self.log(f"Loaded {len(mc_versions)} MC versions for {loader}.")
        except Exception as e:
            self.log(f"ERROR fetching versions: {e}")

    def update_loader_versions(self):
        mc = self.mc_version.get()
        lv = self._versions_cache.get(mc, [])
        self.lv_cb["values"] = lv
        if lv:
            self.loader_version.set(lv[0])

    # ---------- install ----------
    def run_install(self):
        self.threaded(self._install)

    def _install(self):
        sd = self.server_dir.get()
        os.makedirs(sd, exist_ok=True)
        loader = self.loader.get()
        mc = self.mc_version.get()
        lv = self.loader_version.get()
        if not mc or not lv:
            self.log("Pick MC version and loader version first.")
            return
        self.log(f"=== Installing {loader} {lv} for MC {mc} ===")
        self._install_log_header(f"Install {loader} {lv} / MC {mc}")
        try:
            if loader == "NeoForge":
                jar = os.path.join(sd, "neoforge-installer.jar")
                url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{lv}/neoforge-{lv}-installer.jar"
                self._download(url, jar, note=f"NeoForge {lv} installer")
                self._java(["-jar", jar, "--installServer"], cwd=sd)
                self._log_install(jar, note="(installServer ran)")

            elif loader == "Forge":
                jar = os.path.join(sd, "forge-installer.jar")
                full = f"{mc}-{lv}"
                url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full}/forge-{full}-installer.jar"
                self._download(url, jar, note=f"Forge {full} installer")
                self._java(["-jar", jar, "--installServer"], cwd=sd)
                self._log_install(jar, note="(installServer ran)")

            elif loader == "Fabric":
                installers = http_json(FABRIC_INSTALLER)
                inst_ver = installers[0]["version"]
                jar = os.path.join(sd, "fabric-installer.jar")
                url = (f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/"
                       f"{inst_ver}/fabric-installer-{inst_ver}.jar")
                self._download(url, jar, note=f"Fabric installer {inst_ver}")
                # Install Fabric WITHOUT -downloadMinecraft (that step is flaky).
                # We fetch the vanilla server.jar straight from Mojang instead.
                self._java(["-jar", jar, "server", "-mcversion", mc,
                            "-loader", lv], cwd=sd)
                # Always get server.jar ourselves, with hash verification + retries.
                ok = self._fix_serverjar(verify=True)
                if not ok:
                    self.log("Could not obtain a valid server.jar. See messages above.")

            self._write_eula(sd)
            self._write_props(sd)
            os.makedirs(os.path.join(sd, "mods"), exist_ok=True)
            self.log("=== Install complete ===")
        except Exception as e:
            self.log(f"INSTALL ERROR: {e}")

    def _write_eula(self, sd):
        val = "true" if self.eula.get() else "false"
        with open(os.path.join(sd, "eula.txt"), "w") as f:
            f.write(f"eula={val}\n")
        if not self.eula.get():
            self.log("NOTE: EULA not accepted. Tick 'Accept EULA' before starting.")

    def _write_props(self, sd):
        p = os.path.join(sd, "server.properties")
        if os.path.exists(p):
            return
        with open(p, "w") as f:
            f.write(f"online-mode={'true' if self.online_mode.get() else 'false'}\n")
            f.write("motd=My Server\nmax-players=10\n")

    # ---------- fixes & tools ----------
    def run_fix_serverjar(self):
        self.threaded(lambda: self._fix_serverjar(verify=True))

    def _fix_serverjar(self, verify=True):
        """Download the vanilla server.jar from Mojang for the selected MC version,
        verify its SHA1, and retry on failure. Returns True on success.
        Fixes Fabric's 'Missing game jar' / 'server.jar is missing' errors."""
        sd = self.server_dir.get()
        os.makedirs(sd, exist_ok=True)
        mc = self.mc_version.get()
        if not mc:
            self.log("Pick an MC version first.")
            return False
        self.log(f"=== Fetching vanilla server.jar for {mc} ===")
        try:
            manifest = http_json(MC_MANIFEST)
            entry = next((v for v in manifest["versions"] if v["id"] == mc), None)
            if not entry:
                self.log(f"MC version {mc} not found in Mojang manifest.")
                return False
            meta = http_json(entry["url"])
            srv = meta.get("downloads", {}).get("server")
            if not srv:
                self.log(f"No dedicated server jar published for {mc}.")
                return False

            dest = os.path.join(sd, "server.jar")
            want_sha = srv.get("sha1")
            want_size = srv.get("size")

            for attempt in range(1, 4):
                self.log(f"Download attempt {attempt}/3...")
                try:
                    download(srv["url"], dest, self.log)
                except Exception as e:
                    self.log(f"  download failed: {e}")
                    continue

                size = os.path.getsize(dest)
                if want_size and size != want_size:
                    self.log(f"  size mismatch ({size} != {want_size}), retrying.")
                    continue

                if verify and want_sha:
                    got = self._sha1(dest)
                    if got.lower() != want_sha.lower():
                        self.log(f"  SHA1 mismatch, retrying.")
                        continue
                    self.log(f"  SHA1 verified OK.")

                # write the fabric properties so the launcher always finds it
                self._write_fabric_props(sd)
                self._log_install(dest, note="vanilla server.jar (SHA1 verified)")
                self.log(f"server.jar saved ({round(size/1024/1024,1)} MB) and verified. "
                         "Start Server now.")
                return True

            self.log("All 3 attempts failed. Check your internet / DPI bypass and retry.")
            return False
        except Exception as e:
            self.log(f"FIX ERROR: {e}")
            return False

    @staticmethod
    def _sha1(path):
        import hashlib
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _write_fabric_props(self, sd):
        """Pin the vanilla jar name so fabric-server-launch.jar always finds it."""
        p = os.path.join(sd, "fabric-server-launcher.properties")
        with open(p, "w") as f:
            f.write("serverJar=server.jar\n")


    def fix_eula(self):
        sd = self.server_dir.get()
        os.makedirs(sd, exist_ok=True)
        with open(os.path.join(sd, "eula.txt"), "w") as f:
            f.write("eula=true\n")
        self.eula.set(True)
        self.log("eula.txt set to true.")

    def run_java_check(self):
        self.threaded(self._java_check)

    def _java_check(self):
        self.log("=== Java check ===")
        try:
            p = subprocess.run(["java", "-version"], capture_output=True, text=True)
            out = (p.stderr or p.stdout).strip()
            self.log(out)
            line = out.splitlines()[0] if out else ""
            # crude major-version parse
            major = None
            if '"' in line:
                ver = line.split('"')[1]
                major = ver.split(".")[0]
                if major == "1":  # old scheme 1.8 etc
                    major = ver.split(".")[1]
            if major and major.isdigit():
                mj = int(major)
                if mj >= 21:
                    self.log("Java 21+ OK (good for 1.20.5+).")
                elif mj >= 17:
                    self.log("Java 17. OK for 1.17-1.20.4. For 1.20.5+ install Java 21.")
                else:
                    self.log("Java too old. Install Java 21: winget install Microsoft.OpenJDK.21")
        except FileNotFoundError:
            self.log("Java not found on PATH. Install: winget install Microsoft.OpenJDK.21")
        except Exception as e:
            self.log(f"JAVA CHECK ERROR: {e}")

    def run_check_mods(self):
        self.threaded(self._check_mods)

    def _check_mods(self):
        """Report what's actually in the server mods folder vs the source folder."""
        sd = self.server_dir.get()
        mods_dir = os.path.join(sd, "mods")
        self.log("=== Check Mods ===")
        if not os.path.isdir(mods_dir):
            self.log(f"No mods folder yet at {mods_dir}. Run Install or Import first.")
        else:
            jars = [f for f in os.listdir(mods_dir) if f.lower().endswith(".jar")]
            self.log(f"Server mods folder: {len(jars)} jar(s) in {mods_dir}")
            for f in sorted(jars):
                sz = os.path.getsize(os.path.join(mods_dir, f))
                flag = "  !! 0 bytes (bad download)" if sz == 0 else ""
                self.log(f"  - {f} ({round(sz/1024,1)} KB){flag}")
            if not jars:
                self.log("  (empty)")

        # compare to source mods folder if set
        src = self.mods_src.get()
        if src and os.path.isdir(src):
            src_jars = {f for f in os.listdir(src) if f.lower().endswith(".jar")}
            dst_jars = set(os.listdir(mods_dir)) if os.path.isdir(mods_dir) else set()
            missing = src_jars - dst_jars
            if missing:
                self.log(f"Not yet synced from source ({len(missing)}):")
                for f in sorted(missing):
                    self.log(f"  + {f}")
            else:
                self.log("Source folder fully synced.")

        # flag client-only leftovers (common server crash cause)
        if os.path.isdir(mods_dir):
            hits = [f for f in os.listdir(mods_dir)
                    if any(c in f.lower() for c in self.CLIENT_ONLY)]
            if hits:
                self.log(f"WARNING: {len(hits)} client-only mod(s) present (crash a server):")
                for f in hits:
                    self.log(f"  x {f}")
                self.log("Use 'Delete Client Mods' to remove them.")

    def delete_client_mods(self):
        sd = self.server_dir.get()
        mods_dir = os.path.join(sd, "mods")
        if not os.path.isdir(mods_dir):
            self.log("No mods folder found.")
            return
        hits = [f for f in os.listdir(mods_dir)
                if f.lower().endswith(".jar")
                and any(c in f.lower() for c in self.CLIENT_ONLY)]
        if not hits:
            self.log("No client-only mods detected. Nothing to remove.")
            return
        msg = "Remove these client-only mods from the server?\n\n" + "\n".join(hits)
        if not messagebox.askyesno(APP, msg):
            return
        # move to a backup folder instead of hard delete, so nothing is lost
        backup = os.path.join(sd, "_client_mods_removed")
        os.makedirs(backup, exist_ok=True)
        n = 0
        for f in hits:
            try:
                shutil.move(os.path.join(mods_dir, f), os.path.join(backup, f))
                self.log(f"  removed: {f}")
                n += 1
            except Exception as e:
                self.log(f"  failed: {f} ({e})")
        self.log(f"Moved {n} client-only mod(s) to {backup}")

    def delete_server(self):
        sd = self.server_dir.get()
        if not os.path.isdir(sd):
            self.log("Nothing to delete, folder doesn't exist.")
            return
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning(APP, "Stop the server before deleting.")
            return
        ok = messagebox.askyesno(
            APP, f"Permanently delete EVERYTHING in:\n\n{sd}\n\nThis cannot be undone.")
        if not ok:
            return
        # second guard for safety
        ok2 = messagebox.askyesno(APP, "Are you absolutely sure?")
        if not ok2:
            return
        try:
            shutil.rmtree(sd)
            self.log(f"Deleted: {sd}")
        except Exception as e:
            self.log(f"DELETE ERROR: {e}")

    # ---------- modpack import ----------
    def open_install_log(self):
        sd = self.server_dir.get()
        path = os.path.join(sd, "install_log.txt")
        if not os.path.exists(path):
            self.log("No install_log.txt yet. Install or import something first.")
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.log(f"Opened {path}")
        except Exception as e:
            self.log(f"Could not open log: {e}")

    def add_existing_server(self):
        """Point the launcher at an already-set-up server folder and auto-detect
        loader + version so you can just Start it."""
        d = filedialog.askdirectory(title="Select an existing server folder")
        if not d:
            return
        d = os.path.normpath(d)
        self.server_dir.set(d)
        self._warn_non_ascii(d)
        self.log(f"=== Adding existing server: {d} ===")
        files = os.listdir(d)
        low = [f.lower() for f in files]

        loader = None
        # Fabric: fabric server launch jar present
        if any("fabric-server-launch" in f or "fabric-server-launcher" in f for f in low):
            loader = "Fabric"
        # NeoForge: a neoforge folder/jar or run script referencing neoforge
        elif any("neoforge" in f for f in low) or os.path.isdir(os.path.join(d, "libraries", "net", "neoforged")):
            loader = "NeoForge"
        # Forge
        elif any("forge" in f for f in low) or os.path.isdir(os.path.join(d, "libraries", "net", "minecraftforge")):
            loader = "Forge"

        if loader:
            self.loader.set(loader)
            self.log(f"Detected loader: {loader}")
        else:
            self.log("Could not auto-detect loader. Pick it in the dropdown manually.")

        # try to detect MC version from a fabric jar name or mods
        ver = self._detect_mc_version(d, files)
        if ver:
            self.refresh_versions()
            self.after(1500, lambda: self._apply_detected_version(ver))
            self.log(f"Detected MC version: {ver}")
        else:
            self.log("Could not auto-detect MC version. Set it in the dropdown.")

        # report mods
        mods_dir = os.path.join(d, "mods")
        if os.path.isdir(mods_dir):
            jars = [f for f in os.listdir(mods_dir) if f.lower().endswith(".jar")]
            self.log(f"Found {len(jars)} mod(s) in this server.")

        # check eula
        eula_path = os.path.join(d, "eula.txt")
        if os.path.exists(eula_path):
            with open(eula_path) as f:
                if "eula=true" in f.read().lower():
                    self.eula.set(True)
                    self.log("EULA already accepted.")
        self.log("Ready. Tick EULA if needed, then click '3. Start Server'.")

    def _detect_mc_version(self, d, files):
        import re
        # fabric server jar often: fabric-server-mc.1.21.1-loader...
        for f in files:
            m = re.search(r"mc[.\-_](1\.\d+(?:\.\d+)?)", f.lower())
            if m:
                return m.group(1)
        # scan mod filenames for a version like 1.21.1
        mods_dir = os.path.join(d, "mods")
        if os.path.isdir(mods_dir):
            for f in os.listdir(mods_dir):
                m = re.search(r"(1\.\d{2}(?:\.\d+)?)", f)
                if m:
                    return m.group(1)
        return None

    def _apply_detected_version(self, ver):
        vals = list(self.mc_cb["values"])
        if ver in vals:
            self.mc_version.set(ver)
            self.update_loader_versions()

    def run_import_pack(self):
        path = filedialog.askopenfilename(
            title="Select modpack",
            filetypes=[("Modpacks", "*.mrpack *.zip"), ("All files", "*.*")])
        if path:
            self.threaded(lambda: self._import_pack(path))

    def _import_pack(self, path):
        low = path.lower()
        self.log(f"=== Importing modpack: {os.path.basename(path)} ===")
        self._install_log_header(f"Import modpack: {os.path.basename(path)}")
        try:
            if low.endswith(".mrpack"):
                self._import_mrpack(path)
            elif low.endswith(".zip"):
                self._import_curseforge(path)
            else:
                self.log("Unknown pack type. Use .mrpack (Modrinth) or .zip (CurseForge).")
        except Exception as e:
            self.log(f"IMPORT ERROR: {e}")

    def _import_mrpack(self, path):
        """Modrinth .mrpack: zip with modrinth.index.json + optional overrides/."""
        sd = self.server_dir.get()
        os.makedirs(sd, exist_ok=True)
        mods_dir = os.path.join(sd, "mods")
        os.makedirs(mods_dir, exist_ok=True)

        with zipfile.ZipFile(path) as z:
            with z.open("modrinth.index.json") as f:
                index = json.load(f)

            # auto-set loader + versions from the pack
            deps = index.get("dependencies", {})
            mc = deps.get("minecraft", "")
            if "fabric-loader" in deps:
                self._apply_pack_loader("Fabric", mc, deps["fabric-loader"])
            elif "neoforge" in deps:
                self._apply_pack_loader("NeoForge", mc, deps["neoforge"])
            elif "forge" in deps:
                self._apply_pack_loader("Forge", mc, deps["forge"])

            files = index.get("files", [])
            self.log(f"Pack '{index.get('name','?')}' lists {len(files)} files.")

            # folders that never belong on a server
            skip_dirs = ("resourcepacks/", "shaderpacks/", "resourcepack/",
                         "shaders/", "screenshots/", "saves/")

            got = skipped = 0
            for entry in files:
                fpath = entry.get("path", "").replace("\\", "/")
                fname = os.path.basename(fpath).lower()
                env = entry.get("env", {})

                # 1. explicit client-unsupported flag in the pack
                if env.get("server") == "unsupported":
                    skipped += 1
                    self.log(f"  skip (client-only): {fpath}")
                    continue
                # 2. resource/shader/etc folders
                if fpath.lower().startswith(skip_dirs):
                    skipped += 1
                    self.log(f"  skip (not a server file): {fpath}")
                    continue
                # 3. known client-only mod names (Sodium, Iris, Xaero, etc.)
                if fpath.lower().startswith("mods/") and \
                        any(c in fname for c in self.CLIENT_ONLY):
                    skipped += 1
                    self.log(f"  skip (client mod): {fpath}")
                    continue

                urls = entry.get("downloads", [])
                if not urls:
                    continue
                dest = os.path.join(sd, fpath.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                self._download(urls[0], dest, note="from modpack")
                got += 1
            self.log(f"Downloaded {got} server file(s), skipped {skipped} client-only.")

            # copy overrides (configs, etc.) but not client-only asset folders
            names = z.namelist()
            for pref in ("overrides/", "server-overrides/"):
                members = [n for n in names if n.startswith(pref) and not n.endswith("/")]
                copied = 0
                for n in members:
                    rel = n[len(pref):]
                    if rel.lower().startswith(skip_dirs):
                        continue
                    if rel.lower().startswith("mods/") and \
                            any(c in os.path.basename(rel).lower() for c in self.CLIENT_ONLY):
                        continue
                    dest = os.path.join(sd, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    copied += 1
                if copied:
                    self.log(f"Applied {copied} files from {pref}")
        self.log("=== mrpack import done. Now: Install Server, then Start. ===")

    def _import_curseforge(self, path):
        """CurseForge .zip: manifest.json (projectID/fileID) + overrides/.
        CF blocks direct downloads, so this extracts overrides and lists mods to fetch."""
        sd = self.server_dir.get()
        os.makedirs(sd, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "manifest.json" not in names:
                # not a CF pack, maybe a plain mods zip -> just extract jars
                self._extract_plain_zip(z, sd)
                return
            with z.open("manifest.json") as f:
                manifest = json.load(f)

            ml = manifest.get("minecraft", {}).get("modLoaders", [{}])
            loader_id = ml[0].get("id", "") if ml else ""
            mc = manifest.get("minecraft", {}).get("version", "")
            if loader_id.startswith("neoforge-"):
                self._apply_pack_loader("NeoForge", mc, loader_id.split("-", 1)[1])
            elif loader_id.startswith("forge-"):
                self._apply_pack_loader("Forge", mc, loader_id.split("-", 1)[1])
            elif loader_id.startswith("fabric-"):
                self._apply_pack_loader("Fabric", mc, loader_id.split("-", 1)[1])

            # extract overrides
            for n in names:
                if n.startswith("overrides/") and not n.endswith("/"):
                    rel = n[len("overrides/"):]
                    dest = os.path.join(sd, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)

            mods = manifest.get("files", [])
            self.log(f"Pack '{manifest.get('name','?')}' needs {len(mods)} CurseForge mods.")
            self.log("CurseForge blocks auto-download. Writing mod list to needed_mods.txt")
            listfile = os.path.join(sd, "needed_mods.txt")
            with open(listfile, "w") as out:
                for m in mods:
                    out.write(f"projectID={m.get('projectID')} fileID={m.get('fileID')}\n")
            self.log(f"-> {listfile}")
            self.log("Tip: open the pack on CurseForge and grab the SERVER pack zip, "
                     "which bundles mods directly.")
        self.log("=== CurseForge import done (overrides applied). ===")

    def _extract_plain_zip(self, z, sd):
        mods_dir = os.path.join(sd, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        n = 0
        for name in z.namelist():
            if name.lower().endswith(".jar") and not name.endswith("/"):
                dest = os.path.join(mods_dir, os.path.basename(name))
                with z.open(name) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                n += 1
        self.log(f"Plain zip: extracted {n} jars into mods/.")

    def _apply_pack_loader(self, loader, mc, lver):
        """Push loader/version values into the dropdowns from the main thread."""
        def apply():
            self.loader.set(loader)
            self._refresh_versions()
            if mc:
                self.mc_version.set(mc)
                self.update_loader_versions()
            if lver:
                self.loader_version.set(lver)
            self.log(f"Pack -> {loader} {lver} for MC {mc}")
        self.after(0, apply)

    # ---------- mods ----------
    def run_sync_mods(self):
        self.threaded(self._sync_mods)

    def _sync_mods(self):
        src = self.mods_src.get()
        if not src or not os.path.isdir(src):
            self.log("Pick a valid mods folder first.")
            return
        dst = os.path.join(self.server_dir.get(), "mods")
        os.makedirs(dst, exist_ok=True)
        n = 0
        for f in os.listdir(src):
            if f.lower().endswith(".jar"):
                target = os.path.join(dst, f)
                shutil.copy2(os.path.join(src, f), target)
                n += 1
                self.log(f"  + {f}")
                self._log_install(target, note="synced from mods folder")
        self.log(f"Synced {n} mod(s) -> {dst}")

    # ---------- run server ----------
    def _find_start(self, sd):
        loader = self.loader.get()
        files = os.listdir(sd) if os.path.isdir(sd) else []

        # Fabric: always launch the fabric server jar directly (no run.bat)
        if loader == "Fabric":
            for cand in ("fabric-server-launch.jar", "fabric-server-launcher.jar"):
                if cand in files:
                    return ("jar", cand)
            # fallback: any fabric jar that isn't the installer
            for f in files:
                fl = f.lower()
                if fl.endswith(".jar") and "fabric" in fl and "installer" not in fl:
                    return ("jar", f)
            return (None, None)

        # NeoForge / Forge (modern): prefer run.bat/run.sh, but only if non-empty
        script_names = ["run.bat", "run.sh"] if os.name == "nt" else ["run.sh", "run.bat"]
        for name in script_names:
            p = os.path.join(sd, name)
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return ("script", name)

        # Old Forge / fallback: a server jar
        for f in files:
            fl = f.lower()
            if (fl.endswith(".jar") and ("server" in fl or "forge" in fl)
                    and "installer" not in fl):
                return ("jar", f)
        return (None, None)

    def run_start(self):
        self.threaded(self._start)

    def _port_in_use(self, port):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            # if we can connect, something is listening
            return s.connect_ex(("127.0.0.1", port)) == 0
        finally:
            s.close()

    def _pid_on_port(self, port):
        """Return the PID listening on *port*, or None if not found."""
        try:
            if os.name == "nt":
                out = subprocess.check_output(
                    ["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
                for line in out.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            return int(parts[-1])
            else:
                out = subprocess.check_output(
                    ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL)
                pid = out.strip().splitlines()[0]
                if pid.isdigit():
                    return int(pid)
        except Exception:
            pass
        return None

    def _kill_java(self):
        self.log("Stopping server process...")
        try:
            if self.proc and self.proc.poll() is None:
                pid = self.proc.pid
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   capture_output=True, text=True)
                else:
                    import signal, os as _os
                    try:
                        _os.killpg(_os.getpgid(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        self.proc.kill()
                self.log(f"Server process (PID {pid}) terminated.")
            else:
                pid = self._pid_on_port(25565)
                if pid:
                    self.log(f"No tracked process; killing PID {pid} on port 25565.")
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                       capture_output=True, text=True)
                    else:
                        import signal
                        os.kill(pid, signal.SIGKILL)
                    self.log("Done.")
                else:
                    self.log("No server process found to kill.")
        except Exception as e:
            self.log(f"Could not stop server: {e}")

    def _clear_session_lock(self, sd):
        """Remove stale session.lock files left by a crashed run. Only safe because
        we already confirmed our own self.proc isn't running."""
        # read level-name from server.properties (default 'world')
        level = "world"
        props = os.path.join(sd, "server.properties")
        if os.path.exists(props):
            try:
                with open(props, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip().startswith("level-name="):
                            level = line.split("=", 1)[1].strip() or "world"
            except Exception:
                pass
        # overworld + nether/end dimension folders
        candidates = [
            os.path.join(sd, level, "session.lock"),
            os.path.join(sd, level, "DIM-1", "session.lock"),
            os.path.join(sd, level, "DIM1", "session.lock"),
        ]
        for lock in candidates:
            if os.path.exists(lock):
                try:
                    os.remove(lock)
                    self.log(f"Cleared stale lock: {os.path.relpath(lock, sd)}")
                except PermissionError:
                    self.log(f"Lock still held: {os.path.relpath(lock, sd)}. "
                             "A server is still running, close it (Task Manager > java.exe).")
                except Exception as e:
                    self.log(f"Could not clear lock: {e}")

    def _start(self):
        sd = self.server_dir.get()
        if self.proc and self.proc.poll() is None:
            self.log("Server already running.")
            return
        if not self.eula.get():
            self.log("Accept EULA first.")
            return
        # Clear a stale world lock left by a crashed/killed previous run.
        self._clear_session_lock(sd)
        # Warn if the server port is already taken (zombie java from a failed start).
        if self._port_in_use(25565):
            ok = messagebox.askyesno(
                APP,
                "Port 25565 is already in use, likely a leftover server process "
                "from a failed start.\n\nKill the process on that port and continue?")
            if ok:
                pid = self._pid_on_port(25565)
                if pid:
                    self.log(f"Killing PID {pid} on port 25565...")
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                       capture_output=True, text=True)
                    else:
                        import signal
                        os.kill(pid, signal.SIGKILL)
                else:
                    self._kill_java()
                self.after(800, lambda: self.threaded(self._start))
                return
            else:
                self.log("Port 25565 busy. Close the other server first.")
                return
        # Fabric needs the vanilla server.jar present. Auto-fetch if missing or corrupt.
        if self.loader.get() == "Fabric":
            sjar = os.path.join(sd, "server.jar")
            need = not os.path.exists(sjar) or os.path.getsize(sjar) < 1_000_000
            if need:
                if os.path.exists(sjar):
                    self.log("server.jar looks corrupt (too small), re-fetching...")
                else:
                    self.log("server.jar missing, fetching it before launch...")
                if not self._fix_serverjar(verify=True):
                    self.log("Cannot start without a valid server.jar.")
                    return
        kind, target = self._find_start(sd)
        ram = self.ram.get()
        if kind == "script":
            full = os.path.join(sd, target)
            if os.name == "nt":
                cmd = ["cmd", "/c", full]
            else:
                os.chmod(full, 0o755)
                cmd = ["bash", full]
            self.log(f"Starting via {target} ...")
        elif kind == "jar":
            jar_path = os.path.join(sd, target)
            cmd = ["java", f"-Xmx{ram}", f"-Xms{ram}", "-jar", jar_path, "nogui"]
            self.log(f"Starting jar {target} ...")
        else:
            self.log("No start script or server jar found. Install first.")
            return

        try:
            self.proc = subprocess.Popen(
                cmd, cwd=sd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace", env=self._utf8_env())
            threading.Thread(target=self._pump, daemon=True).start()
        except Exception as e:
            self.log(f"START ERROR: {e}")

    def _pump(self):
        for line in self.proc.stdout:
            self.log(line.rstrip())
        self.log("=== Server process ended ===")

    def send_command(self):
        c = self.cmd_entry.get().strip()
        if c and self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(c + "\n")
                self.proc.stdin.flush()
                self.cmd_entry.delete(0, "end")
            except Exception as e:
                self.log(f"CMD ERROR: {e}")

    def stop_server(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
                self.log("Stop sent.")
            except Exception:
                self.proc.terminate()
        else:
            self.log("No server running.")

    # ---------- java runner ----------
    def _utf8_env(self):
        """Force UTF-8 so Java + Python handle non-ASCII paths (e.g. Cyrillic)."""
        env = os.environ.copy()
        env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "")
                                    + " -Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8").strip()
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _java(self, args, cwd):
        # use absolute paths for any .jar arg so a weird cwd encoding can't break it
        fixed = []
        for a in args:
            if a.lower().endswith(".jar") and not os.path.isabs(a):
                cand = os.path.join(cwd, a)
                fixed.append(cand if os.path.exists(cand) else a)
            else:
                fixed.append(a)
        cmd = ["java"] + fixed
        self.log("RUN: java " + " ".join(fixed))
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1,
                             encoding="utf-8", errors="replace", env=self._utf8_env())
        for line in p.stdout:
            self.log(line.rstrip())
        p.wait()
        if p.returncode != 0:
            raise RuntimeError(f"java exited {p.returncode}")


if __name__ == "__main__":
    Launcher().mainloop()
