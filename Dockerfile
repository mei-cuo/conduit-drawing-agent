FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
ENV DRAWFLOW_HOME=/workspace
WORKDIR /workspace
EXPOSE 8000
CMD ["uvicorn", "drawflow.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
