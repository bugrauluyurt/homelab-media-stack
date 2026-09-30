#!/usr/bin/env python3
"""Supervise Pi's public JSONL RPC interface; pi-telegram owns all Telegram I/O."""
import argparse
import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
import uuid

DIALOGS = {"confirm", "select", "input", "editor"}
REQUIRED_COMMANDS = {"telegram-connect", "telegram-status", "skill:stack-health", "skill:stack-logs"}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def atomic_json(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".gateway-", dir=path.parent)

    try:
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())

        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def classify_telegram(text):
    text = ANSI.sub("", text).lower()

    match = re.search(r"(?:^|\s)(connected|leader|follower)(?:\s+\+\d+)?$", text)
    if match:
        return match.group(1)

    if re.search(r"(?:^|\s)disconnected(?:\s+\+\d+)?$", text):
        return "disconnected"

    return "unknown"


def safe_state(data):
    model = data.get("model") or {}

    return {"sessionId": data.get("sessionId"), "sessionFile": data.get("sessionFile"),
            "model": model.get("id"), "provider": model.get("provider"),
            "contextWindow": model.get("contextWindow"), "thinkingLevel": data.get("thinkingLevel"),
            "busy": bool(data.get("isStreaming") or data.get("isCompacting")),
            "pendingMessages": data.get("pendingMessageCount", 0)}


def child_env(agent_dir):
    env = dict(os.environ)

    for key in list(env):
        if key.startswith("PI_SESSION_") or key in {"PI_MODEL", "PI_PROVIDER", "PI_CODING_AGENT"}:
            env.pop(key)

    env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    env["PI_SKIP_VERSION_CHECK"] = "1"

    return env


def pi_version(cli):
    for parent in Path(cli).parents:
        package = parent / "package.json"
        if package.is_file():
            data = json.loads(package.read_text())
            if data.get("name") == "@earendil-works/pi-coding-agent":
                return data["version"]

    raise ValueError("Cannot locate Pi package metadata")


def telegram_version(agent_dir):
    package = Path(agent_dir) / "npm/node_modules/@llblab/pi-telegram/package.json"
    return json.loads(package.read_text())["version"]


def validate_config(config):
    for key in ("cwd", "agentDir", "stateDir", "node", "piCli"):
        if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
            raise ValueError(f"{key} must be an absolute path")

    for key in ("cwd", "agentDir"):
        if not Path(config[key]).is_dir():
            raise ValueError(f"{key} does not exist")

    for key in ("node", "piCli"):
        if not Path(config[key]).is_file():
            raise ValueError(f"{key} does not exist")

    if not re.fullmatch(r"[a-z0-9]{1,32}", config.get("profile", "default")):
        raise ValueError("Invalid Telegram profile")

    expected = config.get("piVersion")
    if not expected or pi_version(config["piCli"]) != expected:
        raise ValueError("Pi version changed: run agent-install and gateway --check before restarting")

    if config.get("telegramVersion") != telegram_version(config["agentDir"]):
        raise ValueError("Telegram extension version changed: reinstall and check before restarting")


def validate_pairing(config):
    data = json.loads((Path(config["agentDir"]) / "telegram.json").read_text())
    profile = data.get("profiles", {}).get(config.get("profile", "default"))

    if not profile or not profile.get("botToken") or type(profile.get("allowedUserId")) is not int:
        raise ValueError("Pair Telegram in Pi first; gateway refuses unattended first-user pairing")

    if profile["allowedUserId"] <= 0:
        raise ValueError("Invalid paired Telegram user")


