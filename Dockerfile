# For MCP directories that check a server by running it in a container (e.g. Glama).
# iWork Studio is built for macOS: in Linux the server starts and every tool is listed,
# the .numbers and .key file tools work, and app-driven tools say a Mac is needed.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
RUN uv pip install --system --no-cache .
ENTRYPOINT ["iwork-studio-mcp"]
