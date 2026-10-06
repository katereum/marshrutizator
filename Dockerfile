FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Amvera по умолчанию ждёт HTTP на порту 80 (containerPort). $PORT уважает
# хосты, которые его задают (Render/SnapDeploy); иначе — 80.
EXPOSE 80
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-80}
