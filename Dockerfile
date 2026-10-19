FROM python:3.12-slim

# No .pyc files in the mounted source, logs unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so the layer is cached while only the code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Development server listening on every interface so the port can be published
CMD ["flask", "--app", "app", "run", "--debug", "--host", "0.0.0.0", "--port", "8080"]
