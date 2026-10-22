FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_DIR=/models
WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir /models && chown app /models

COPY requirements.txt .
RUN pip install -r requirements.txt

# The embedding model is part of the image, so the service works offline and starts without a download
USER app
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/models')"
ENV HF_HUB_OFFLINE=1

COPY --chown=app evaluator ./evaluator
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"
CMD ["uvicorn", "evaluator.main:app", "--host", "0.0.0.0", "--port", "8000"]
