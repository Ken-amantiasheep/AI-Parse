"""
Client startup update checker for shared-drive deployment.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from packaging.version import InvalidVersion, Version

from version import __version__


APP_NAME = "AI-parse"
APP_FOLDER = "AI_parse"
SHARE_ROOT = Path(r"S:\Uploading Team") / APP_NAME
REMOTE_RELEASE_DIR = SHARE_ROOT / "release" / APP_FOLDER
REMOTE_METADATA_FILE = SHARE_ROOT / "metadata" / "version.json"
LOCAL_VERSION_FILE = Path("version.json")
UPDATER_RELATIVE_PATH = Path("updater") / "update_and_restart.cmd"
LAUNCHER_NAME = "start_gui.bat"


def _read_json_file(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _parse_version(raw: str) -> Optional[Version]:
    if not raw:
        return None
    try:
        return Version(str(raw).strip())
    except InvalidVersion:
        return None


def _get_local_install_root() -> Path:
    return Path(__file__).resolve().parent


def _get_local_version(install_root: Path) -> str:
    local_meta = _read_json_file(install_root / LOCAL_VERSION_FILE)
    if local_meta and local_meta.get("version"):
        return str(local_meta["version"])
    return __version__


def _build_fallback_updater_script() -> Path:
    temp_path = Path(tempfile.gettempdir()) / "ai_parse_update_and_restart.cmd"
    content = r"""@echo off
setlocal EnableDelayedExpansion
if "%~4"=="" (
  echo Usage: update_and_restart.cmd PID SOURCE_DIR TARGET_DIR LAUNCHER_BAT
  exit /b 1
)

set "APP_PID=%~1"
set "SRC_DIR=%~2"
set "DST_DIR=%~3"
set "LAUNCHER=%~4"

:waitLoop
tasklist /FI "PID eq %APP_PID%" 2>NUL | find /I "%APP_PID%" >NUL
if not errorlevel 1 (
  timeout /T 1 /NOBREAK >NUL
  goto waitLoop
)

if not exist "%DST_DIR%\logs" mkdir "%DST_DIR%\logs" >NUL 2>NUL
echo [%DATE% %TIME%] fallback updater started>>"%DST_DIR%\logs\updater.log"

robocopy "%SRC_DIR%" "%DST_DIR%" /MIR /R:2 /W:1 /XD logs output __pycache__ .git>>"%DST_DIR%\logs\updater.log" 2>&1

start "" "%DST_DIR%\%LAUNCHER%"
exit /b 0
"""
    temp_path.write_text(content, encoding="ascii")
    return temp_path


def _resolve_updater_script(install_root: Path) -> Path:
    updater = install_root / UPDATER_RELATIVE_PATH
    if updater.exists():
        return updater
    return _build_fallback_updater_script()


def run_startup_update_check(messagebox_module) -> bool:
    """
    Returns True when updater has been launched and caller should exit app startup.
    """
    install_root = _get_local_install_root()

    remote_meta = _read_json_file(REMOTE_METADATA_FILE)
    if not remote_meta:
        return False

    remote_version_raw = str(remote_meta.get("version", "")).strip()
    remote_version = _parse_version(remote_version_raw)
    local_version_raw = _get_local_version(install_root)
    local_version = _parse_version(local_version_raw)

    if remote_version is None or local_version is None:
        return False
    if remote_version <= local_version:
        return False

    if not REMOTE_RELEASE_DIR.exists():
        return False

    should_update = messagebox_module.askyesno(
        "发现新版本",
        (
            f"检测到新版本：{remote_version}\n"
            f"当前版本：{local_version}\n\n"
            "是否现在更新并重启软件？"
        ),
    )
    if not should_update:
        return False

    updater_script = _resolve_updater_script(install_root)
    cmd = [
        "cmd",
        "/c",
        str(updater_script),
        str(os.getpid()),
        str(REMOTE_RELEASE_DIR),
        str(install_root),
        LAUNCHER_NAME,
    ]
    try:
        subprocess.Popen(cmd, cwd=str(install_root))
    except Exception as exc:
        messagebox_module.showerror("更新失败", f"无法启动更新器：{exc}")
        return False

    messagebox_module.showinfo("开始更新", "程序将退出并自动更新，更新完成后会自动重启。")
    return True

