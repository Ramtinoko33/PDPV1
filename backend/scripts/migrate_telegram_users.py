"""One-shot migration: assistencias_bot_users → telegram_internal_authorized_users.

Non-destructive & idempotent.

For each doc in assistencias_bot_users:
  - Upsert an entry in telegram_internal_authorized_users, populating
    `user_id`, ensuring `"assistencias"` is in allowed_flows.
  - Mark the source doc with {migrated: true, migrated_at: <ts>} but do NOT
    delete it.

For each doc in telegram_internal_authorized_users without `user_id`:
  - Try a case-insensitive name match against `users.name`.
  - Unique match → populate user_id and clear needs_migration.
  - Ambiguous → keep needs_migration=True and print to stderr for manual
    resolution.

Usage:
    python scripts/migrate_telegram_users.py --dry-run
    python scripts/migrate_telegram_users.py --apply
    python scripts/migrate_telegram_users.py --report
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv


async def _run(mode: str) -> int:
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    is_apply = mode == "apply"
    is_report = mode == "report"

    stats = {
        "seen_bot_users": 0,
        "upserted": 0,
        "populated_user_id": 0,
        "auto_matched_by_name": 0,
        "ambiguous_by_name": 0,
        "still_needs_migration": 0,
        "already_migrated": 0,
    }

    if not is_report:
        # Step 1: consume assistencias_bot_users
        async for src in db.assistencias_bot_users.find({}):
            stats["seen_bot_users"] += 1
            tid = src.get("telegram_user_id")
            uid = src.get("user_id")
            name = src.get("user_name") or f"Op {tid}"
            if src.get("migrated"):
                stats["already_migrated"] += 1
                continue
            if not tid or not uid:
                print(f"[SKIP] bot_users doc telegram_user_id={tid} user_id={uid} — insufficient", file=sys.stderr)
                continue
            if is_apply:
                now = datetime.now(timezone.utc).isoformat()
                existing = await db.telegram_internal_authorized_users.find_one(
                    {"telegram_user_id": tid}
                )
                flows = list((existing or {}).get("allowed_flows") or [])
                if "assistencias" not in flows:
                    flows.append("assistencias")
                await db.telegram_internal_authorized_users.update_one(
                    {"telegram_user_id": tid},
                    {
                        "$set": {
                            "user_id": uid,
                            "name": (existing or {}).get("name") or name,
                            "role": (existing or {}).get("role") or "AGENT",
                            "allowed_flows": flows,
                            "active": True,
                            "needs_migration": False,
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now, "telegram_user_id": tid},
                    },
                    upsert=True,
                )
                await db.assistencias_bot_users.update_one(
                    {"_id": src["_id"]},
                    {"$set": {"migrated": True, "migrated_at": now}},
                )
            stats["upserted"] += 1

    # Step 2: fill user_id via name match for legacy docs still missing it.
    q = {"$or": [{"user_id": None}, {"user_id": {"$exists": False}}]}
    async for doc in db.telegram_internal_authorized_users.find(q):
        name = (doc.get("name") or "").strip()
        if not name:
            stats["still_needs_migration"] += 1
            continue
        # Case-insensitive exact match
        matches = await db.users.find(
            {"name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(5)
        if len(matches) == 1:
            stats["auto_matched_by_name"] += 1
            if is_apply:
                await db.telegram_internal_authorized_users.update_one(
                    {"telegram_user_id": doc["telegram_user_id"]},
                    {"$set": {
                        "user_id": matches[0]["id"],
                        "needs_migration": False,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                stats["populated_user_id"] += 1
        elif len(matches) > 1:
            stats["ambiguous_by_name"] += 1
            print(f"[AMBIGUOUS] tg_id={doc['telegram_user_id']} name={name!r} — {len(matches)} candidates: "
                  f"{[m['id'] for m in matches]}",
                  file=sys.stderr)
            if is_apply:
                await db.telegram_internal_authorized_users.update_one(
                    {"telegram_user_id": doc["telegram_user_id"]},
                    {"$set": {"needs_migration": True}},
                )
            stats["still_needs_migration"] += 1
        else:
            stats["still_needs_migration"] += 1
            if is_apply:
                await db.telegram_internal_authorized_users.update_one(
                    {"telegram_user_id": doc["telegram_user_id"]},
                    {"$set": {"needs_migration": True}},
                )

    print("=== migration report ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not is_apply and not is_report:
        print("(dry-run — no writes)")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--report", action="store_true")
    args = p.parse_args()
    mode = "apply" if args.apply else "report" if args.report else "dry-run"
    sys.exit(asyncio.run(_run(mode)))


if __name__ == "__main__":
    main()
