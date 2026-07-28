FROM python:3.11-slim

# tesseract-ocr — системная зависимость pytesseract (см. packages.txt для Streamlit Cloud)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# altair и python-dateutil используются в app.py, но отсутствуют в requirements.txt
RUN pip install --no-cache-dir -r requirements.txt altair python-dateutil

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
