FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Порт: ${PORT} задаёт хостинг (напр. SnapDeploy/Koyeb), иначе 7860 (Hugging Face Spaces).
EXPOSE 7860
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-7860}
