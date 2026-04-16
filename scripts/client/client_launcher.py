"""
Local bootstrap launcher for AI-parse client.

Workflow:
1) Read local installed version.
2) Read release_manifest.json from S drive.
3) Prompt user when newer version exists.
4) Backup local app and fully replace local current app.
5) Launch local app/current/start_gui.bat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


VERSION_PATTERN = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']')
SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass
class VersionInfo:
    raw: str
    parsed: Tuple[int, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-parse local launcher")
    parser.add_argument("--install-root", help="Local install root path")
    parser.add_argument("--s-root", default=r"S:\Uploading Team\AI-parse", help="Remote S drive root")
    parser.add_argument("--skip-update", action="store_true", help="Skip update check")
    return parser.parse_args()


def infer_install_root(args_root: Optional[str]) -> Path:
    if args_root:
        return Path(args_root).expanduser().resolve()

    env_root = os.getenv("AI_PARSE_INSTALL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = Path(__file__).resolve()
    if current.parent.name.lower() == "bootstrap":
        return current.parent.parent
    if current.parent.name.lower() == "client" and current.parent.parent.name.lower() == "scripts":
        return current.parent.parent.parent
    return Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AI-parse"


def parse_semver(version: str) -> Optional[Tuple[int, int, int]]:
    if not version:
        return None
    match = SEMVER_PATTERN.match(version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def read_json(path: Path) -> Dict[str, Any]:
    # "utf-8-sig" can read both plain UTF-8 and UTF-8 BOM.
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return data


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_local_version_from_file(version_file: Path) -> Optional[str]:
    if not version_file.exists():
        return None
    for line in version_file.read_text(encoding="utf-8").splitlines():
        match = VERSION_PATTERN.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def read_remote_manifest(s_root: Path) -> Dict[str, Any]:
    manifest_path = s_root / "release_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"远端版本清单不存在: {manifest_path}")
    return read_json(manifest_path)


def get_latest_remote_version(manifest: Dict[str, Any]) -> Optional[VersionInfo]:
    current = str(manifest.get("currentVersion", "")).strip()
    parsed = parse_semver(current)
    if parsed is None:
        return None
    return VersionInfo(raw=current, parsed=parsed)


def get_local_version(state: Dict[str, Any], app_current: Path) -> Optional[VersionInfo]:
    state_version = str(state.get("installedVersion", "")).strip()
    parsed_state = parse_semver(state_version)
    if parsed_state:
        return VersionInfo(raw=state_version, parsed=parsed_state)

    file_version = read_local_version_from_file(app_current / "version.py")
    parsed_file = parse_semver(file_version or "")
    if parsed_file:
        return VersionInfo(raw=file_version or "", parsed=parsed_file)
    return None


def compare_versions(local_v: Optional[VersionInfo], remote_v: Optional[VersionInfo]) -> int:
    if remote_v is None:
        return 0
    if local_v is None:
        return -1
    if local_v.parsed < remote_v.parsed:
        return -1
    if local_v.parsed > remote_v.parsed:
        return 1
    return 0


def ask_user_for_update(remote_version: str, local_version: str) -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        answer = messagebox.askyesno(
            "发现新版本",
            (
                f"检测到新版本：{remote_version}\n"
                f"当前本地版本：{local_version or '未安装'}\n\n"
                "是否现在更新？"
            ),
        )
        root.destroy()
        return bool(answer)
    except Exception:
        # Tk dialog failed (e.g., running headless): default to no update.
        return False


def show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def show_info(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()
    except Exception:
        print(message)


def sync_local_state(state_file: Path, version: str, s_root: Path) -> None:
    state = {
        "installedVersion": version,
        "lastUpdatedAt": datetime.now().isoformat(),
        "remoteRoot": str(s_root),
    }
    write_json(state_file, state)


def resolve_remote_release_dir(s_root: Path, remote_version: str, manifest: Dict[str, Any]) -> Path:
    releases = manifest.get("releases", [])
    if isinstance(releases, list):
        for item in releases:
            if isinstance(item, dict) and str(item.get("version", "")).strip() == remote_version:
                rel_path = str(item.get("path", "")).strip()
                if rel_path:
                    return (s_root / rel_path).resolve()
    return s_root / "releases" / remote_version


def ensure_local_app_exists(app_current: Path, s_root: Path, manifest: Dict[str, Any], remote_version: str) -> None:
    if app_current.exists():
        return
    src = resolve_remote_release_dir(s_root, remote_version, manifest)
    if not src.exists():
        # fallback to remote current
        src = s_root / "current"
    if not src.exists():
        raise FileNotFoundError(f"无法找到远端程序目录: {src}")
    app_current.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, app_current, dirs_exist_ok=True)


def apply_full_update(
    install_root: Path,
    app_current: Path,
    local_releases: Path,
    s_root: Path,
    manifest: Dict[str, Any],
    remote_version: str,
    local_version_text: str,
) -> None:
    remote_release = resolve_remote_release_dir(s_root, remote_version, manifest)
    if not remote_release.exists():
        raise FileNotFoundError(f"远端版本目录不存在: {remote_release}")

    local_releases.mkdir(parents=True, exist_ok=True)
    if app_current.exists():
        backup_name = (local_version_text or "unknown") + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = local_releases / backup_name
        shutil.copytree(app_current, backup_dir, dirs_exist_ok=False)

    temp_parent = install_root / "app" / "_update_tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="release_", dir=str(temp_parent)))
    temp_release = temp_dir / "current"
    shutil.copytree(remote_release, temp_release, dirs_exist_ok=False)

    old_current = install_root / "app" / "_current_old"
    if old_current.exists():
        shutil.rmtree(old_current, ignore_errors=True)
    if app_current.exists():
        app_current.replace(old_current)

    try:
        temp_release.replace(app_current)
    except Exception:
        if old_current.exists() and not app_current.exists():
            old_current.replace(app_current)
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if old_current.exists():
            shutil.rmtree(old_current, ignore_errors=True)


def launch_gui(app_current: Path) -> int:
    launcher = app_current / "start_gui.bat"
    if not launcher.exists():
        raise FileNotFoundError(f"启动文件不存在: {launcher}")

    process = subprocess.Popen(
        ["cmd", "/c", str(launcher)],
        cwd=str(app_current),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return process.pid


def main() -> int:
    args = parse_args()
    install_root = infer_install_root(args.install_root)
    s_root = Path(args.s_root)

    bootstrap_dir = install_root / "bootstrap"
    state_file = bootstrap_dir / "local_state.json"
    app_current = install_root / "app" / "current"
    local_releases = install_root / "app" / "local_releases"

    state: Dict[str, Any] = {}
    if state_file.exists():
        try:
            state = read_json(state_file)
        except Exception:
            state = {}

    try:
        manifest = read_remote_manifest(s_root)
        remote = get_latest_remote_version(manifest)
    except Exception as exc:
        if not app_current.exists():
            show_error(f"S盘不可用且本地未安装程序：{exc}")
            return 1
        remote = None
        manifest = {}

    local = get_local_version(state, app_current)
    local_text = local.raw if local else ""

    if remote:
        ensure_local_app_exists(app_current, s_root, manifest, remote.raw)
        should_update = (not args.skip_update) and compare_versions(local, remote) < 0
        if should_update:
            if ask_user_for_update(remote.raw, local_text):
                apply_full_update(
                    install_root=install_root,
                    app_current=app_current,
                    local_releases=local_releases,
                    s_root=s_root,
                    manifest=manifest,
                    remote_version=remote.raw,
                    local_version_text=local_text or "unknown",
                )
                sync_local_state(state_file, remote.raw, s_root)
                show_info(f"已更新到版本 {remote.raw}，即将启动。")
            elif local is None:
                show_error("本地未安装有效版本，必须先更新后才能启动。")
                return 1
        elif local is None:
            # First install path: copy current remote into local.
            apply_full_update(
                install_root=install_root,
                app_current=app_current,
                local_releases=local_releases,
                s_root=s_root,
                manifest=manifest,
                remote_version=remote.raw,
                local_version_text="bootstrap",
            )
            sync_local_state(state_file, remote.raw, s_root)

    try:
        launch_gui(app_current)
        return 0
    except Exception as exc:
        show_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
