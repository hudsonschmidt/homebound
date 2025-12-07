#!/usr/bin/env python
"""
Broadcast push notification to all users with registered devices.

Usage:
    python -m src.scripts.broadcast "Title" "Body"
    python -m src.scripts.broadcast "Title" "Body" --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import sqlalchemy

from .. import database as db
from ..services.notifications import send_push_to_user


async def broadcast(title: str, body: str, dry_run: bool = False) -> tuple[int, int, int]:
    """
    Send push notification to all users with registered iOS devices.

    Returns: (total_users, successful, failed)
    """
    # Get all unique user IDs with iOS devices
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                "SELECT DISTINCT user_id FROM devices WHERE platform = 'ios'"
            )
        ).fetchall()

    user_ids = [row[0] for row in result]
    total = len(user_ids)

    if total == 0:
        print("No users with registered iOS devices found.")
        return 0, 0, 0

    print(f"Found {total} user(s) with registered devices.")

    if dry_run:
        print("\n[DRY RUN] Would send:")
        print(f"  Title: {title}")
        print(f"  Body: {body}")
        print(f"  To: {total} user(s)")
        return total, 0, 0

    print(f"\nSending: {title}")
    print(f"Message: {body}\n")

    successful = 0
    failed = 0

    for i, user_id in enumerate(user_ids, 1):
        try:
            print(f"[{i}/{total}] Sending to user {user_id}...", end=" ")
            await send_push_to_user(user_id, title, body)
            print("OK")
            successful += 1
        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    return total, successful, failed


def main():
    parser = argparse.ArgumentParser(
        description="Broadcast push notification to all users"
    )
    parser.add_argument("title", help="Notification title")
    parser.add_argument("body", help="Notification body")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending"
    )

    args = parser.parse_args()

    total, successful, failed = asyncio.run(
        broadcast(args.title, args.body, args.dry_run)
    )

    if not args.dry_run and total > 0:
        print(f"\nSummary:")
        print(f"  Total users: {total}")
        print(f"  Successful:  {successful}")
        print(f"  Failed:      {failed}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
