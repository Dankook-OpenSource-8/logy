from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_PUSH_BATCH_SIZE = 100


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def build_expo_push_messages(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {},
        }
        for token in tokens
        if token and (
            token.startswith("ExponentPushToken[")
            or token.startswith("ExpoPushToken[")
        )
    ]


def send_expo_push_notifications(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    timeout_seconds: int = 10,
) -> set[str]:
    messages = build_expo_push_messages(tokens, title, body, data)
    invalid_tokens: set[str] = set()

    for batch in _chunked(messages, EXPO_PUSH_BATCH_SIZE):
        request = urllib.request.Request(
            EXPO_PUSH_URL,
            data=json.dumps(batch).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue

        results = payload.get("data")
        if not isinstance(results, list):
            continue

        for message, result in zip(batch, results):
            if not isinstance(result, dict) or result.get("status") != "error":
                continue
            details = result.get("details") if isinstance(result.get("details"), dict) else {}
            if details.get("error") == "DeviceNotRegistered":
                invalid_tokens.add(message["to"])

    return invalid_tokens
