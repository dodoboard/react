"""Download the models AdForge's workflows expect into a ComfyUI install (resumable), plus open-licensed fonts.

usage:
  python scripts/setup_models.py --comfy D:/ComfyUI_windows_portable/ComfyUI            # everything
  python scripts/setup_models.py --comfy ... --only flux,upscaler,kontext,infinitetalk    # by feature
  python scripts/setup_models.py --comfy ... --files clip_vision_h.safetensors            # what the doctor reported missing
  python scripts/setup_models.py --only fonts                                              # fonts only (no --comfy needed)
  python scripts/setup_models.py --comfy ... --dry-run                                     # show the plan
Entries marked "verify" in models.json point at paths that may move upstream — the doctor page tells you if the
file name your ComfyUI sees differs; edit models.json or the workflow accordingly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("models.json")
FEATURES = ["flux", "upscaler", "kontext", "wan-common", "wan-i2v", "infinitetalk", "s2v", "fonts"]


def load(manifest: Path = MANIFEST) -> list[dict]:
    return json.loads(manifest.read_text())


def target(entry: dict, comfy: Path | None, data_dir: Path) -> Path:
    if entry["folder"] == "@fonts":
        return data_dir / "fonts" / entry["file"]
    if comfy is None:
        raise SystemExit("--comfy <ComfyUI klasörü> gerekli (models/ dizinini içeren klasör)")
    base = comfy / "models" if (comfy / "models").exists() or comfy.name != "models" else comfy
    return base / entry["folder"] / entry["file"]


def select(entries: list[dict], only: list[str] | None, files: list[str] | None) -> list[dict]:
    out = entries
    if only:
        want = set(only) | ({"wan-common"} if {"wan-i2v", "infinitetalk", "s2v"} & set(only) else set())
        out = [e for e in out if e["feature"] in want]
    if files:
        out = [e for e in out if e["file"] in set(files)]
    return out


def existing_anywhere(entry: dict, comfy: Path | None) -> Path | None:
    """ComfyUI scans subfolders too: a model already sitting in e.g. models/unet or models/checkpoints/flux counts."""
    if comfy is None or entry["folder"] == "@fonts":
        return None
    base = comfy / "models" if (comfy / "models").exists() else comfy
    if not base.exists():
        return None
    return next(base.rglob(entry["file"]), None)


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_suffix(dst.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "adforge-setup", **({"Range": f"bytes={have}-"} if have else {})})
    if tok := os.environ.get("HF_TOKEN"):
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0) + have
        mode = "ab" if have and r.status == 206 else "wb"
        done = have if mode == "ab" else 0
        with open(part, mode) as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {dst.name}: {done / 1e9:.2f}/{total / 1e9:.2f} GB ({done * 100 // total}%)", end="", flush=True)
    print()
    part.replace(dst)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--comfy", type=Path, help="ComfyUI klasörü")
    ap.add_argument("--only", help="virgülle özellikler: " + ",".join(FEATURES))
    ap.add_argument("--files", nargs="*", help="yalnızca bu dosya adları")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--ollama-model", default="qwen3:14b")
    ap.add_argument("--skip-ollama", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    entries = select(load(), a.only.split(",") if a.only else None, a.files)
    if not entries:
        print("Eşleşen kayıt yok.")
        return 1
    needs_comfy = any(e["folder"] != "@fonts" for e in entries)
    comfy = a.comfy if needs_comfy else None
    total = sum(e["gb"] for e in entries)
    print(f"{len(entries)} dosya, ~{total:.1f} GB")
    for e in entries:
        dst = target(e, comfy, a.data)
        elsewhere = existing_anywhere(e, comfy)
        if elsewhere and not dst.exists():
            print(f"[VAR (başka klasörde)] {e['feature']:12} {elsewhere}")
            continue
        state = "VAR" if dst.exists() else "İNDİRİLECEK"
        print(f"[{state:11}] {e['feature']:12} {dst}" + ("  (yolu doğrulayın)" if e.get("verify") else ""))
        if a.dry_run or dst.exists():
            continue
        try:
            download(e["url"], dst)
        except Exception as ex:  # keep going; the doctor page will flag what's still missing
            print(f"  ! {e['file']}: {ex}")
    if not a.skip_ollama and not a.dry_run and not a.only and shutil.which("ollama"):
        print(f"ollama pull {a.ollama_model}")
        subprocess.run(["ollama", "pull", a.ollama_model], check=False)
    print("Bitti. Uygulamada 'Sistem Durumu' sayfasından doğrulayın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
