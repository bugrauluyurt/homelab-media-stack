import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import patch


repo = Path(__file__).resolve().parents[1]
config_dir = Path(tempfile.mkdtemp())

spec = importlib.util.spec_from_file_location("sync_youtube", repo / "scripts/sync-youtube.py")
sync = importlib.util.module_from_spec(spec)

with patch.dict(sys.modules, {"stack_env": types.SimpleNamespace(
        CONFIG=config_dir, ENV={}, REPO=repo, STATE=config_dir, require_service=lambda name: None,
        set_env=lambda key, value: None)}):
    spec.loader.exec_module(sync)

WORKING_CHANNEL_ID = "UC" + "a" * 22
FAILING_CHANNEL_ID = "UC" + "b" * 22

ATOM_FEED = b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry><yt:videoId>older</yt:videoId><title>Older upload</title><published>2026-09-01T10:00:00+00:00</published></entry>
  <entry><yt:videoId>newer</yt:videoId><title>Newer upload</title><published>2026-09-03T08:00:00-04:00</published></entry>
</feed>"""


def fake_urlopen(url, timeout):
    if FAILING_CHANNEL_ID[2:] in url:
        raise urllib.error.URLError("HTTP Error 404: Not Found")

    return io.BytesIO(ATOM_FEED)


class WriteFeedsTests(unittest.TestCase):
    def setUp(self):
        (config_dir / "glance").mkdir(exist_ok=True)
        (config_dir / "glance/youtube-tech.yml").write_text(
            f"- {WORKING_CHANNEL_ID} # Working\n- {FAILING_CHANNEL_ID} # Failing\n")

        sync.FEEDS.mkdir(exist_ok=True)
        previous_video = {"id": "kept", "title": "Kept upload", "channel_id": FAILING_CHANNEL_ID,
                          "channel": "Failing", "published": "2026-09-02T00:00:00Z"}
        (sync.FEEDS / "tech.json").write_text(json.dumps({"videos": [previous_video]}))

    def write_feeds(self, token=None):
        output = io.StringIO()
        with patch.object(sync.urllib.request, "urlopen", side_effect=fake_urlopen), \
                contextlib.redirect_stdout(output):
            sync.write_feeds(token)

        return output.getvalue(), json.loads((sync.FEEDS / "tech.json").read_text())["videos"]

    def test_rss_videos_sorted_newest_first_with_failed_channel_kept(self):
        output, videos = self.write_feeds()

        self.assertEqual([video["id"] for video in videos], ["newer", "kept", "older"])
        self.assertEqual(videos[0]["published"], "2026-09-03T12:00:00Z")
        self.assertIn("! Tech: kept the last videos of unreachable channels: Failing", output)

    def test_second_run_is_unchanged(self):
        self.write_feeds()
        output, _ = self.write_feeds()

        self.assertIn("= Tech: 3 videos", output)

    def test_api_uploads_skip_videos_without_publish_time(self):
        items = [{"snippet": {"title": "Public"}, "contentDetails": {"videoId": "public", "videoPublishedAt": "2026-09-04T00:00:00Z"}},
                 {"snippet": {"title": "Private video"}, "contentDetails": {"videoId": "private"}}]

        with patch.object(sync, "api", return_value={"items": items}) as api:
            videos = sync.api_uploads("token", WORKING_CHANNEL_ID, "Working")

        self.assertEqual([video["id"] for video in videos], ["public"])
        self.assertEqual(api.call_args.kwargs["playlistId"], "UULF" + WORKING_CHANNEL_ID[2:])


if __name__ == "__main__":
    unittest.main()
