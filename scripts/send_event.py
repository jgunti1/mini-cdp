"""Send one signed test event to the webhook.

Examples:
  python scripts/send_event.py --event app_open --device-id d_demo1
  python scripts/send_event.py --event login --device-id d_demo1 --user-id u_2b6447a3
  python scripts/send_event.py --url https://YOUR-APP/webhooks/app --event read_story \\
      --device-id d_demo1 --user-id u_2b6447a3 --story supreme-court-ruling-explained

The secret is read from the WEBHOOK_SECRET environment variable, or from a .env file.
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def read_secret():
    secret = os.environ.get("WEBHOOK_SECRET")
    if secret:
        return secret
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("WEBHOOK_SECRET is not set (environment variable or .env file).")


def main():
    parser = argparse.ArgumentParser(description="Send one signed app event.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/webhooks/app")
    parser.add_argument("--event", default="app_open", choices=["app_open", "read_story", "link_click", "login"])
    parser.add_argument("--device-id", default="d_demo1")
    parser.add_argument("--user-id", default=None, help="leave out for an anonymous event")
    parser.add_argument("--event-id", default=None, help="reuse an ID to test duplicates")
    parser.add_argument("--timestamp", default="2026-09-28T14:22:05Z", help="when the event happened")
    parser.add_argument("--story", default=None)
    args = parser.parse_args()

    payload = {
        "event_id": args.event_id or f"evt_{uuid.uuid4().hex[:8]}",
        "event": args.event,
        "user_id": args.user_id,
        "device_id": args.device_id,
        "timestamp": args.timestamp,
        "properties": {"story": args.story} if args.story else {},
    }
    body = json.dumps(payload).encode()

    # Sign '<current time>.<body>' with the shared secret.
    sent_at = str(int(time.time()))
    signature = "sha256=" + hmac.new(read_secret().encode(), sent_at.encode() + b"." + body, hashlib.sha256).hexdigest()

    request = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": sent_at,
            "X-Webhook-Signature": signature,
        },
    )
    print("sending:", json.dumps(payload))
    try:
        with urllib.request.urlopen(request) as response:
            print(response.status, response.read().decode())
    except urllib.error.HTTPError as error:
        print(error.code, error.read().decode())


if __name__ == "__main__":
    main()
