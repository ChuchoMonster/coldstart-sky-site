"""Tests for scripts/generate-sky.py with the kie.ai API mocked.

The script reads its API key at import time, so a fictional key is put in the
environment before loading it. Nothing here reaches the network."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]


def load_generate_sky():
    with mock.patch.dict(os.environ, {"KIE_AI_API_KEY": "fake-test-key"}):
        spec = importlib.util.spec_from_file_location("generate_sky", REPO / "scripts" / "generate-sky.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


gs = load_generate_sky()


def fake_http_response(payload):
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return resp


class LoadKeyTests(unittest.TestCase):
    def test_environment_wins(self):
        with mock.patch.dict(os.environ, {"KIE_AI_API_KEY": "from-env"}):
            self.assertEqual(gs.load_key(), "from-env")

    def test_reads_quoted_value_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text("OTHER=1\nKIE_AI_API_KEY = \"from-file\"\n")
            with mock.patch.object(gs, "ROOT", Path(tmp)), mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(gs.load_key(), "from-file")

    def test_missing_key_exits_with_hint(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(gs, "ROOT", Path(tmp)), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                gs.load_key()
        self.assertIn(".env.example", str(ctx.exception))


class ApiTests(unittest.TestCase):
    def test_posts_json_with_bearer_and_returns_data(self):
        with mock.patch.object(gs.urllib.request, "urlopen",
                               return_value=fake_http_response({"code": 200, "data": {"taskId": "t1"}})) as uo:
            self.assertEqual(gs.create_task("nano-banana-2", {"prompt": "p"}), "t1")
        req = uo.call_args.args[0]
        self.assertEqual(req.full_url, f"{gs.API}/createTask")
        self.assertEqual(req.get_header("Authorization"), "Bearer fake-test-key")
        self.assertEqual(json.loads(req.data), {"model": "nano-banana-2", "input": {"prompt": "p"}})

    def test_get_request_has_no_body(self):
        with mock.patch.object(gs.urllib.request, "urlopen",
                               return_value=fake_http_response({"code": 200, "data": {}})) as uo:
            gs.api("recordInfo?taskId=t1")
        self.assertIsNone(uo.call_args.args[0].data)

    def test_non_200_code_in_body_raises(self):
        with mock.patch.object(gs.urllib.request, "urlopen",
                               return_value=fake_http_response({"code": 402, "msg": "credits exhausted"})):
            with self.assertRaisesRegex(RuntimeError, "credits exhausted"):
                gs.api("createTask", {})


class PollTests(unittest.TestCase):
    def poll(self, states, timeout=100):
        responses = [{"state": s, "resultJson": json.dumps({"resultUrls": ["https://x.example/r.png"]}),
                      "failCode": "E1", "failMsg": "nsfw"} for s in states]
        with mock.patch.object(gs, "api", side_effect=responses) as api, \
             mock.patch.object(gs.time, "sleep") as sleep:
            return gs.poll("t1", "band image", 3, timeout), api, sleep

    def test_returns_first_result_url_after_waiting(self):
        url, api, sleep = self.poll(["waiting", "generating", "success"])
        self.assertEqual(url, "https://x.example/r.png")
        self.assertEqual(api.call_count, 3)
        sleep.assert_called_with(3)

    def test_failure_raises_with_reason(self):
        with self.assertRaisesRegex(RuntimeError, "band image failed: E1 nsfw"):
            self.poll(["fail"])

    def test_times_out(self):
        clock = iter([0, 0, 5, 11])
        with mock.patch.object(gs.time, "time", side_effect=lambda: next(clock)), \
             mock.patch.object(gs, "api", return_value={"state": "waiting"}), \
             mock.patch.object(gs.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "timed out after 10s"):
                gs.poll("t1", "band image", 3, 10)


class MainTests(unittest.TestCase):
    """main() over a fictional two-band manifest in a temporary project root."""

    MANIFEST = {
        "defaults": {"duration": 10, "resolution": "1080p", "aspect_ratio": "16:9", "image_size": "16:9"},
        "bands": [
            {"id": "test-a", "image_prompt": "img a", "video_prompt": "vid a"},
            {"id": "test-b", "image_prompt": "img b", "video_prompt": "vid b"},
        ],
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "sky-manifest.json").write_text(json.dumps(self.MANIFEST))
        self.raw = self.root / "assets-src" / "raw"
        self.raw.mkdir(parents=True)

    def run_main(self, video_states):
        """video_states maps band id -> final state reported for its video."""
        tasks, downloads = [], []

        def fake_create(model, input_obj):
            tasks.append((model, input_obj))
            return f"task-{len(tasks)}"

        def fake_api(path):
            task = path.split("taskId=")[1]
            model, input_obj = tasks[int(task.split("-")[1]) - 1]
            band = next(b["id"] for b in self.MANIFEST["bands"]
                        if b["video_prompt"] == input_obj.get("prompt"))
            return {"state": video_states[band], "failCode": "E9", "failMsg": "fictional failure",
                    "resultJson": json.dumps({"resultUrls": [f"https://x.example/{band}.mp4"]})}

        def fake_poll(task_id, label, interval, timeout_s):
            return f"https://x.example/{task_id}.png"

        def fake_download(url, dest):
            downloads.append((url, dest.name))
            dest.write_text(url)

        with mock.patch.object(gs, "ROOT", self.root), mock.patch.object(gs, "RAW", self.raw), \
             mock.patch.object(gs, "create_task", side_effect=fake_create), \
             mock.patch.object(gs, "poll", side_effect=fake_poll), \
             mock.patch.object(gs, "api", side_effect=fake_api), \
             mock.patch.object(gs, "download", side_effect=fake_download), \
             mock.patch.object(gs.time, "sleep"), redirect_stdout(io.StringIO()) as out:
            gs.main()
        return tasks, downloads, out.getvalue()

    def test_skips_bands_whose_raw_video_exists(self):
        (self.raw / "test-a.mp4").write_text("already made")
        tasks, downloads, _ = self.run_main({"test-b": "success"})
        prompts = [t[1]["prompt"] for t in tasks]
        self.assertEqual(prompts, ["img b", "vid b"])
        self.assertIn(("https://x.example/test-b.mp4", "test-b.mp4"), downloads)
        self.assertEqual((self.raw / "test-a.mp4").read_text(), "already made")

    def test_all_images_before_videos_and_video_uses_its_own_image(self):
        tasks, _, _ = self.run_main({"test-a": "success", "test-b": "success"})
        self.assertEqual([m for m, _ in tasks], ["nano-banana-2", "nano-banana-2",
                                                 "bytedance/seedance-2", "bytedance/seedance-2"])
        self.assertEqual(tasks[0][1], {"prompt": "img a", "output_format": "png", "image_size": "16:9"})
        vid_a = tasks[2][1]
        self.assertEqual(vid_a["image_url"], "https://x.example/task-1.png")
        self.assertEqual((vid_a["duration"], vid_a["resolution"], vid_a["aspect_ratio"]), (10, "1080p", "16:9"))
        self.assertEqual(tasks[3][1]["image_url"], "https://x.example/task-2.png")

    def test_failed_band_is_reported_and_others_still_finish(self):
        _, downloads, out = self.run_main({"test-a": "fail", "test-b": "success"})
        self.assertIn("[test-a] FAILED: E9 fictional failure", out)
        self.assertTrue((self.raw / "test-b.mp4").exists())
        self.assertFalse((self.raw / "test-a.mp4").exists())

    def test_nothing_pending_makes_no_api_calls(self):
        for b in self.MANIFEST["bands"]:
            (self.raw / f"{b['id']}.mp4").write_text("done")
        tasks, _, out = self.run_main({})
        self.assertEqual(tasks, [])
        self.assertIn("All bands already generated", out)


if __name__ == "__main__":
    unittest.main()
