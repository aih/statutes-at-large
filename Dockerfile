FROM python:3.12-slim

RUN pip install --no-cache-dir uv

# The venv lives outside /app so the compose bind mount (.:/app) cannot shadow it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .

EXPOSE 8001

CMD ["uv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", \
     "--port", "8001", "--proxy-headers", "--forwarded-allow-ips", "*"]
