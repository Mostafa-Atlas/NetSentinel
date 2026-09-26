FROM node:24-alpine AS frontend
WORKDIR /app/frontend
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.lock && pip install --no-cache-dir --no-deps ./backend
COPY --from=frontend /app/frontend/dist /app/static
ENV NETSENTINEL_STATIC_DIR=/app/static
ENV NETSENTINEL_DATABASE_URL=sqlite:////data/netsentinel.db
EXPOSE 8000
CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && uvicorn netsentinel.main:app --host 0.0.0.0 --port 8000 --workers 1"]
