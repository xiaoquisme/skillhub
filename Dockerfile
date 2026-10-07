FROM python:3.11-slim

# Use Chinese mirrors for apt (safe for non-CN too — falls back to upstream if unreachable)
RUN sed -i s/deb.debian.org/mirrors.aliyun.com/g /etc/apt/sources.list.d/debian.sources

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy source code and install dependencies
COPY pyproject.toml README.md ./
COPY skillhub/ skillhub/
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com .

# Create data directories
RUN mkdir -p /data/skills /data/db

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser

# Expose port
EXPOSE 8000

# Environment variables
ENV SKILLHUB_DATA_DIR=/data/db
ENV SKILLHUB_SKILLS_DIR=/data/skills

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run the application
CMD ["uvicorn", "skillhub.main:app", "--host", "0.0.0.0", "--port", "8000"]
