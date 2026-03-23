FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive


RUN apt-get update && \
    apt-get install -y minizinc build-essential python3 && \
    rm -rf /var/lib/apt/lists/*
    
WORKDIR /app


COPY setup.py ./

COPY ugr/ ./ugr/
COPY backend/ ./backend/

RUN pip install --no-cache-dir -e .

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]