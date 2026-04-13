# ENV.md — Environment Variables & Local Setup

## .env.example (commit this to GitHub)

```bash
# ─── IBM WatsonX ───────────────────────────────────────────
WATSONX_API_KEY=your_ibm_cloud_api_key_here
WATSONX_PROJECT_ID=your_watsonx_project_id_here
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-13b-chat-v2

# ─── Reddit API ────────────────────────────────────────────
# Get at: https://www.reddit.com/prefs/apps → Create app → Script
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=DevCityPulse/1.0 by YourUsername

# ─── Database ──────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:password@localhost:5432/devcitypulse
REDIS_URL=redis://localhost:6379

# ─── Optional ──────────────────────────────────────────────
NEWS_API_KEY=

# ─── App Config ────────────────────────────────────────────
UPDATE_INTERVAL_SECONDS=30
SIMULATION_BATCH_SIZE=50
```

---

## .gitignore (must include)

```
.env
__pycache__/
*.pyc
.DS_Store
*.egg-info/
dist/
build/
.venv/
node_modules/
*.log
```

---

## Local Setup — Step by Step

```bash
# 1. Clone repo
git clone https://github.com/YOUR_USERNAME/devcity-pulse.git
cd devcity-pulse

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env file and fill in keys
cp .env.example .env
# Edit .env with your API keys

# 5. Start infrastructure (PostgreSQL + Redis)
docker compose up -d

# 6. Run backend
uvicorn backend.main:app --reload --port 8000

# 7. Open browser
# Dashboard: http://localhost:8000/dashboard.html
# API docs:  http://localhost:8000/docs
```

---

## Getting API Keys

### IBM WatsonX (required)
1. Go to https://dataplatform.cloud.ibm.com
2. Sign in with IBM SkillBuild Lab account
3. Create a new project
4. Go to project settings → copy Project ID
5. Go to IBM Cloud → Manage → Access (IAM) → API Keys → Create
6. Copy API key to `WATSONX_API_KEY`
7. Your URL is `https://us-south.ml.cloud.ibm.com` unless you're in a different region

### Reddit API (required)
1. Go to https://www.reddit.com/prefs/apps
2. Click "Create app" → choose "Script"
3. Name: DevCityPulse, Redirect: http://localhost:8080
4. Copy client_id (under app name) and client_secret
5. User agent format: `DevCityPulse/1.0 by YOUR_REDDIT_USERNAME`

### NewsAPI (optional)
1. Go to https://newsapi.org → Get API key (free tier: 100 req/day)
2. Used as fallback if RSS feeds fail

---

## IBM Cloud Deployment (Week 4)

```bash
# Install IBM Cloud CLI
curl -fsSL https://clis.cloud.ibm.com/install/linux | sh

# Login
ibmcloud login --sso

# Target resource group
ibmcloud target -g Default

# Deploy to Code Engine
ibmcloud ce project create --name devcity-pulse
ibmcloud ce project select --name devcity-pulse

ibmcloud ce application create \
  --name devcity-api \
  --image us.icr.io/devcity/api:latest \
  --env WATSONX_API_KEY=$WATSONX_API_KEY \
  --env WATSONX_PROJECT_ID=$WATSONX_PROJECT_ID \
  --env DATABASE_URL=$DATABASE_URL \
  --env REDIS_URL=$REDIS_URL \
  --port 8000 \
  --min-scale 1
```
