#!/usr/bin/env python3
"""Apply migration 011: Add unique constraint for active sessions."""

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import from the project
sys.path.insert(0, str(Path(__file__).parent))

from src.integrations.supabase import supabase_client
from src.utils.logger import log


async def check_duplicates():
    """Check for duplicate active sessions before migration."""
    try:
        # Query for users with multiple active sessions
        response = (
            supabase_client.client.from_("conversation_sessions")
            .select("subcontractor_id")
            .eq("status", "active")
            .execute()
        )

        if not response.data:
            log.info("✅ No active sessions found")
            return []

        # Count sessions per user
        user_sessions = {}
        for session in response.data:
            user_id = session["subcontractor_id"]
            user_sessions[user_id] = user_sessions.get(user_id, 0) + 1

        # Find duplicates
        duplicates = {
            user_id: count for user_id, count in user_sessions.items() if count > 1
        }

        if duplicates:
            log.warning(f"⚠️ Found {len(duplicates)} users with duplicate active sessions")
            for user_id, count in duplicates.items():
                log.warning(f"   User {user_id}: {count} active sessions")
        else:
            log.info("✅ No duplicate active sessions found")

        return list(duplicates.keys())

    except Exception as e:
        log.error(f"Error checking duplicates: {e}")
        return []


async def cleanup_duplicates(user_ids):
    """Clean up duplicate sessions by ending all but the most recent."""
    if not user_ids:
        return

    log.info(f"🧹 Cleaning up duplicates for {len(user_ids)} users")

    for user_id in user_ids:
        try:
            # Get all active sessions for this user
            response = (
                supabase_client.client.from_("conversation_sessions")
                .select("*")
                .eq("subcontractor_id", user_id)
                .eq("status", "active")
                .order("last_message_at", desc=True)
                .execute()
            )

            if not response.data or len(response.data) <= 1:
                continue

            # Keep the first (most recent), end the rest
            sessions_to_end = [s["id"] for s in response.data[1:]]
            kept_session = response.data[0]["id"]

            log.info(f"   User {user_id}:")
            log.info(f"     Keeping session: {kept_session}")
            log.info(f"     Ending {len(sessions_to_end)} duplicate(s)")

            # End duplicate sessions
            from datetime import datetime

            for session_id in sessions_to_end:
                supabase_client.client.from_("conversation_sessions").update(
                    {
                        "status": "ended",
                        "ended_at": datetime.utcnow().isoformat(),
                        "ended_reason": "duplicate_cleanup",
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", session_id).execute()

            log.info(f"   ✅ Cleaned up user {user_id}")

        except Exception as e:
            log.error(f"   ❌ Error cleaning up user {user_id}: {e}")


async def apply_constraint():
    """Apply the unique constraint using raw SQL."""
    try:
        log.info("📝 Applying unique constraint...")

        # Read migration file
        migration_file = Path(__file__).parent / "migrations" / "011_add_unique_active_session_constraint.sql"

        if not migration_file.exists():
            log.error(f"Migration file not found: {migration_file}")
            return False

        with open(migration_file, "r") as f:
            sql = f.read()

        # Execute SQL using Supabase RPC
        # Note: Supabase client doesn't directly support raw SQL execution
        # The SQL must be executed via Supabase Dashboard or direct PostgreSQL connection

        log.warning("⚠️ Cannot execute raw SQL via Supabase REST API")
        log.info("Please apply the migration manually:")
        log.info(f"  1. Open Supabase Dashboard SQL Editor")
        log.info(f"  2. Copy contents from: {migration_file}")
        log.info(f"  3. Execute the SQL")
        log.info("")
        log.info("Or use PostgreSQL connection string:")
        log.info("  psql <connection_string> -f migrations/011_add_unique_active_session_constraint.sql")

        return False

    except Exception as e:
        log.error(f"Error applying constraint: {e}")
        return False


async def main():
    """Main migration script."""
    log.info("=" * 70)
    log.info("Migration 011: Add unique constraint for active sessions")
    log.info("=" * 70)

    # Step 1: Check for duplicates
    log.info("\n📊 Step 1: Checking for duplicate active sessions...")
    duplicate_users = await check_duplicates()

    # Step 2: Clean up duplicates if any
    if duplicate_users:
        log.info("\n🧹 Step 2: Cleaning up duplicate sessions...")
        await cleanup_duplicates(duplicate_users)

        # Re-check to confirm cleanup
        log.info("\n🔍 Verifying cleanup...")
        remaining_duplicates = await check_duplicates()
        if remaining_duplicates:
            log.error("❌ Some duplicates remain - please investigate")
            return False
    else:
        log.info("\n✅ Step 2: No cleanup needed")

    # Step 3: Apply constraint
    log.info("\n🔒 Step 3: Applying database constraint...")
    success = await apply_constraint()

    if success:
        log.info("\n✅ Migration completed successfully!")
    else:
        log.info("\n⚠️ Manual migration required (see instructions above)")

    log.info("=" * 70)
    return True


if __name__ == "__main__":
    asyncio.run(main())
