"""Check existing Supabase database schema."""
import asyncio
from supabase import create_client
from src.config import settings

def check_schema():
    """Check what tables exist in Supabase."""
    try:
        client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )

        # Query to get all tables in public schema
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """

        result = client.rpc('exec_sql', {'query': query}).execute()
        print("=== Existing Tables ===")
        print(result)

    except Exception as e:
        print(f"Error checking schema: {e}")
        print("\nLet me try a different approach - checking specific tables:")

        # Try to check specific tables
        tables_to_check = [
            'users', 'messages', 'subcontractors', 'projects',
            'action_logs', 'escalations', 'conversations'
        ]

        for table in tables_to_check:
            try:
                result = client.table(table).select("*").limit(1).execute()
                print(f"✓ Table '{table}' exists (found {len(result.data)} sample records)")

                # If messages table exists, show its structure
                if table == 'messages' and result.data:
                    print(f"  Sample record keys: {list(result.data[0].keys()) if result.data else 'No records'}")

                # If subcontractors table exists, show its structure
                if table == 'subcontractors' and result.data:
                    print(f"  Sample record keys: {list(result.data[0].keys()) if result.data else 'No records'}")

            except Exception as e:
                error_msg = str(e)
                if 'PGRST205' in error_msg or 'not find' in error_msg:
                    print(f"✗ Table '{table}' does not exist")
                else:
                    print(f"✗ Table '{table}' - Error: {e}")

        # Check storage buckets
        print("\n=== Storage Buckets ===")
        try:
            buckets = client.storage.list_buckets()
            for bucket in buckets:
                print(f"✓ Bucket: {bucket.name}")
        except Exception as e:
            print(f"Error listing buckets: {e}")

if __name__ == "__main__":
    check_schema()
