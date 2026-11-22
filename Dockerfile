FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY fakes ./fakes
COPY tools ./tools
RUN pip install --no-cache-dir .
