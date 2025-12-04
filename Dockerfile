FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 8080
CMD ["sh","-c","gunicorn -w 2 -k gthread --threads 8 -b 0.0.0.0:${PORT:-8080} web.app:app"]
