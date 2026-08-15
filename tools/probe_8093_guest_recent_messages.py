from __future__ import annotations

import argparse
import json
import sys
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlparse


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read recent shared-guest QA messages without sending a model request.")
    parser.add_argument("--base-url", default="http://10.30.220.12:8093")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    parsed = urlparse(args.base_url)
    connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=30)
    connection.request("GET", "/api/qa/bootstrap", headers={"Accept": "application/json"})
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()

    conversation = payload.get("conversation") or {}
    messages = conversation.get("messages") or payload.get("messages") or []
    selected = []
    for message in messages[-max(1, args.limit) :]:
        selected.append(
            {
                "role": message.get("role"),
                "created_at": message.get("created_at"),
                "content": message.get("content"),
                "metadata": message.get("metadata"),
            }
        )
    print(
        json.dumps(
            {
                "schema": "bf.qa.guest-recent-messages-probe.v1",
                "http_status": response.status,
                "access_mode": payload.get("access_mode"),
                "conversation_id": conversation.get("id") or payload.get("conversation_id"),
                "messages": selected,
                "production_write_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
