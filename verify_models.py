import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base
import sys


async def verify_models():
    print("Verifying SQLAlchemy models...")
    try:
        # Use an in-memory SQLite database for verification
        # Note: SQLite doesn't support some MySQL specific things like Enums directly in the same way,
        # but for relationship/syntax verification it's usually enough to check if metadata can be bound.
        # Actually, let's just try to import and check metadata.

        print(f"Models found: {len(Base.metadata.tables)}")
        for table_name in Base.metadata.tables:
            print(f" - {table_name}")

        print("\nSuccess: All models imported and metadata collected successfully.")
    except Exception as e:
        print(f"\nError verifying models: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify_models())
