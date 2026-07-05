FROM python:3.11-slim

# tesseract para OCR de imágenes (inglés + español)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# La biblioteca vive en un volumen: los Markdown sobreviven al contenedor
ENV LIBRARY_DIR=/data/library
VOLUME /data

CMD ["second-brain", "run"]
