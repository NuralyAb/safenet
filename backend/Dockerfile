FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# ffmpeg: yt-dlp media handling / audio extraction
# tesseract (rus + kaz + eng): on-prem OCR for screenshots — works without any external API
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
        tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Run as a non-root user (container hardening — OWASP A05 / CIS).
RUN useradd --create-home --uid 10001 afm && chown -R afm:afm /app
USER afm

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
