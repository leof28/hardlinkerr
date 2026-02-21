FROM python:3.9-slim

# Installation des outils système
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    jq \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie des fichiers
COPY bridge.py .
COPY hardlink_manager.sh .
COPY templates/ ./templates/

# Préparation
RUN mkdir -p /app/config && \
    chmod +x hardlink_manager.sh

EXPOSE 5000

CMD ["python", "bridge.py"]