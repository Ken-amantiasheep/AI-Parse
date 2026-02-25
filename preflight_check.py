"""
Runtime preflight checks for shared deployment on Windows Server.
"""
import argparse
import json
import os
import sys
import urllib.request


def _load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_writable_dir(path: str, label: str):
    os.makedirs(path, exist_ok=True)
    test_file = os.path.join(path, ".write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
    print(f"[OK] {label} writable: {os.path.abspath(path)}")


def _check_gateway(config: dict):
    mode = str(config.get("mode", "direct")).lower()
    if mode != "gateway":
        print("[OK] mode=direct, gateway check skipped")
        return

    gateway_url = str(config.get("gateway_url", "http://127.0.0.1:8080")).rstrip("/")
    timeout_sec = int(config.get("timeout_sec", 180))
    health_url = f"{gateway_url}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=min(timeout_sec, 10)) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        print(f"[OK] Gateway reachable: {health_url}")
        print(f"[INFO] Gateway health response: {body}")
    except Exception as e:
        raise RuntimeError(f"Gateway check failed: {health_url} | {e}")


def main():
    parser = argparse.ArgumentParser(description="Preflight checks")
    parser.add_argument("--config", default="config/config.json", help="Config file path")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--log-dir", default="logs", help="Log directory")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        raise FileNotFoundError(f"Config file not found: {args.config}")

    config = _load_config(args.config)
    _check_writable_dir(args.output_dir, "Output directory")
    _check_writable_dir(args.log_dir, "Log directory")
    _check_gateway(config)
    print("[SUCCESS] Preflight checks passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc)
        try:
            print(f"[ERROR] {message}")
        except UnicodeEncodeError:
            safe = message.encode("ascii", "ignore").decode("ascii")
            print(f"[ERROR] {safe}")
        sys.exit(1)
