#!/usr/bin/env python
"""
Send push notification to a specific user.

Usage:
    python -m src.scripts.direct user_id "Title" "Body"
    python -m src.scripts.direct user_id "Title" "Body" --dry-run
"""
from __future__ import annotations

import argparse
import asyncio

from ..services.notifications import send_push_to_user


async def broadcast(user_id: int, title: str, body: str, dry_run: bool = False) -> tuple[int, int, int]:   
    if dry_run:
        print("\n[DRY RUN] Would send:")
        print(f"  Title: {title}")
        print(f"  Body: {body}")
        print(f"  To: user {user_id}")
        return user_id, 0, 0

    print(f"\nSending: {title}")
    print(f"Message: {body}\n")

    try:
        print(f"Sending to user {user_id}...", end=" ")
        await send_push_to_user(user_id, title, body)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")

    return 1, 1, 0


def main():
    parser = argparse.ArgumentParser(
        description="Broadcast push notification to one user"
    )
    parser.add_argument("user_id", type=int, help="User ID to send notification to")
    parser.add_argument("title", help="Notification title")
    parser.add_argument("body", help="Notification body")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending"
    )

    args = parser.parse_args()

    asyncio.run(
        broadcast(args.user_id, args.title, args.body, args.dry_run)
    )


if __name__ == "__main__":
    main()
