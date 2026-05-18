# ── Stage 1: build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build


# ── Stage 2: Python backend + serve built frontend ────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System deps for pypdf, scikit-learn, psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY agent.py .
COPY api/ ./api/
COPY DATA/ ./DATA/

# Copy built frontend into a static dir FastAPI will serve
COPY --from=frontend-build /app/frontend/dist ./static

# Environment variables — set defaults, Railway overrides at runtime
ENV GEMINI_API_KEY=""
ENV SUPABASE_URL=""
ENV SUPABASE_SERVICE_KEY=""
ENV LANGSMITH_API_KEY=""
ENV LANGSMITH_PROJECT="mir9ad"
ENV LANGSMITH_TRACING="false"
ENV PORT=8000

# Railway injects $PORT at runtime — app must read it
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
