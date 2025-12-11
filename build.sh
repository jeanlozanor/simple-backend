#!/bin/bash
set -e

# Actualizar pip
pip install --upgrade pip setuptools wheel

# Instalar dependencias Python
pip install -r requirements.txt

# Instalar dependencias del sistema para Playwright (solo en Render)
apt-get update && apt-get install -y \
    libgconf-2-4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgdk-pixbuf2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    fonts-liberation \
    libnss3 \
    libappindicator3-1 \
    libindicator7 \
    xdg-utils \
    wget \
    ca-certificates 2>/dev/null || true

# Instalar Chromium para Playwright
python -m playwright install chromium --with-deps

