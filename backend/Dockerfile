FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY data ./data
RUN pip install -e ".[era5]" && useradd --create-home wodiva && mkdir -p /app/var && chown wodiva /app/var
USER wodiva
RUN python -c "import duckdb; duckdb.connect().execute('INSTALL httpfs')"

EXPOSE 8000
CMD ["uvicorn", "app.core.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
