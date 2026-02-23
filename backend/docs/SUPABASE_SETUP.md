# 🗄️ Supabase Database Setup Guide for OpenTA

Complete guide for setting up Supabase PostgreSQL database with pgvector extension for OpenTA Backend.

---

## 📋 Table of Contents

1. [Create Supabase Project](#create-supabase-project)
2. [Enable pgvector Extension](#enable-pgvector-extension)
3. [Run Database Migrations](#run-database-migrations)
4. [Load Initial Data](#load-initial-data)
5. [Verify Setup](#verify-setup)
6. [Connection Pooling](#connection-pooling)
7. [Backup Strategy](#backup-strategy)

---

## 1. Create Supabase Project

### Step 1: Sign Up / Login

1. Go to [https://supabase.com](https://supabase.com)
2. Click **Start your project** or **Sign In**

### Step 2: Create New Project

1. Click **New Project**
2. Configure:
   ```
   Name: OpenTA Database
   Database Password: [Generate strong password - SAVE THIS!]
   Region: Southeast Asia (Singapore) recommended
   Pricing Plan: Free (or Pro if needed)
   ```
3. Click **Create new project**
4. Wait for provisioning (~2 minutes)

### Step 3: Get Connection String

1. In your project dashboard, go to **Settings** → **Database**
2. Scroll to **Connection String** section
3. Select **URI** format
4. Copy the connection string
5. **Important**: Replace `postgresql://` with `postgresql+asyncpg://` for async support
   
   **Original format:**
   ```
   postgresql://postgres.[project-ref]:[password]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
   ```
   
   **Required format:**
   ```
   postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
   ```

---

## 2. Enable pgvector Extension

pgvector is required for vector similarity search on paper embeddings.

### Via SQL Editor (Recommended)

1. In Supabase dashboard, click **SQL Editor** in left sidebar
2. Run the following command:

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

**Expected output:**
```
 extname | extversion
---------+------------
 vector  | 0.5.0
```

### What is pgvector?

pgvector is a PostgreSQL extension that provides:
- **Vector data type**: Store embeddings (arrays of floats)
- **IVFFlat index**: Fast approximate nearest neighbor search
- **Cosine similarity**: Measure similarity between vectors
- **L2 distance**: Euclidean distance for vectors

This enables efficient semantic search on paper abstracts and titles.

---

## 3. Run Database Migrations

### Option A: Local Migration (Recommended)

Run migrations from your local machine:

```bash
# Navigate to backend directory
cd backend

# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres"

# Run Alembic migrations
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime] Migration 001_initial -> 002_add_abstract_embedding_hnsw
INFO  [alembic.runtime] Running upgrade 001_initial -> 002_add_abstract_embedding_hnsw
INFO  [alembic.runtime] Migration 002_add_abstract_embedding_hnsw -> 003_add_conversations_messages
INFO  [alembic.runtime] Running upgrade 002_add_abstract_embedding_hnsw -> 003_add_conversations_messages
```

### Option B: Via Supabase SQL Editor

Alternatively, you can manually run the migration SQL:

1. Go to **SQL Editor** in Supabase
2. Open migration files from `backend/alembic/versions/`
3. Copy and run each migration SQL in order

### Tables Created

After migrations, you should have these tables:

| Table | Purpose |
|-------|---------|
| `catalog` | Paper catalog (titles, abstracts, authors, etc.) |
| `conversations` | Chat conversation sessions |
| `messages` | Individual Q&A messages within conversations |

---

## 4. Load Initial Data

### Option A: Via Supabase Table Editor

1. Click **Table Editor** in Supabase
2. Select the `catalog` table
3. Click **Insert row** to add papers manually
4. Fill in fields:
   - `title`: Paper title
   - `author`: Author names (comma-separated)
   - `abstract`: Paper abstract
   - `publication_year`: Year published
   - `catalog_type`: Type (e.g., "Karya Ilmiah - Skripsi (S1) - Reference")
   - `subject`: Subject keywords
   - `catalog_number`: Library catalog number

### Option B: Bulk Import via CSV

1. Prepare CSV file with columns:
   ```csv
   title,author,abstract,publication_year,catalog_type,subject,catalog_number
   "Paper Title 1","Author One, Author Two","Abstract text...",2024,"Karya Ilmiah - Skripsi (S1) - Reference","Machine Learning","CAT001"
   ```

2. In Supabase dashboard:
   - Go to **Table Editor** → `catalog`
   - Click **Import Data**
   - Select CSV file
   - Map columns correctly
   - Click **Import**

### Option C: Via Python Script

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.models import Catalog

DATABASE_URL = "postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"

async def import_papers():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Sample paper
        paper = Catalog(
            title="Deep Learning in Computer Vision",
            author="John Doe, Jane Smith",
            abstract="This paper explores...",
            publication_year=2024,
            catalog_type="Karya Ilmiah - Skripsi (S1) - Reference",
            subject="Artificial Intelligence, Computer Vision",
            catalog_number="SK001",
            total_copies=1
        )
        
        session.add(paper)
        await session.commit()
        print("Paper imported successfully!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(import_papers())
```

---

## 5. Verify Setup

### Check Database Connection

```bash
cd backend

# Test database connection
python -c "
from app.database import get_engine, get_session_factory
import asyncio

async def test():
    engine = get_engine()
    if engine:
        print('✅ Database engine created')
        session_factory = get_session_factory()
        print('✅ Session factory created')
        await engine.dispose()
    else:
        print('❌ Database connection failed')

asyncio.run(test())
"
```

### Verify Tables Exist

In Supabase **SQL Editor**, run:

```sql
-- List all tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

**Expected output:**
```
table_name
-------------------------
alembic_version
catalog
conversations
messages
```

### Check pgvector Extension

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### Test API Connection

```bash
# Test health endpoint (after deployment)
curl https://openta-backend.onrender.com/health

# Should return:
# {"status":"healthy","version":"1.0.0","database":"connected"}
```

---

## 6. Connection Pooling

Supabase uses **PgBouncer** for connection pooling. This is important for performance.

### Direct Connection (for migrations/admin)

```
postgresql+asyncpg://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
```

### Pooled Connection (for application)

```
postgresql+asyncpg://postgres:[password]@db.[project-ref].supabase.co:6543/postgres
```

**Note**: The application uses `DATABASE_URL` which can be either format. Supabase handles routing automatically.

### Pool Settings in Application

Your backend is already configured with optimal pool settings (in `.env.production.example`):

```bash
DB_POOL_SIZE=5          # Number of connections to maintain
DB_MAX_OVERFLOW=10      # Additional connections under load
DB_POOL_TIMEOUT=30       # Seconds to wait for connection
DB_POOL_RECYCLE=1800    # Recycle connections after 30 minutes
```

---

## 7. Backup Strategy

### Automatic Backups (Supabase)

Supabase provides automatic backups:
- **Free tier**: 7 days retention
- **Pro tier**: 30 days retention

### Manual Backup

Via **SQL Editor**:
```sql
-- Export all catalog data
COPY catalog TO 'catalog_backup.csv' CSV HEADER;
```

### Restore from Backup

```sql
-- Restore catalog data
COPY catalog FROM 'catalog_backup.csv' CSV HEADER;
```

---

## 🔧 Troubleshooting Supabase

### Issue: Connection Refused

**Solution**: Check that IP is whitelisted (if using Supabase's network restrictions)

1. Go to **Settings** → **Database**
2. Check **Connection pooling** mode
3. Try **Direct connection** (port 5432) instead of pooled (port 6543)

### Issue: pgvector Not Found

**Solution**: Make sure you're running the SQL as the `postgres` user (default)

```sql
-- Check current user
SELECT current_user;

-- Switch to postgres if needed
SET ROLE postgres;

-- Then run
CREATE EXTENSION IF NOT EXISTS vector;
```

### Issue: Migration Fails

**Solution**: Check Alembic version in database

```sql
-- Check alembic version
SELECT * FROM alembic_version;

-- If needed, reset (WARNING: deletes data)
-- DROP TABLE alembic_version;
-- Then re-run migrations
```

---

## 📚 Useful Resources

- [Supabase Documentation](https://supabase.com/docs)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Alembic Documentation](https://alembic.sqlalchemy.org)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/core/async_helpers.html)

---

## ✅ Setup Checklist

- [ ] Supabase project created
- [ ] Database password saved securely
- [ ] pgvector extension enabled
- [ ] Database URL obtained and formatted correctly
- [ ] Alembic migrations run successfully
- [ ] Tables verified in database
- [ ] Connection tested from application
- [ ] Initial data loaded (optional)

---

**🎉 Your Supabase database is now ready for OpenTA!**
