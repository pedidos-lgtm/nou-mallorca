FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home nm && mkdir /data && chown nm:nm /data
COPY --chown=nm:nm app ./app
COPY --chown=nm:nm static ./static
COPY --chown=nm:nm migrations ./migrations
COPY --chown=nm:nm scripts ./scripts
USER nm
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
