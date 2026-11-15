FROM node:24-bookworm-slim AS frontend
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM debian:bookworm-slim AS source
WORKDIR /src
COPY . .
RUN tar -czf /tfwatch-source.tar.gz --transform 's,^,tfwatch/,' AGENTS.md LICENSE README.md docs backend frontend deploy Dockerfile compose.yaml .github .dockerignore .env.example .gitignore

FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/opt/tfwatch/static
RUN groupadd --system tfwatch && useradd --system --gid tfwatch tfwatch \
    && install -d -o tfwatch -g tfwatch /data
WORKDIR /opt/tfwatch/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /src/dist /opt/tfwatch/static
COPY --from=source /tfwatch-source.tar.gz /opt/tfwatch/static/tfwatch-source.tar.gz
USER tfwatch
EXPOSE 8000
CMD ["uvicorn", "tfwatch.main:app", "--host", "0.0.0.0", "--port", "8000"]

