# Deterministic router build: installs the pinned requirements and runs the default
# rules-only path, which replays cache/media_text.json and calls no API.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "code/main.py"]
