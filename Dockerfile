FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY iotpipe iotpipe
COPY sql sql
COPY schemas schemas
COPY governance governance
RUN useradd -r -u 10001 app && mkdir -p data && chown app data
USER app
CMD ["python", "-m", "iotpipe.bridge"]
