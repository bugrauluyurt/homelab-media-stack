#!/usr/bin/env python3
"""Opt-in live model + session restart test. Uses existing auth, never connects Telegram."""
import asyncio
import json
from pathlib import Path
import tempfile

from gateway import Gateway, validate_config, validate_pairing


class Probe(Gateway):
    def __init__(self, config):
        super().__init__(config, check=True)

        self.finished = asyncio.Event()
        self.answer = None
        self.used_tools = False

    async def handle(self, event):
        await super().handle(event)

        if event.get("type") == "tool_execution_start":
            self.used_tools = True

        if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
            self.answer = event["message"]

        if event.get("type") == "agent_end":
            self.finished.set()


async def main():
    config = json.loads((Path.home()/".config/arr-agent/config.json").read_text())
    validate_config(config)
    validate_pairing(config)

    with tempfile.TemporaryDirectory(prefix="arr-agent-live-smoke-") as directory:
        first = Probe(config)
        try:
            await first.start(directory)

            await first.request("prompt", message="Integration test: reply with exactly GATEWAY_SMOKE_OK and nothing else. Do not use any tools.")
            await asyncio.wait_for(first.finished.wait(), timeout=180)

            text = "".join(x.get("text", "") for x in (first.answer or {}).get("content", []) if x.get("type") == "text").strip()
            if first.used_tools or text != "GATEWAY_SMOKE_OK":
                raise RuntimeError("Model smoke reply failed (content withheld)")

            before = await first.request("get_state")
            if not Path(before["sessionFile"]).is_file():
                raise RuntimeError("Session was not persisted")
        finally:
            await first.close()

        second = Probe(config)
        try:
            await second.start(directory)

            after = await second.request("get_state")
            if before["sessionId"] != after["sessionId"] or before["messageCount"] != after["messageCount"]:
                raise RuntimeError("Session did not restore after restart")

            if second.telegram not in ("disconnected", "unknown"):
                raise RuntimeError("Unexpected Telegram connection during isolated test")
        finally:
            await second.close()

    print("PASS: real model reply, session persistence, clean shutdown, restart/resume; no Telegram connection")


if __name__ == "__main__":
    asyncio.run(main())
