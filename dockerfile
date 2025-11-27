FROM python:3.10-slim

# --- System deps required by Playwright browsers ---
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl unzip \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libgtk-3-0 libgbm1 libasound2 libxcomposite1 libxdamage1 libxrandr2 \
    libxfixes3 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# --- Install Playwright + Chromium ---
RUN pip install playwright && playwright install --with-deps chromium

# --- Install uv package manager ---
RUN pip install uv

# --- Copy app to container ---
WORKDIR /app
COPY . .

# --- Install project dependencies using uv ---
RUN uv sync --frozen

# HuggingFace Spaces exposes port 7860
EXPOSE 7860

# --- Run your FastAPI app ---
# uvicorn must be in pyproject dependencies
CMD ["uv", "run", "main.py"]
