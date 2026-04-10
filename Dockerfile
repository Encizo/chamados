FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY run.py /app/run.py
COPY manage_admin.py /app/manage_admin.py
COPY .env.example /app/.env.example

RUN mkdir -p /app/data /app/credenciais

EXPOSE 5000

CMD ["python", "run.py"]
