"""Render the mermaid sources to PNG via mermaid.ink (kroki.io fallback)."""

import base64
import json
import sys
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("```mermaid")[1].split("```")[0].strip()


def mermaid_ink(code: str) -> bytes:
    state = json.dumps({"code": code, "mermaid": {"theme": "default"}})
    encoded = base64.urlsafe_b64encode(state.encode()).decode()
    req = urllib.request.Request(
        f"https://mermaid.ink/img/{encoded}?type=png&bgColor=ffffff&width=1400",
        headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def kroki(code: str) -> bytes:
    payload = base64.urlsafe_b64encode(
        zlib.compress(code.encode(), 9)).decode()
    req = urllib.request.Request(
        f"https://kroki.io/mermaid/png/{payload}", headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def main() -> int:
    failed = False
    for md in sorted(HERE.glob("d*.md")):
        code = source(md)
        out = md.with_suffix(".png")
        try:
            png = mermaid_ink(code)
        except Exception as first:
            try:
                png = kroki(code)
            except Exception as second:
                print(f"{md.name}: FAILED ({first}; fallback: {second})")
                failed = True
                continue
        out.write_bytes(png)
        print(f"{out.name}: {len(png)} bytes")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
