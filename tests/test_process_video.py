"""Black-box test for scripts/process-video.sh.

The script locates the project from its own path, so it is copied into a
throwaway project root. Fake `ffmpeg`/`ffprobe` executables come first on
PATH: they log their arguments and write placeholder output files, so the
loop/encode logic runs without encoding any video."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FAKE_FFPROBE = """#!/usr/bin/env bash
echo "ffprobe $*" >> "$FAKE_LOG"
echo "${FAKE_DURATION:-10.000000}"
"""

# Writes the last argument (the output file). Size in KB comes from
# FAKE_KB_<ext>, so budget warnings can be exercised.
FAKE_FFMPEG = """#!/usr/bin/env bash
echo "ffmpeg $*" >> "$FAKE_LOG"
for out; do :; done
ext="${out##*.}"
var="FAKE_KB_${ext}"
kb="${!var:-4}"
head -c $((kb * 1024)) /dev/zero > "$out"
"""


def make_exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class ProcessVideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "project"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(REPO / "scripts" / "process-video.sh", self.root / "scripts")
        self.raw = self.root / "assets-src" / "raw"
        self.raw.mkdir(parents=True)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        make_exec(bin_dir / "ffprobe", FAKE_FFPROBE)
        make_exec(bin_dir / "ffmpeg", FAKE_FFMPEG)
        self.log = base / "tools.log"
        # A unique band id keeps the script's /tmp/<id>-loop.mp4 scratch file
        # from colliding with anything else.
        self.band = f"testband-{uuid.uuid4().hex[:8]}"
        self.addCleanup(lambda: Path(f"/tmp/{self.band}-loop.mp4").unlink(missing_ok=True))
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                    "HOME": str(base)}

    def run_script(self, **extra_env):
        return subprocess.run(["bash", str(self.root / "scripts" / "process-video.sh")],
                              env=dict(self.env, **extra_env), capture_output=True, text=True, timeout=60)

    def ffmpeg_calls(self):
        return [l for l in self.log.read_text().splitlines() if l.startswith("ffmpeg ")]

    def test_crossfade_trims_tail_onto_head(self):
        (self.raw / f"{self.band}.mp4").write_text("raw")
        r = self.run_script(FAKE_DURATION="10.04")
        self.assertEqual(r.returncode, 0, r.stderr)
        loop_cmd = self.ffmpeg_calls()[0]
        self.assertIn("trim=0:8.54", loop_cmd)
        self.assertIn("trim=8.54:10.04", loop_cmd)
        self.assertIn("xfade=transition=fade:duration=1.5:offset=0", loop_cmd)
        self.assertIn("(10.04s -> 8.54s seamless)", r.stdout)

    def test_writes_mp4_webm_and_poster_per_band_and_skips_reference_files(self):
        (self.raw / f"{self.band}.mp4").write_text("raw")
        (self.raw / f"{self.band}-ref.mp4").write_text("reference still, not a band")
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.root / "site" / "assets" / "sky"
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         sorted(f"{self.band}.{ext}" for ext in ("jpg", "mp4", "webm")))
        calls = self.ffmpeg_calls()
        self.assertEqual(len(calls), 4)  # loop, mp4, webm, poster for the one real band
        self.assertIn("-c:v libvpx-vp9", calls[2])
        self.assertIn("-ss 4", calls[3])
        self.assertNotIn("WARN", r.stdout)

    def test_warns_when_outputs_exceed_budget(self):
        (self.raw / f"{self.band}.mp4").write_text("raw")
        r = self.run_script(FAKE_KB_mp4="3000", FAKE_KB_webm="2000", FAKE_KB_jpg="120")
        self.assertEqual(r.returncode, 0, r.stderr)
        for msg in ("mp4 over 2.5MB budget", "webm over 1.6MB budget", "poster over 80KB budget"):
            self.assertIn(msg, r.stdout)


if __name__ == "__main__":
    unittest.main()
