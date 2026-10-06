#!/usr/bin/env python3
"""Download FLUX.2 weights for a profile into ComfyUI's models/ folder.

    python scripts/download_models.py --comfy C:\\ComfyUI_windows_portable\\ComfyUI
    python scripts/download_models.py --comfy ~/ComfyUI --profile klein-9b   # gated: set HF_TOKEN

Standard library only, resumable (.part files), skips files that already exist.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from studio.flux2 import PROFILES  # noqa: E402


def download(url: str, dest: Path, token: str | None) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[skip] {dest} already exists")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "influencer-studio"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416:  # .part is already complete
            part.replace(dest)
            return
        if e.code in (401, 403):
            raise SystemExit(f"{dest.name}: access denied. Accept the license on Hugging Face and set HF_TOKEN.")
        raise SystemExit(f"{dest.name}: HTTP {e.code} for {url}")
    with resp:
        if have and resp.status != 206:  # server ignored Range: start over
            have = 0
        total = have + int(resp.headers.get("Content-Length") or 0)
        done, last = have, 0.0
        with open(part, "ab" if have else "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if time.monotonic() - last > 0.5:
                    last = time.monotonic()
                    pct = f"{done / total:6.1%}" if total else ""
                    print(f"\r  {dest.name}: {done / 2**30:5.2f} GB {pct}", end="", flush=True)
    part.replace(dest)
    print(f"\r[ok] {dest} ({done / 2**30:.2f} GB)        ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--comfy", required=True, type=Path, help="ComfyUI folder (the one containing models/)")
    parser.add_argument("--profile", default="klein-4b", choices=[*PROFILES, "all"])
    args = parser.parse_args()

    models = args.comfy.expanduser() / "models"
    if not models.is_dir():
        raise SystemExit(f"{models} not found. Point --comfy at the ComfyUI folder that contains models/.")
    token = os.environ.get("HF_TOKEN")
    profiles = PROFILES.values() if args.profile == "all" else [PROFILES[args.profile]]
    seen: set[str] = set()
    for profile in profiles:
        print(f"== {profile.label} ({profile.license})")
        for folder, url in profile.downloads:
            if url not in seen:
                seen.add(url)
                download(url, models / folder / url.rsplit("/", 1)[-1], token)


if __name__ == "__main__":
    main()
