#!/usr/bin/env python3
"""Generate sky loop videos via KIE.AI: Nano Banana 2 ref image -> Seedance 2 video.

Manifest-driven (scripts/sky-manifest.json) and idempotent: bands whose raw
video already exists in assets-src/raw/ are skipped. To regenerate one band,
delete its raw file, tweak its manifest prompts, and rerun.

Ref-image URLs are temporary, so each band's image->video flow completes in
one run. Image tasks are submitted/polled first (sequential, ~30-60s each),
then all video tasks are submitted together and polled as a batch (~3-5 min).
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets-src" / "raw"
API = "https://api.kie.ai/api/v1/playground"

RAW.mkdir(parents=True, exist_ok=True)


def load_key():
    if os.environ.get("KIE_AI_API_KEY"):
        return os.environ["KIE_AI_API_KEY"]
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("KIE_AI_API_KEY not set (export it or put it in .env; see .env.example)")
    for line in env.read_text().splitlines():
        if line.startswith("KIE_AI_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("KIE_AI_API_KEY not found in .env")


KEY = load_key()


def api(path, payload=None):
    url = f"{API}/{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
    if body.get("code") != 200:
        raise RuntimeError(f"KIE error on {path}: {body}")
    return body["data"]


def create_task(model, input_obj):
    return api("createTask", {"model": model, "input": input_obj})["taskId"]


def poll(task_id, label, interval, timeout_s):
    start = time.time()
    while time.time() - start < timeout_s:
        d = api(f"recordInfo?taskId={task_id}")
        state = d.get("state")
        if state == "success":
            return json.loads(d["resultJson"])["resultUrls"][0]  # resultJson is a JSON *string*
        if state == "fail":
            raise RuntimeError(f"{label} failed: {d.get('failCode')} {d.get('failMsg')}")
        time.sleep(interval)
    raise RuntimeError(f"{label} timed out after {timeout_s}s")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        dest.write_bytes(r.read())
    print(f"  saved {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")


def main():
    manifest = json.loads((ROOT / "scripts" / "sky-manifest.json").read_text())
    defaults = manifest["defaults"]
    pending = [b for b in manifest["bands"] if not (RAW / f"{b['id']}.mp4").exists()]
    if not pending:
        print("All bands already generated. Delete a raw file to regenerate.")
        return

    print(f"Generating {len(pending)} band(s): {', '.join(b['id'] for b in pending)}")

    # Stage 1: reference images (sequential — each is quick)
    for b in pending:
        print(f"[{b['id']}] image task...")
        tid = create_task("nano-banana-2", {
            "prompt": b["image_prompt"],
            "output_format": "png",
            "image_size": defaults["image_size"],
        })
        b["image_url"] = poll(tid, f"{b['id']} image", 3, 360)
        try:
            download(b["image_url"], RAW / f"{b['id']}-ref.png")
        except Exception as e:  # ref download is a nice-to-have; the URL itself is what Seedance needs
            print(f"  ref download skipped ({e})")

    # Stage 2: submit all videos, then poll the batch
    for b in pending:
        print(f"[{b['id']}] video task...")
        b["video_task"] = create_task("bytedance/seedance-2", {
            "prompt": b["video_prompt"],
            "image_url": b["image_url"],
            "duration": defaults["duration"],
            "resolution": defaults["resolution"],
            "aspect_ratio": defaults["aspect_ratio"],
        })

    remaining = {b["id"]: b for b in pending}
    start = time.time()
    while remaining and time.time() - start < 1800:
        time.sleep(15)
        for bid, b in list(remaining.items()):
            d = api(f"recordInfo?taskId={b['video_task']}")
            state = d.get("state")
            if state == "success":
                url = json.loads(d["resultJson"])["resultUrls"][0]
                download(url, RAW / f"{bid}.mp4")
                del remaining[bid]
            elif state == "fail":
                print(f"[{bid}] FAILED: {d.get('failCode')} {d.get('failMsg')}")
                del remaining[bid]
        if remaining:
            print(f"  ...waiting on {', '.join(remaining)} ({int(time.time() - start)}s)")

    if remaining:
        print(f"TIMED OUT waiting on: {', '.join(remaining)}")
        sys.exit(1)
    print("Done. Next: ./scripts/process-video.sh")


if __name__ == "__main__":
    main()
