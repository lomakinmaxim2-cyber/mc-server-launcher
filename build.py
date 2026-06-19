#!/usr/bin/env python3
"""Build MCServerLauncher.exe with PyInstaller."""
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "MCServerLauncher",
        "mc_server_launcher_9.py",
    ],
    check=True,
)
print("\nBuild complete -> dist/MCServerLauncher.exe")
