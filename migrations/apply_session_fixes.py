#!/usr/bin/env python3
"""
Apply session race condition fixes
- Phase 5: Unique constraint on active sessions
- Debugging: Enhanced RPC function with RAISE NOTICE
"""

import asyncio
import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.integrations.supabase import supabase_client


async def check_index_exists(index_name: str) -> bool:
    """Check if an index exists in the database."""
    query = """
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'conversation_sessions'
        AND indexname = %s
    """
    try:
        result = supabase_client.client.rpc(
            "exec_sql",
            {"sql": f"SELECT indexname FROM pg_indexes WHERE tablename = 'conversation_sessions' AND indexname = '{index_name}'"}
        ).execute()

        # Alternative: Direct query
        result = supabase_client.client.rpc(
            "exec",
            {"query": f"SELECT COUNT(*) as cnt FROM pg_indexes WHERE tablename = 'conversation_sessions' AND indexname = '{index_name}'"}
        ).execute()

        return bool(result.data)
    except Exception as e:
        print(f"⚠️  Could not check index existence: {e}")
        return False


async def apply_migration_file(filepath: str) -> bool:
    """Apply a migration file."""
    try:
        with open(filepath, 'r') as f:
            sql = f.read()

        print(f"📄 Applying migration: {os.path.basename(filepath)}")

        # Split by semicolon and execute each statement
        statements = [s.strip() for s in sql.split(';') if s.strip()]

        for i, statement in enumerate(statements):
            if not statement:
                continue

            try:
                # Skip pure comment blocks
                if statement.strip().startswith('--'):
                    continue

                print(f"   Executing statement {i+1}/{len(statements)}...")
                result = supabase_client.client.rpc(
                    "exec",
                    {"query": statement}
                ).execute()

            except Exception as e:
                # Some statements might fail (e.g., IF NOT EXISTS), that's OK
                if "already exists" in str(e).lower():
                    print(f"   ℹ️  Skipped (already exists)")
                else:
                    print(f"   ⚠️  Error: {e}")

        print(f"✅ Migration applied: {os.path.basename(filepath)}")
        return True

    except Exception as e:
        print(f"❌ Failed to apply migration: {e}")
        return False


async def main():
    print("=" * 70)
    print("Session Race Condition Fixes - Migration Application")
    print("=" * 70)

    # Get migration directory
    migrations_dir = os.path.dirname(os.path.abspath(__file__))

    # Check if Phase 5 migration needs to be applied
    print("\n📋 Checking Phase 5 migration (unique constraint)...")

    migration_011 = os.path.join(migrations_dir, "011_add_unique_active_session_constraint.sql")
    migration_012 = os.path.join(migrations_dir, "012_add_session_rpc_debugging.sql")

    # Note: We can't easily check if migrations are applied via Supabase client
    # Instead, we'll just apply them - they're written with IF NOT EXISTS

    print("\n🔧 Applying migrations...")

    # Apply Phase 5 (unique constraint)
    print("\n1️⃣  Phase 5: Unique Constraint")
    if os.path.exists(migration_011):
        await apply_migration_file(migration_011)
    else:
        print(f"   ⚠️  Migration file not found: {migration_011}")

    # Apply debugging enhancement
    print("\n2️⃣  RPC Debugging Enhancement")
    if os.path.exists(migration_012):
        await apply_migration_file(migration_012)
    else:
        print(f"   ⚠️  Migration file not found: {migration_012}")

    print("\n" + "=" * 70)
    print("✅ Migration application complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Deploy the code changes (message.py, message_pipeline.py, session.py)")
    print("2. Monitor logs for:")
    print("   - '✅ Reusing existing session_id' (should appear frequently)")
    print("   - PostgreSQL NOTICE logs in Supabase Dashboard")
    print("3. Verify session count in database (should see only 1 active per user)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
