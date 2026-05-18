FROM python:3.11-slim

# git is needed to detect whether a repo has version control
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY repoaudit/ ./repoaudit/
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["repoaudit"]
