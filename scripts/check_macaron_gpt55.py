#!/usr/bin/env python
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def _collect_stream_text(response) -> tuple[list[str], str]:
    event_types: list[str] = []
    text_parts: list[str] = []
    saw_delta = False
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        data = line.removeprefix("data: ").strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "")
        if event_type:
            event_types.append(event_type)
        delta = event.get("delta")
        if isinstance(delta, str):
            saw_delta = True
            text_parts.append(delta)
        elif not saw_delta and isinstance(event.get("text"), str):
            text_parts.append(event["text"])
    return event_types, "".join(text_parts)


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    api_key = os.getenv("MACARON_API_KEY")
    base_url = os.getenv("MACARON_BASE_URL", "https://pi-api.macaron.xin").rstrip("/")
    model = os.getenv("MACARON_MODEL", "gpt-5.5")
    if not api_key:
        print("Missing MACARON_API_KEY in .env or environment", file=sys.stderr)
        return 2

    payload = {
        "model": model,
        "stream": True,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
    }
    request = Request(
        f"{base_url}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            event_types, text = _collect_stream_text(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body[:1000]}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK model={model} endpoint={base_url}/responses")
    if event_types:
        print("events=" + ",".join(event_types[:8]))
    if text:
        print("text=" + text[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
