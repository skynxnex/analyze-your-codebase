# Pull Trivy binary from its official image (handles multi-arch automatically)
FROM aquasec/trivy:0.57.1 AS trivy-bin

FROM python:3.11-slim

# Install system deps: git (VCS detection)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy Trivy binary from official image
COPY --from=trivy-bin /usr/local/bin/trivy /usr/local/bin/trivy

WORKDIR /app
COPY pyproject.toml .
COPY repoaudit/ ./repoaudit/
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["repoaudit"]
