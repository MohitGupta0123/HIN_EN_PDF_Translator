FROM python:3.12-slim

# System deps for ocrmypdf + fonts + runtime
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ocrmypdf tesseract-ocr ghostscript qpdf pngquant unpaper \
    fonts-noto fonts-noto-cjk fonts-noto-unhinted fonts-noto-color-emoji \
    libglib2.0-0 libgl1 \
 && rm -rf /var/lib/apt/lists/*

# app code
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# streamlit port on Spaces is 7860 by convention
ENV PORT=7860
EXPOSE 7860

# Ensure output dirs exist
RUN mkdir -p output_pdfs temp

# Streamlit config
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]