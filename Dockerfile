# syntax=docker/dockerfile:1
# Playwright/Patchright base image already ships Chromium + all system deps.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PDX_OUT=/data/output \
    PDX_SITE=/data/site

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY pdx ./pdx
COPY perplexity_tech_scraper.py ./

RUN pip install --no-cache-dir -e . \
 && scrapling install || true

# در حالت توزیع‌شده (root) کروم باید --no-sandbox بگیرد
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

VOLUME ["/data"]
ENTRYPOINT ["python", "perplexity_tech_scraper.py"]
CMD ["--out", "/data/output", "--site", "/data/site"]
