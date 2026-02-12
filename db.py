from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String

# 1. Database URL for MySQL (Note the +aiomysql driver)
DATABASE_URL = "mysql+aiomysql://root:@127.0.0.1/Health_Guide"

# 2. Create the Async Engine
engine = create_async_engine(DATABASE_URL, echo=True)

# 3. Create a Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 4. Base class for your models
class Base(DeclarativeBase):
    pass

# 5. Dependency to get DB session in routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session