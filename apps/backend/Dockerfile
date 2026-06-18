FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/backend ./apps/backend
COPY apps/frontend ./apps/frontend
WORKDIR /app/apps/backend
CMD ["python3", "app.py", "serve"]
