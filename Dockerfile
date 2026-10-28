# Stage 1: Base image with Python
FROM python:3.11-slim

# Install system dependencies for Chromium/Puppeteer
# These are the libraries that were missing on Render's native environment
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Node.js
    curl \
    gnupg \
    # Chromium dependencies
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first (for Docker caching)
COPY requirements.txt package.json package-lock.json ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js dependencies (includes Puppeteer + Chrome download via postinstall)
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port (Render sets PORT env var automatically)
EXPOSE 8011

# Start the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
