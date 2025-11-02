FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.3.1 torchvision==0.18.1
    
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000
CMD ["bash", "-lc", "python -c 'print(\"image ready\")' && sleep infinity"]
