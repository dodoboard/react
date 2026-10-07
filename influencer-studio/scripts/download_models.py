#!/usr/bin/env python3
"""Download model weights into ComfyUI's models/ folder.

    python scripts/download_models.py --comfy C:\\ComfyUI_windows_portable\\ComfyUI
    python scripts/download_models.py --comfy ~/ComfyUI --profile klein-9b         # gated: set HF_TOKEN
    python scripts/download_models.py --comfy ~/ComfyUI --profile none --video dance,smooth
    python scripts/download_models.py --comfy ~/ComfyUI --video all              # every Motion mode

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
from studio.video import MODE_FILES  # noqa: E402


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
    parser.add_argument("--profile", default="klein-4b", choices=[*PROFILES, "all", "none"],
                        help="FLUX.2 image profile")
    parser.add_argument("--video", default="", metavar="MODES",
                        help=f"comma-separated Motion modes: {', '.join(MODE_FILES)} or all")
    args = parser.parse_args()
    modes = list(MODE_FILES) if args.video == "all" else [m for m in args.video.split(",") if m]
    if unknown := [m for m in modes if m not in MODE_FILES]:
        parser.error(f"unknown video mode(s): {', '.join(unknown)}")

    models = args.comfy.expanduser() / "models"
    if not models.is_dir():
        raise SystemExit(f"{models} not found. Point --comfy at the ComfyUI folder that contains models/.")
    token = os.environ.get("HF_TOKEN")
    if args.profile == "all":
        profiles = list(PROFILES.values())
    else:
        profiles = [] if args.profile == "none" else [PROFILES[args.profile]]
    groups = [(f"{p.label} ({p.license})", [(folder, url, url.rsplit("/", 1)[-1]) for folder, url in p.downloads])
              for p in profiles]
    groups += [(f"Motion: {m}", [(f.folder, f.url, f.name) for f in MODE_FILES[m]]) for m in modes]
    if not groups:
        parser.error("nothing to download: pick a --profile and/or --video modes")
    seen: set[str] = set()
    for title, files in groups:
        print(f"== {title}")
        for folder, url, name in files:
            if url not in seen:
                seen.add(url)
                download(url, models / folder / name, token)


if __name__ == "__main__":
    main()
