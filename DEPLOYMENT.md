# 🚀 OpenTA Deployment Guide - Render.com

Complete guide for deploying OpenTA Backend to Render.com using the provided Docker and CI/CD setup.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (Blueprint Method)](#quick-start-blueprint-method)
3. [GitHub Secrets Configuration](#github-secrets-configuration)
4. [Manual Deployment](#manual-deployment)
5. [Post-Deployment Steps](#post-deployment-steps)
6. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
7. [Rollback Procedure](#rollback-procedure)

---

## Prerequisites

### Required Accounts

| Service | Account | Cost | Purpose |
|---------|---------|------|---------|
| **Render.com** | [Sign up](https://render.com) | Free tier available | Hosting platform |
| **GitHub** | [Sign up](https://github.com) | Free | CI/CD + Git |
| **OpenRouter** | [Get API key](https://openrouter.ai/settings/keys) | Pay-per-use | LLM access |
| **Voyage AI** | [Get API key](https://www.voyageai.com/) | Free tier | Embeddings |

### Required API Keys

1. **OpenRouter API Key** (`sk-or-v1-...`)
2. **Voyage AI API Key** (`pa-...`)

---

## Quick Start (Blueprint Method)

### Step 1: Push Code to GitHub

```bash
git init
git add .
git commit -m "Initial commit: OpenTA backend with Render deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/open-ta-telyu-dspy.git
git push -u origin main
```

### Step 2: Deploy on Render via Blueprint

1. **Go to [Render Dashboard](https://dashboard.render.com)**

2. **Click "New +" → "Blueprint"**

3. **Connect your GitHub repository**:
   - Select `open-ta-telyu-dspy`
   - Render will automatically detect `render.yaml`

4. **Review the blueprint configuration**:
   - Services: `openta-backend` (Docker web service)
   - Databases: `openta-db` (PostgreSQL 16)

5. **Click "Apply Blueprint"**

6. **Wait for deployment** (~3-5 minutes)

7. **Your API will be live at**:
   ```
   https://openta-backend.onrender.com
   ```

### Step 3: Set Environment Variables

After deployment, add sensitive environment variables in Render:

1. Go to your service: `openta-backend`
2. Click "Environment" tab
3. Add the following variables:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
VOYAGE_API_KEY=pa-your-voyage-key-here

# Optional (for Redis/conversation history)
REDIS_URL=redis://default:password@redis-xxx.cloud.redislabs.com:12345
```

### Step 4: Enable pgvector Extension

1. Go to `openta-db` in Render dashboard
2. Click "Query" (SQL editor)
3. Run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Step 5: Run Database Migrations

Option A - Via Render shell:

```bash
# In Render dashboard → openta-backend → Shell
alembic upgrade head
```

Option B - Via direct SSH (if available):

```bash
# Connect to your service and run
cd /app
alembic upgrade head
```

---

## GitHub Secrets Configuration

For GitHub Actions CI/CD to work, add these secrets in your GitHub repository:

### Go to: Settings → Secrets and variables → Actions

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | OpenRouter API key |
| `VOYAGE_API_KEY` | `pa-...` | Voyage AI API key |
| `RENDER_API_KEY` | `rnd_...` | From [Render settings](https://dashboard.render.com/settings) |
| `RENDER_SERVICE_URL` | `https://openta-backend.onrender.com` | Your deployed API URL |
| `RENDER_DATABASE_URL` | `postgresql+asyncpg://...` | From Render database dashboard |
| `RENDER_ADMIN_KEY` | `random-string` | For migration endpoint protection |

### Getting Render API Key

1. Go to [Render Settings](https://dashboard.render.com/settings)
2. Scroll to "API Keys"
3. Click "Create API Key"
4. Copy the key (format: `rnd_...`)

---

## Manual Deployment (Alternative)

If you prefer manual deployment instead of Blueprint:

### Step 1: Create Web Service

1. Go to Render Dashboard → "New +" → "Web Service"
2. Connect your GitHub repository
3. Configure:

```
Name: openta-backend
Environment: Docker
Region: Singapore (or closest to you)
Branch: main
Dockerfile Path: ./backend/Dockerfile
Plan: Free (or Starter/Standard)
```

### Step 2: Create Database

1. Go to Render Dashboard → "New +" → "PostgreSQL"
2. Configure:

```
Name: openta-db
Database: openta
User: openta_user
Region: Same as web service
Plan: Free
Version: PostgreSQL 16
```

### Step 3: Link Database to Web Service

1. Go to `openta-backend` service
2. Click "Environment" tab
3. Find `DATABASE_URL`
4. Click "Link" → Select `openta-db`
5. Render will auto-fill the connection string

### Step 4: Add Remaining Environment Variables

See [Step 3 above](#step-3-set-environment-variables)

---

## Post-Deployment Steps

### 1. Verify Deployment

```bash
# Health check
curl https://openta-backend.onrender.com/health

# Expected response:
# {"status":"healthy","version":"1.0.0","database":"connected"}
```

### 2. Test API Endpoints

```bash
# List papers
curl https://openta-backend.onrender.com/papers/list?limit=5

# Chat endpoint
curl -X POST https://openta-backend.onrender.com/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What papers discuss machine learning?",
    "meta_params": {"stream": false}
  }'
```

### 3. Set Custom Domain (Optional)

1. Go to `openta-backend` → "Settings"
2. Click "Add Custom Domain"
3. Enter your domain: `api.openta.telkomuniversity.ac.id`
4. Update DNS records as shown in Render

### 4. Configure CORS

Update `CORS_ORIGINS_STR` environment variable to include your frontend domain:

```bash
CORS_ORIGINS_STR=https://openta-frontend.onrender.com,https://your-custom-domain.com
```

---

## Monitoring & Troubleshooting

### View Logs

1. Go to `openta-backend` → "Logs" tab
2. Real-time logs stream
3. Filter by log level

### Common Issues

#### Issue: Database Connection Failed

**Solution:**
```bash
# Check DATABASE_URL format
# Should be: postgresql+asyncpg://user:password@host:port/database

# Test connection in Render dashboard → Database → Query
SELECT 1;
```

#### Issue: "Module not found" Error

**Solution:**
```bash
# Check requirements.txt includes all dependencies
# Rebuild service by pushing a new commit
git commit --allow-empty -m "Trigger rebuild"
git push
```

#### Issue: Health Check Failing

**Solution:**
```bash
# Check logs for startup errors
# Verify PORT environment variable is set (default 8000)
# Verify /health endpoint exists
curl https://openta-backend.onrender.com/health
```

#### Issue: pgvector Extension Not Found

**Solution:**
```sql
-- Run in Render dashboard → Database → Query
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### Performance Monitoring

Render provides built-in metrics:
- CPU usage
- Memory usage
- Response times
- Request count

Access via: `openta-backend` → "Metrics" tab

---

## Rollback Procedure

If something goes wrong after deployment:

### Option 1: Automatic Rollback (Render)

Render keeps previous deployments. To rollback:

1. Go to `openta-backend` → "Events" tab
2. Find previous successful deployment
3. Click "Rollback"
4. Confirm rollback

### Option 2: Git Revert

```bash
# Revert to previous commit
git revert HEAD

# Or hard reset (use with caution)
git reset --hard HEAD~1

# Push to trigger redeployment
git push origin main
```

### Option 3: Blue-Green Deployment

For zero-downtime deployments:

1. Deploy new version as `openta-backend-v2`
2. Test thoroughly
3. Switch traffic via DNS or load balancer
4. Keep old version as rollback option

---

## Cost Estimation

| Service | Plan | Monthly Cost |
|---------|------|--------------|
| **Web Service** | Free (750 hours/month) | $0 |
| **Web Service** | Starter ($7/month) | $7 |
| **Database** | Free (90 days, then $7/month) | $7 |
| **Redis** | External (Redis Cloud Free) | $0 |
| **LLM API Calls** | OpenRouter (usage-based) | ~$5-20/month |
| **Embeddings** | Voyage AI (usage-based) | ~$2-5/month |
| **Total (Free tier)** | | **$0** (first 90 days) |
| **Total (Paid)** | | **$20-40/month** |

---

## Security Checklist

- [ ] API keys stored in Render environment (not in code)
- [ ] `DEBUG=false` in production
- [ ] CORS restricted to frontend domain only
- [ ] Database connection uses SSL
- [ ] Custom domain configured with HTTPS
- [ ] Regular database backups enabled
- [ ] Rate limiting configured (future)

---

## Next Steps

1. **Deploy Frontend** - Deploy your frontend separately on Render/Vercel
2. **Set Up Monitoring** - Add Sentry for error tracking
3. **Configure Redis** - Enable conversation history
4. **Load Initial Data** - Import Telkom University paper catalog
5. **Performance Testing** - Run load tests before production launch

---

## Useful Links

- [Render Documentation](https://render.com/docs)
- [Blueprint Spec](https://render.com/docs/blueprint-spec)
- [GitHub Actions](https://docs.github.com/en/actions)
- [DSPy Documentation](https://dspy.ai)
- [OpenRouter](https://openrouter.ai)

---

## Support

If you encounter issues:

1. Check [Render Status Page](https://status.render.com)
2. Review Render logs in dashboard
3. Check GitHub Actions logs
4. Open an issue on GitHub

---

**🎉 Congratulations! Your OpenTA Backend is now deployed on Render.com!**