class Gateway:
    def __init__(self, config, check=False):
        self.config = config
        self.check = check

        self.process = None
        self.pending = {}
        self.reader_task = None
        self.stop_event = asyncio.Event()

        self.telegram = "disconnected"
        self.state = {}
        self.last_rpc = None
        self.failure = None
        self.status_file = Path(config["stateDir"]) / "status.json"

        self.dialog_count = 0
        self.extension_errors = 0
        self.check_directory = None

    async def send(self, command):
        self.process.stdin.write((json.dumps(command, ensure_ascii=False) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, kind, timeout=60, **params):
        request_id = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self.pending[request_id] = fut

        try:
            await self.send({"id": request_id, "type": kind, **params})
            result = await asyncio.wait_for(fut, timeout)

            if not result.get("success"):
                raise RuntimeError(f"Pi RPC {kind} failed (payload withheld)")

            self.last_rpc = time.time()
            return result.get("data", {})
        finally:
            self.pending.pop(request_id, None)

    async def handle(self, event):
        kind = event.get("type")

        if kind == "response":
            fut = self.pending.get(event.get("id"))
            if fut and not fut.done():
                fut.set_result(event)
        elif kind == "extension_ui_request":
            method = event.get("method")
            if method in DIALOGS:
                self.dialog_count += 1
                await self.send({"type": "extension_ui_response", "id": event["id"], "cancelled": True})
                if self.dialog_count == 1:
                    print("Unattended UI request declined; no approval granted", flush=True)
            elif method == "setStatus" and event.get("statusKey") == "telegram":
                self.telegram = classify_telegram(event.get("statusText", ""))
            # Never mirror notification text, prompts, thinking or tool payloads to journald.
        elif kind == "extension_error":
            self.extension_errors += 1
            print("Pi extension error; inspect Pi's private diagnostics", flush=True)
        elif kind == "agent_start":
            self.state["busy"] = True
        elif kind == "agent_settled":
            self.state["busy"] = False

    async def read_events(self):
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise RuntimeError("Pi RPC process exited")

                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue

                if isinstance(event, dict):
                    await self.handle(event)
        except Exception as exc:
            self.failure = type(exc).__name__

            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("Pi RPC stream closed"))

            self.stop_event.set()

    def publish(self, phase):
        if not self.check:
            atomic_json(self.status_file, {"phase": phase, "pid": os.getpid(),
                         "piPid": self.process.pid if self.process else None,
                         "updatedAt": time.time(), "lastRpcAt": self.last_rpc,
                         "telegram": self.telegram, "declinedDialogs": self.dialog_count,
                         "extensionErrors": self.extension_errors, **self.state})

    async def start(self, session_dir):
        command = [self.config["node"], self.config["piCli"], "--mode", "rpc", "--offline", "--approve",
                   "--session-dir", str(session_dir), "--continue"]

        self.process = await asyncio.create_subprocess_exec(
            *command, cwd=self.config["cwd"], env=child_env(self.config["agentDir"]),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=32 * 1024 * 1024,
            start_new_session=True)

        self.reader_task = asyncio.create_task(self.read_events())

        data = await self.request("get_state")
        self.state = safe_state(data)

        commands = await self.request("get_commands")
        names = {x.get("name") for x in commands.get("commands", [])}

        if not REQUIRED_COMMANDS <= names:
            raise RuntimeError("Required Telegram commands or homelab skills did not load")

        if not self.state["model"] or self.extension_errors:
            raise RuntimeError("Model or extensions failed startup validation")

        if self.check and self.telegram not in {"disconnected", "unknown"}:
            raise RuntimeError("Unexpected Telegram connection during isolated check")

        print("Pi RPC ready; model and required homelab/Telegram commands loaded", flush=True)

    async def serve(self):
        config = self.config

        if self.check:
            self.check_directory = tempfile.TemporaryDirectory(prefix="arr-agent-check-")
            await self.start(self.check_directory.name)
            print(json.dumps({"check": "passed", "telegramConnected": False,
                              "model": self.state["model"], "provider": self.state["provider"],
                              "contextWindow": self.state["contextWindow"]}), flush=True)
            return

        session_dir = Path(config["stateDir"]) / "sessions"
        session_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        await self.start(session_dir)
        self.publish("connecting")

        profile = config.get("profile", "default")
        last_connect = 0
        announced = None

        while not self.stop_event.is_set():
            if self.telegram == "disconnected" and time.monotonic() - last_connect >= 60:
                last_connect = time.monotonic()
                await self.request("prompt", timeout=120, message=f"/telegram-connect {profile}")

            if announced != self.telegram:
                print("Telegram state: " + self.telegram, flush=True)
                announced = self.telegram

            self.state = safe_state(await self.request("get_state", timeout=20))
            self.publish("running" if self.telegram not in {"disconnected", "unknown"} else "waiting-for-telegram")

            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                pass

        if self.failure:
            raise RuntimeError("Pi RPC stream failed")

    async def close(self):
        self.publish("stopping")

        if self.process and self.process.returncode is None:
            # SIGTERM invokes Pi's own session_shutdown and bridge ownership cleanup.
            self.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self.process.wait(), timeout=30)
            except asyncio.TimeoutError:
                os.killpg(self.process.pid, signal.SIGKILL)
                await self.process.wait()

        if self.reader_task:
            self.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader_task

        self.publish("stopped")

        if self.check_directory:
            self.check_directory.cleanup()


async def run(config, check):
    gateway = Gateway(config, check)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, gateway.stop_event.set)

    serving = asyncio.create_task(gateway.serve())
    stopping = asyncio.create_task(gateway.stop_event.wait())

    try:
        done, _ = await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
        if serving in done:
            await serving
        elif gateway.failure:
            raise RuntimeError("Pi RPC stream failed")
    finally:
        serving.cancel()
        stopping.cancel()
        await asyncio.gather(serving, stopping, return_exceptions=True)
        await gateway.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home()/".config/arr-agent/config.json")
    parser.add_argument("--check", action="store_true", help="Test real Pi RPC/skills without connecting Telegram or calling a model")
    parser.add_argument("--status", action="store_true", help="Read the private heartbeat; no secrets or conversation text")
    args = parser.parse_args()

    try:
        os.umask(0o077)
        config = json.loads(args.config.read_text())

        if args.status:
            data = json.loads((Path(config["stateDir"])/"status.json").read_text())
            data["stale"] = time.time() - data.get("updatedAt", 0) > 60
            print(json.dumps(data, indent=2))
            return 0 if not data["stale"] and data.get("phase") == "running" else 1

        validate_config(config)
        validate_pairing(config)

        state = Path(config["stateDir"])
        state.mkdir(mode=0o700, parents=True, exist_ok=True)

        with (state / "gateway.lock").open("a") as lock:
            if not args.check:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(run(config, args.check))

        return 0
    except Exception as exc:
        # Error values can include extension/auth secrets; never print them automatically.
        print(f"Gateway stopped: {type(exc).__name__}; check configuration, pairing, version and private Pi diagnostics", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
