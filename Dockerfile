FROM python:3.13-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV EXIFTOOL_PATH=/usr/bin/exiftool
ENV FFMPEG_PATH=/usr/bin/ffmpeg

# Install system dependencies (including image processing libs for Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    exiftool \
    libjpeg62-turbo-dev \
    libfreetype6-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Optional: install git
ARG INSTALL_GIT=false
RUN if [ "$INSTALL_GIT" = "true" ]; then \
    apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*; \
    fi

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    /app/packages/markitdown[all] \
    /app/packages/markitdown-sample-plugin \
    -r requirements.txt

# Expose port
EXPOSE 8000

# Optional user (adjust as needed)
ARG USERID=nobody
ARG GROUPID=nogroup
USER $USERID:$GROUPID

# Run with Gunicorn in production
ENTRYPOINT ["gunicorn", "--workers=4", "--bind=0.0.0.0:8000", "webserver:app"]
