FROM python:3.13-slim

WORKDIR /app

# Install system packages required for fitz/pdfminer and tesseract OCR
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-rus \
    libfitz-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "scripts/run_pipeline.py"]
