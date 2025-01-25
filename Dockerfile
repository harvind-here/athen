# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build backend with minimal dependencies
FROM python:3.9-slim AS backend-builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install only required packages
COPY requirements.txt .
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    requests \
    pymongo \
    groq \
    beautifulsoup4 \
    google-api-python-client \
    google-auth-oauthlib \
    pydub \
    pytz

# Stage 3: Final lightweight image
FROM python:3.9-slim
WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary files from previous stages
COPY --from=backend-builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/
COPY --from=frontend-builder /app/frontend/build/ /app/frontend/build/

# Copy only necessary application files
COPY app.py .
COPY config/ ./config/
COPY database/ ./database/
COPY managers/ ./managers/
COPY services/ ./services/
COPY utils/ ./utils/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"] 