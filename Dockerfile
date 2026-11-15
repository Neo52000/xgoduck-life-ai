FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --create-home --uid 10001 lifeai
COPY lifeai ./lifeai
RUN mkdir -p /data && chown -R lifeai:lifeai /data
USER lifeai
EXPOSE 8000
CMD ["uvicorn","lifeai.app:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips","127.0.0.1"]
