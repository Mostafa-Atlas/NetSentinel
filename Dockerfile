FROM node:24-alpine AS frontend
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY frontend/ ./
RUN corepack pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /app/frontend/dist /app/static
ENV NETSENTINEL_STATIC_DIR=/app/static
ENV NETSENTINEL_DATABASE_URL=sqlite:////data/netsentinel.db
EXPOSE 8000
CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && uvicorn netsentinel.main:app --host 0.0.0.0 --port 8000 --workers 1"]
