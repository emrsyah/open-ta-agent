# Database Setup Guide - Supabase PostgreSQL

This guide walks you through setting up PostgreSQL database via Supabase for your Telkom Paper Research API.

---

## 📋 Prerequisites

- Supabase account (free tier available)
- Existing Drizzle ORM schema in your frontend

---

## 🚀 Quick Setup (5 minutes)

### Step 1: Create Supabase Project

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Click **"New Project"**
3. Choose your organization
4. Set project name: `telkom-paper-research`
5. Choose region: `Southeast Asia (Singapore)` (closest to Indonesia)
6. Click **"Create new project"**

Wait 1-2 minutes for the database to be ready.

---

### Step 2: Get Database Connection String

1. In your Supabase project, go to **Project Settings** (gear icon)
2. Click **Database** in the left sidebar
3. Scroll to **Connection string** section
4. Select **URI** tab
5. Copy the connection string:

```
postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxxxxxxxxxx.supabase.co:5432/postgres
```

---

### Step 3: Configure Backend

1. Copy the example environment file:

```bash
cd backend
cp .env.example .env
```

2. Edit `.env` and add your database URL:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://postgres:your-actual-password@db.xxxxxxxxxxxxxxxxxxxx.supabase.co:5432/postgres
```

**Important**: Replace `postgresql://` with `postgresql+asyncpg://` for async support.

---

### Step 4: Run Migrations

Install dependencies if you haven't:

```bash
pip install -r requirements.txt
```

Run the database migrations:

```bash
# Make sure you're in the backend directory
cd backend

# Run Alembic migrations
alembic upgrade head
```

This will create:
- ✅ `catalog` table with all columns matching your Drizzle schema
- ✅ `catalog_type` enum with all 33 catalog types
- ✅ Proper indexes for fast searching

---

## 🧪 Verify Database Connection

### Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Should return:
# {"status":"healthy","version":"1.0.0","timestamp":"..."}

# List all papers (from database)
curl "http://localhost:8000/papers/list?limit=5"
```

### Check in Supabase Dashboard

1. Go to **Table Editor**
2. You should see the `catalog` table
3. Click on it to view columns and data

---

## 📊 Database Schema

Your Drizzle schema has been converted to SQLAlchemy models:

| Drizzle (Frontend) | SQLAlchemy (Backend) |
|-------------------|---------------------|
| `pgTable("catalog")` | `class Catalog(Base)` |
| `serial()` | `Integer, primary_key=True, autoincrement=True` |
| `text()` | `Text` |
| `varchar({ length: 100 })` | `String(100)` |
| `smallint` | `SmallInteger` |
| `pgEnum("catalog_type", [...])` | `SQLEnum(CatalogType, name="catalog_type")` |
| `index()` | `Index(...)` |

### Enum Values (33 catalog types)

All your catalog types are preserved:

```python
class CatalogType(str, enum.Enum):
    ARTICLE_RESTRICTED = "Artikel - Restricted Use"
    BAHAN_AJAR = "Bahan Ajar"
    BUKU_CIRCULATION_BI = "Buku - Circulation (BI Corner)"
    BUKU_CIRCULATION_DIPINJAM = "Buku - Circulation (Dapat Dipinjam)"
    BUKU_ELEKTRONIK = "Buku - Elektronik (E-Book)"
    # ... and 28 more
    SKRIPSI = "skripsi"
```

---

## 🔌 Connection Methods

### Method 1: Full URL (Recommended)

```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxx.supabase.co:5432/postgres
```

### Method 2: Individual Parameters

```bash
DATABASE_HOST=db.xxx.supabase.co
DATABASE_PORT=5432
DATABASE_NAME=postgres
DATABASE_USER=postgres
DATABASE_PASSWORD=your-password
```

---

## 🔄 Sync with Your Drizzle Schema

If you update your Drizzle schema in the frontend:

1. **Update the SQLAlchemy model** in `app/db/models.py`
2. **Create a new migration**:

```bash
alembic revision --autogenerate -m "description of changes"
alembic upgrade head
```

3. **Update both schemas** to stay in sync

---

## 📚 API Endpoints (Database-Backed)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/papers/search` | GET | Search papers in database |
| `/papers/list` | GET | List all papers with pagination |
| `/papers/{id}` | GET | Get single paper by ID |
| `/chat/basic` | POST | AI chat using database papers |

### Example: Search Papers

```bash
curl "http://localhost:8000/papers/search?query=machine+learning&limit=5"
```

Response:
```json
{
  "results": [
    {
      "catalog": {
        "id": 1,
        "title": "Machine Learning in Telecommunications",
        "author": "Dr. Ahmad Rizky",
        "catalogType": "Jurnal Internasional - Reference",
        "publicationYear": 2023,
        ...
      },
      "relevance_score": 5.0
    }
  ],
  "total": 42,
  "query": "machine learning"
}
```

---

## 🛠️ Troubleshooting

### "Database not configured" error

```
ValueError: Database not configured. Set DATABASE_URL or all of: DATABASE_HOST, ...
```

**Solution**: Add `DATABASE_URL` to your `.env` file

### "Connection refused" error

```
Connection refused to db.xxx.supabase.co:5432
```

**Solution**: 
- Check your network/firewall
- Verify the connection string is correct
- Make sure you're using the right password

### Migration errors

```
alembic.util.exc.CommandError: Can't locate revision identified by 'xxx'
```

**Solution**:
```bash
# Reset migrations (WARNING: deletes data!)
alembic downgrade base
alembic upgrade head
```

### "Enum already exists" error

If you run migrations multiple times:

```bash
# Check current state
alembic current

# Skip if already at head
alembic stamp head
```

---

## 🔒 Security Best Practices

1. **Never commit `.env` file** - it's in `.gitignore` by default
2. **Use strong password** for Supabase database
3. **Enable Row Level Security (RLS)** in Supabase for sensitive data
4. **Rotate passwords** periodically

---

## 💰 Cost Estimation (Supabase)

| Tier | Price | Good For |
|------|-------|----------|
| **Free** | $0/mo | Development, <500MB data |
| **Pro** | $25/mo | Production, unlimited data |
| **Team** | $599/mo | Large scale applications |

For your Telkom paper catalog (~10K-100K papers), the **Free tier** should be sufficient for development and testing.

---

## 🎯 Next Steps

1. ✅ Import your existing Telkom paper data into the database
2. ✅ Implement vector search for semantic paper retrieval
3. ✅ Add conversation history table for chat sessions
4. ✅ Set up database backups in Supabase

---

## 📖 Resources

- [Supabase Docs](https://supabase.com/docs)
- [SQLAlchemy 2.0 Async Guide](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

---

**Need help?** Check the logs with `DEBUG=true` in your `.env` file for detailed error messages.
