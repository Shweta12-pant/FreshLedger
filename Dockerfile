FROM python:3.12-slim-trixie AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --disable-pip-version-check -r requirements.txt

FROM dependencies AS test
COPY requirements-dev.txt pyproject.toml ./
RUN python -m pip install --disable-pip-version-check -r requirements-dev.txt
COPY inventory/ inventory/
COPY tests/ tests/
ENV RUFF_CACHE_DIR=/tmp/ruff-cache COVERAGE_FILE=/tmp/freshledger-coverage
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM dependencies AS runtime
RUN groupadd --gid 10001 ledger && useradd --uid 10001 --gid ledger --no-create-home ledger
COPY inventory/ inventory/
USER ledger
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "inventory.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
