FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY pyproject.toml README.md ./
COPY cryptoops ./cryptoops
COPY dashboard ./dashboard
COPY config ./config
RUN pip install --no-cache-dir .
EXPOSE 8000 8501
CMD ["uvicorn", "cryptoops.api:app", "--host", "0.0.0.0", "--port", "8000"]
