FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m app
COPY --chown=app:app . .
RUN mkdir -p /data && chown app:app /data
USER app
ENV ANGOMALL_DB=/data/angomall.sqlite3
EXPOSE 8000
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8000"]
