FROM python:3.10-slim
# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    curl \
    wget \
    unzip \
    ca-certificates \
    tar \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask
WORKDIR /app
COPY panel.py /app/panel.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
