"""Run database migrations v2 via Supabase REST API."""
import requests
from src.config import settings

def run_migrations():
    """Execute migrations via Supabase SQL endpoint."""

    print('🚀 Running Database Migrations v2...\n')

    # Read SQL file
    with open('database_migrations_v2.sql', 'r') as f:
        sql_content = f.read()

    print(f'📄 Loaded SQL file ({len(sql_content)} characters)')

    # Supabase REST API endpoint for SQL execution
    url = f"{settings.supabase_url}/rest/v1/rpc/exec_sql"

    headers = {
        'apikey': settings.supabase_service_role_key,
        'Authorization': f'Bearer {settings.supabase_service_role_key}',
        'Content-Type': 'application/json'
    }

    data = {
        'query': sql_content
    }

    print('⏳ Executing via Supabase REST API...\n')

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            print('✅ Migrations executed successfully!')
            print(f'Response: {response.text[:200]}...')
            return True
        else:
            print(f'❌ Error: HTTP {response.status_code}')
            print(f'Response: {response.text[:500]}')
            return False

    except Exception as e:
        print(f'❌ Exception: {e}')
        return False

if __name__ == '__main__':
    success = run_migrations()

    if not success:
        print('\n' + '='*60)
        print('⚠️  MANUAL MIGRATION REQUIRED')
        print('='*60)
        print('\n📋 Please follow these steps:')
        print('\n1. Open Supabase Dashboard: https://app.supabase.com/')
        print('2. Go to SQL Editor')
        print('3. Create New Query')
        print('4. Copy contents of: database_migrations_v2.sql')
        print('5. Paste and click "Run"')
        print('\n✅ Then run: python verify_migrations.py')
        print('='*60)
