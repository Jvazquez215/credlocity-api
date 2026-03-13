FROM python:3.9-slim-bullseye

WORKDIR /app

# Install MongoDB + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc wget gnupg \
    && wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | apt-key add - \
    && echo "deb http://repo.mongodb.org/apt/debian bullseye/mongodb-org/7.0 main" > /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update \
    && apt-get install -y mongodb-org-server mongodb-org-tools \
    && mkdir -p /data/db \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p media uploads/chat /data/db

CMD ["bash", "start.sh"]
