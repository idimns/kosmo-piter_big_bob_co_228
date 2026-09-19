# многостадийная сборка: сначала фронт, потом питон-рантайм который его раздаёт.
# итог - один контейнер, один процесс.

# --- стадия 1: сборка фронтенда ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- стадия 2: питон-рантайм ---
FROM python:3.12-slim
WORKDIR /app

# ставим зависимости отдельным слоем для кэша
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY data/ ./data/
COPY configs/ ./configs/
COPY results/ ./results/

# собранный фронт из стадии 1
COPY --from=frontend /fe/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "fuelcontour.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
