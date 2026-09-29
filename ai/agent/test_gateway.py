#!/usr/bin/env python3
import asyncio
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from gateway import Gateway, atomic_json, child_env, classify_telegram, safe_state, validate_pairing, validate_config, pi_version

FAKE_PI = r'''
import json, sys
commands = ["telegram-connect", "telegram-status", "skill:stack-health", "skill:stack-logs"]
for line in sys.stdin.buffer:
    event = json.loads(line)
    kind = event["type"]
    data = {}
    if kind == "get_state":
        data = {"model": {"id": "test", "provider": "test"}, "isStreaming": False, "sessionId": "test-session"}
    elif kind == "get_commands":
        data = {"commands": [{"name": x} for x in commands]}
    elif kind == "prompt":
        print(json.dumps({"type":"extension_ui_request", "method":"confirm", "id":"takeover", "title":"Take over?"}), flush=True)
        answer = json.loads(next(sys.stdin.buffer))
        assert answer["cancelled"] is True and "value" not in answer
        print(json.dumps({"type":"extension_ui_request", "method":"setStatus", "statusKey":"telegram", "statusText":"telegram disconnected"}), flush=True)
    elif kind == "unicode":
        data = {"text": "a\u2028b\u2029c"}
    elif kind == "exit":
        sys.exit(1)
    elif kind == "hang":
        continue
    print(json.dumps({"id":event["id"], "type":"response", "success":True, "data":data}, ensure_ascii=False), flush=True)
'''


class PureTests(unittest.TestCase):
    def test_status_text(self):
        for text, expected in [("telegram disconnected", "disconnected"),
                               ("\x1b[32mtelegram leader\x1b[0m +2", "leader"),
                               ("homelab follower", "follower"),
                               ("my leader thread error", "unknown"),
                               ("telegram reconnecting", "unknown"),
                               ("error diagnostics connected", "connected")]:
            self.assertEqual(classify_telegram(text), expected)

    def test_redacted_state(self):
        result = safe_state({"model": {"id": "test", "apiKey": "secret"}, "messages": ["private"], "isCompacting": True})

        self.assertTrue(result["busy"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("private", json.dumps(result))

    def test_atomic_private_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"status.json"
            atomic_json(path, {"x": 1})
            atomic_json(path, {"x": 2})

            self.assertEqual(json.loads(path.read_text()), {"x": 2})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_parent_session_not_inherited(self):
        with patch.dict(os.environ, {"PI_SESSION_FILE": "parent.jsonl", "PI_SESSION_ID": "parent", "PI_MODEL": "parent", "PI_PROVIDER": "parent"}):
            env = child_env("/tmp/agent")

            self.assertNotIn("PI_SESSION_FILE", env)
            self.assertNotIn("PI_MODEL", env)
            self.assertEqual(env["PI_CODING_AGENT_DIR"], "/tmp/agent")

    def test_bundled_pi_version_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"package.json").write_text(json.dumps({"name": "@earendil-works/pi-coding-agent", "version": "test"}))

            self.assertEqual(pi_version(root/"dist/bundle/cli.js"), "test")

    def test_version_changes_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"cwd": tmp, "agentDir": tmp, "stateDir": tmp,
                      "node": sys.executable, "piCli": __file__,
                      "piVersion": "one", "telegramVersion": "one"}

            with patch("gateway.pi_version", return_value="one"), patch("gateway.telegram_version", return_value="one"):
                validate_config(config)

                with self.assertRaises(ValueError):
                    validate_config({**config, "piVersion": "two"})
                with self.assertRaises(ValueError):
                    validate_config({**config, "telegramVersion": "two"})

    def test_pairing_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"telegram.json"
            path.write_text(json.dumps({"profiles": {"default": {"botToken": "test"}}}))

            with self.assertRaises(ValueError):
                validate_pairing({"agentDir": tmp})

            path.write_text(json.dumps({"profiles": {"default": {"botToken": "test", "allowedUserId": 42}}}))
            validate_pairing({"agentDir": tmp})


class RPCTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)/"fake_pi.py"
        path.write_text(FAKE_PI)

        config = {"node": sys.executable, "piCli": str(path), "cwd": self.tmp.name,
                  "agentDir": self.tmp.name, "stateDir": self.tmp.name}

        self.gateway = Gateway(config)
        await self.gateway.start(self.tmp.name)

    async def asyncTearDown(self):
        await self.gateway.close()
        self.tmp.cleanup()

    async def test_real_subprocess_handshake(self):
        self.assertEqual(self.gateway.state["model"], "test")

        result = await self.gateway.request("unicode")
        self.assertEqual(result["text"], "a\u2028b\u2029c")

    async def test_takeover_declined(self):
        await self.gateway.request("prompt", message="/telegram-connect default")

        self.assertEqual(self.gateway.dialog_count, 1)
        self.assertEqual(self.gateway.telegram, "disconnected")

    async def test_timeout(self):
        with self.assertRaises(asyncio.TimeoutError):
            await self.gateway.request("hang", timeout=0.05)

        self.assertFalse(self.gateway.pending)

    async def test_child_exit_unblocks_requests(self):
        with self.assertRaises(RuntimeError):
            await self.gateway.request("exit", timeout=2)

        self.assertTrue(self.gateway.stop_event.is_set())

    async def test_dialog_shapes_and_logs_are_private(self):
        sent = []
        async def record(data):
            sent.append(data)
        self.gateway.send = record

        for method in ("confirm", "select", "input", "editor"):
            await self.gateway.handle({"type":"extension_ui_request", "method":method, "id":method, "message":"private"})

        self.assertEqual(len(sent), 4)
        self.assertTrue(all(x["cancelled"] for x in sent))

        await self.gateway.handle({"type":"extension_ui_request", "method":"notify", "message":"SECRET"})
        self.gateway.publish("running")
        self.assertNotIn("SECRET", self.gateway.status_file.read_text())


if __name__ == "__main__":
    unittest.main()
