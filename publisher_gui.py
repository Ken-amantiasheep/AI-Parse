"""
Central publisher for shared-drive deployment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


APP_NAME = "AI-parse"
APP_FOLDER = "AI_parse"
DEFAULT_SHARE_ROOT = Path(r"S:\Uploading Team") / APP_NAME
VERSION_FILE = "version.py"


@dataclass
class PublishConfig:
    version: str
    share_root: Path

    @property
    def release_dir(self) -> Path:
        return self.share_root / "release" / APP_FOLDER

    @property
    def metadata_file(self) -> Path:
        return self.share_root / "metadata" / "version.json"

    @property
    def publisher_dir(self) -> Path:
        return self.share_root / "Publisher"

    @property
    def first_install_file(self) -> Path:
        return self.share_root / "FIRST_INSTALL.bat"


class PublisherEngine:
    def __init__(self, repo_root: Path, logger):
        self.repo_root = repo_root
        self.logger = logger

    def _run(self, cmd: List[str], cwd: Path | None = None) -> None:
        self.logger(f"> {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=str(cwd or self.repo_root),
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            self.logger(result.stdout.strip())
        if result.stderr.strip():
            self.logger(result.stderr.strip())
        if result.returncode != 0:
            raise RuntimeError(f"命令失败: {' '.join(cmd)}")

    def _update_source_version(self, version: str) -> None:
        version_path = self.repo_root / VERSION_FILE
        text = version_path.read_text(encoding="utf-8")
        text = re.sub(r'^__version__\s*=\s*".*"$', f'__version__ = "{version}"', text, flags=re.MULTILINE)
        text = re.sub(r"^APP_VERSION\s*=.*$", "APP_VERSION = __version__", text, flags=re.MULTILINE)
        version_path.write_text(text, encoding="utf-8")
        self.logger(f"已更新源码版本: {version}")

    def _build(self) -> None:
        # Lightweight build/validation step.
        self._run([sys.executable, "-m", "compileall", "-q", "."])
        self.logger("构建完成（compileall）")

    def _write_local_version_json(self, version: str) -> dict:
        payload = {
            "appName": APP_NAME,
            "appFolder": APP_FOLDER,
            "version": version,
            "builtAt": datetime.now().isoformat(),
            "launcher": "start_gui.bat",
        }
        (self.repo_root / "version.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger("已生成本地 version.json")
        return payload

    def _sync_release_payload(self, cfg: PublishConfig, version_payload: dict) -> None:
        include_items: Iterable[str] = (
            "config",
            "documents",
            "gateway_service",
            "scripts",
            "updater",
            "utils",
            "app_update.py",
            "gui_app_simple.py",
            "main.py",
            "preflight_check.py",
            "requirements.txt",
            "start_gui.bat",
            "start.bat",
            "run.bat",
            "version.py",
            "version.json",
            "README.md",
            "PUBLISH_README.md",
        )

        cfg.release_dir.parent.mkdir(parents=True, exist_ok=True)
        if cfg.release_dir.exists():
            shutil.rmtree(cfg.release_dir)
        cfg.release_dir.mkdir(parents=True, exist_ok=True)

        for item in include_items:
            src = self.repo_root / item
            dst = cfg.release_dir / item
            if not src.exists():
                continue
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # Guarantee updater in package.
        updater_path = cfg.release_dir / "updater" / "update_and_restart.cmd"
        if not updater_path.exists():
            raise RuntimeError("发布包缺少 updater/update_and_restart.cmd")

        # Keep release copy's version.json aligned with metadata payload.
        (cfg.release_dir / "version.json").write_text(
            json.dumps(version_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.logger(f"已同步发布包到: {cfg.release_dir}")

    def _sync_metadata_and_tools(self, cfg: PublishConfig, version_payload: dict) -> None:
        cfg.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        cfg.metadata_file.write_text(json.dumps(version_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger(f"已更新共享盘 metadata/version.json: {cfg.metadata_file}")

        # Sync publisher tools.
        cfg.publisher_dir.mkdir(parents=True, exist_ok=True)
        for name in ("publisher_gui.py", "RUN_PUBLISHER.bat", "PUBLISH_README.md"):
            src = self.repo_root / name
            if src.exists():
                shutil.copy2(src, cfg.publisher_dir / name)

        # Sync first installer to share root.
        src_first_install = self.repo_root / "FIRST_INSTALL.bat"
        if src_first_install.exists():
            shutil.copy2(src_first_install, cfg.first_install_file)
            self.logger(f"已同步 FIRST_INSTALL.bat: {cfg.first_install_file}")

    def get_online_version(self, share_root: Path) -> str:
        metadata_file = share_root / "metadata" / "version.json"
        if not metadata_file.exists():
            return "(未发布)"
        try:
            data = json.loads(metadata_file.read_text(encoding="utf-8-sig"))
            return str(data.get("version", "(未知)"))
        except Exception:
            return "(读取失败)"

    def publish(self, cfg: PublishConfig) -> None:
        if not re.match(r"^\d+\.\d+\.\d+$", cfg.version):
            raise RuntimeError("版本号必须为 x.y.z，例如 1.2.3")

        self.logger("开始发布流程")
        # 1) git pull origin main
        self._run(["git", "pull", "origin", "main"])
        # 2) update source __version__
        self._update_source_version(cfg.version)
        # 3) build
        self._build()
        # 4) generate version.json
        payload = self._write_local_version_json(cfg.version)
        # 5) sync release package
        self._sync_release_payload(cfg, payload)
        # 6) update metadata/version.json
        # 7) sync FIRST_INSTALL.bat and publisher docs
        self._sync_metadata_and_tools(cfg, payload)
        self.logger("发布完成")


class PublisherGUI:
    def __init__(self, root: tk.Tk, repo_root: Path):
        self.root = root
        self.root.title("AI-parse Publisher")
        self.root.geometry("900x680")

        self.repo_root = repo_root
        self.engine = PublisherEngine(repo_root=repo_root, logger=self.log)

        self.share_root_var = tk.StringVar(value=str(DEFAULT_SHARE_ROOT))
        self.online_version_var = tk.StringVar(value="-")
        self.new_version_var = tk.StringVar(value="")

        self._build_ui()
        self.refresh_online_version()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        config = ttk.LabelFrame(frame, text="发布配置", padding=10)
        config.pack(fill=tk.X)

        ttk.Label(config, text="共享盘根目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(config, textvariable=self.share_root_var, width=60).grid(row=0, column=1, sticky="we", padx=8)
        ttk.Button(config, text="刷新线上版本", command=self.refresh_online_version).grid(row=0, column=2, padx=4)

        ttk.Label(config, text="线上版本").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(config, textvariable=self.online_version_var).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))

        ttk.Label(config, text="新版本号").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(config, textvariable=self.new_version_var, width=20).grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))
        ttk.Button(config, text="执行发布", command=self.run_publish).grid(row=2, column=2, padx=4, pady=(8, 0))
        config.columnconfigure(1, weight=1)

        log_box = ttk.LabelFrame(frame, text="发布日志", padding=10)
        log_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(log_box, height=25, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def refresh_online_version(self) -> None:
        share_root = Path(self.share_root_var.get().strip())
        self.online_version_var.set(self.engine.get_online_version(share_root))

    def run_publish(self) -> None:
        version = self.new_version_var.get().strip()
        share_root = Path(self.share_root_var.get().strip())
        if not version:
            messagebox.showwarning("缺少版本号", "请输入要发布的新版本号，例如 1.0.3")
            return
        if not share_root:
            messagebox.showwarning("缺少路径", "请填写共享盘根目录")
            return
        if not messagebox.askyesno("确认发布", f"确认发布版本 {version} 到\n{share_root}\n\n并执行 git pull origin main ?"):
            return

        try:
            self.engine.publish(PublishConfig(version=version, share_root=share_root))
            self.refresh_online_version()
            messagebox.showinfo("发布完成", f"版本 {version} 已发布到共享盘")
        except Exception as exc:
            messagebox.showerror("发布失败", str(exc))


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    root = tk.Tk()
    PublisherGUI(root, repo_root=repo_root)
    root.mainloop()


if __name__ == "__main__":
    main()

