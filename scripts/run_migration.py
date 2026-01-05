"""Run database migration for templates table."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.utils.logger import log


def run_migration():
    """Run the templates table migration."""
    migration_file = Path(__file__).parent.parent / "migrations" / "create_templates_table.sql"

    log.info("=" * 60)
    log.info("Running templates table migration")
    log.info("=" * 60)

    try:
        # Read migration SQL
        with open(migration_file, 'r') as f:
            sql = f.read()

        log.info(f"Read migration file: {migration_file}")

        # Try to use psycopg2 if database URL is available
        if settings.supabase_db_url:
            try:
                import psycopg2
                log.info("Connecting to database...")
                conn = psycopg2.connect(settings.supabase_db_url)
                cursor = conn.cursor()

                log.info("Executing migration...")
                cursor.execute(sql)
                conn.commit()

                cursor.close()
                conn.close()

                log.info("✅ Migration executed successfully!")
                return True

            except ImportError:
                log.warning("psycopg2 not installed. Install with: pip install psycopg2-binary")
            except Exception as e:
                log.error(f"❌ Error executing migration: {e}")
                log.info("\nFalling back to manual instructions...")

        # Fallback: log the SQL and instruct to run manually
        log.info("\nPlease run this SQL in your Supabase SQL Editor:")
        log.info("-" * 60)
        print(sql)
        log.info("-" * 60)

        log.info("\nOr run via psql if you have database URL:")
        log.info("psql <DATABASE_URL> -f migrations/create_templates_table.sql")

    except Exception as e:
        log.error(f"❌ Error reading migration file: {e}")
        return False

    return True


if __name__ == "__main__":
    run_migration()
