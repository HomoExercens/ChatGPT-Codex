from __future__ import annotations

import os
from typing import Any

import httpx


def _env(*names: str) -> str | None:
    for n in names:
        v = str(os.environ.get(n) or "").strip()
        if v:
            return v
    return None


def _payload() -> list[dict[str, Any]]:
    return [
        {
            "name": "nl",
            "type": 1,
            "description": "NeuroLeague shortcuts",
            "options": [
                {"type": 1, "name": "top", "description": "Top clip today"},
                {"type": 1, "name": "challenge", "description": "Daily challenge link"},
                {
                    "type": 1,
                    "name": "weekly",
                    "description": "Weekly theme / tournament link",
                },
                {
                    "type": 1,
                    "name": "build",
                    "description": "Import a build code",
                    "options": [
                        {
                            "type": 3,
                            "name": "code",
                            "description": "Build code",
                            "required": True,
                        }
                    ],
                },
            ],
        }
    ]


def main() -> None:
    app_id = _env("NEUROLEAGUE_DISCORD_APPLICATION_ID", "DISCORD_APPLICATION_ID")
    token = _env("NEUROLEAGUE_DISCORD_BOT_TOKEN", "DISCORD_BOT_TOKEN")
    guild_id = _env("NEUROLEAGUE_DISCORD_GUILD_ID", "DISCORD_GUILD_ID")

    if not app_id or not token:
        raise SystemExit(
            "Missing DISCORD app config. Set:\n"
            "- NEUROLEAGUE_DISCORD_APPLICATION_ID (or DISCORD_APPLICATION_ID)\n"
            "- NEUROLEAGUE_DISCORD_BOT_TOKEN (or DISCORD_BOT_TOKEN)\n"
            "- (optional) NEUROLEAGUE_DISCORD_GUILD_ID (or DISCORD_GUILD_ID)\n"
        )

    if guild_id:
        url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands"
        scope = "guild"
    else:
        url = f"https://discord.com/api/v10/applications/{app_id}/commands"
        scope = "global"

    resp = httpx.put(
        url, json=_payload(), headers={"Authorization": f"Bot {token}"}, timeout=20.0
    )
    try:
        parsed = resp.json()
    except Exception:  # noqa: BLE001
        parsed = {"status_code": resp.status_code, "body": resp.text[:600]}

    if resp.status_code >= 400:
        raise SystemExit(f"Discord API error ({resp.status_code}): {parsed}")

    print(f"Registered commands ({scope}) OK: {parsed}")


if __name__ == "__main__":
    main()
