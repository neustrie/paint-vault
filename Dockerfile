FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" jinja2 python-multipart reportlab
WORKDIR /srv
COPY app/ /srv/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
