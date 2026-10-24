FROM node:24.11.0-alpine3.22 AS frontend
WORKDIR /front
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.12.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home newschops
COPY backend/ ./backend/
COPY --from=frontend /front/dist ./frontend/dist
COPY scripts/start.sh ./scripts/start.sh
USER newschops
EXPOSE 8080
CMD ["sh","scripts/start.sh"]
