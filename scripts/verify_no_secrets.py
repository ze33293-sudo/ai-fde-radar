"""Fail when generated public artifacts contain configured secret values."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


FEISHU_TOKEN = re.compile(
    rb"https://open\.(?:feishu\.cn|larksuite\.com)/open-apis/bot/v2/hook/[A-Za-z0-9_-]+"
)


def iter_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not any(
                part in {".git", ".venv", ".uv-cache"} for part in path.parts
            ):
                yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--env",
        action="append",
        default=["DEEPSEEK_API_KEY", "HORIZON_WEBHOOK_URL"],
        help="Environment variable whose value must not appear in artifacts",
    )
    args = parser.parse_args()

    secrets = [
        value.encode("utf-8")
        for name in args.env
        if (value := os.getenv(name)) and len(value) >= 8
    ]
    violations = []
    for path in iter_files(args.paths):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if FEISHU_TOKEN.search(content) or any(secret in content for secret in secrets):
            violations.append(path)

    if violations:
        for path in violations:
            print(f"secret-like value detected in public artifact: {path}")
        return 1
    print("public artifact secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
