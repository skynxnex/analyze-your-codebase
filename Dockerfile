FROM python:3.11-slim AS base

# Install system deps: git (VCS detection) + curl (Trivy download)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Trivy (pinned binary)
RUN curl -sfL https://github.com/aquasecurity/trivy/releases/download/v0.58.1/trivy_0.58.1_Linux-64bit.tar.gz \
    | tar -xz -C /usr/local/bin trivy \
    && trivy --version

WORKDIR /app
COPY pyproject.toml .
COPY repoaudit/ ./repoaudit/
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["repoaudit"]
