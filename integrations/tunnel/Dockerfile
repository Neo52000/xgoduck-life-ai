FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY integrations/tunnel/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY integrations/tunnel/gateway.py .
USER 65532:65532
CMD ["python", "gateway.py"]
