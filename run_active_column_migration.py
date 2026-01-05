"""Run migration to add active column to projects table."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.integrations.supabase import supabase_client
from src.utils.logger import log

def run_migration():
    """Execute migration to add active column."""

    print('🚀 Running Migration: Add active column to projects table\n')

    # Read migration file
    migration_file = Path(__file__).parent / 'migrations' / 'add_active_column_to_projects.sql'

    with open(migration_file, 'r') as f:
        sql_content = f.read()

    print(f'📄 Loaded migration file ({len(sql_content)} characters)\n')

    try:
        # Execute SQL via Supabase client
        # Using the raw SQL execution
        result = supabase_client.client.rpc('exec', {'query': sql_content}).execute()

        print('✅ Migration executed successfully!')
        print(f'Result: {result}\n')

        # Verify the column exists now
        test_query = supabase_client.client.table('projects').select('active').limit(1).execute()
        print('✅ Verification: active column is now accessible!')
        print(f'Test query result: {test_query.data}\n')

        return True

    except Exception as e:
        print(f'❌ Error executing via RPC: {e}\n')
        print('Trying alternative method using raw SQL execution...\n')

        try:
            # Alternative: Use PostgREST SQL execution if available
            from src.config import settings
            import requests

            # Try direct SQL endpoint
            url = f"{settings.supabase_url}/rest/v1/rpc/exec"

            headers = {
                'apikey': settings.supabase_service_role_key,
                'Authorization': f'Bearer {settings.supabase_service_role_key}',
                'Content-Type': 'application/json'
            }

            # Execute SQL directly
            response = requests.post(
                url,
                headers=headers,
                json={'query': sql_content},
                timeout=30
            )

            if response.status_code == 200:
                print('✅ Migration executed via direct API!')
                return True
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

        except Exception as e2:
            print(f'❌ Alternative method also failed: {e2}\n')
            print('='*60)
            print('⚠️  MANUAL MIGRATION REQUIRED')
            print('='*60)
            print('\n📋 Please follow these steps:')
            print('\n1. Open Supabase Dashboard: https://app.supabase.com/')
            print('2. Select your project: onchhcuflbabwsgppfgn')
            print('3. Go to SQL Editor')
            print('4. Create New Query')
            print('5. Copy contents of: migrations/add_active_column_to_projects.sql')
            print('6. Paste and click "Run"')
            print('\n' + '='*60)
            return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
