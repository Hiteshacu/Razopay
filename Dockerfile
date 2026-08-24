# Digital Trust Shield — API container
#
# Layout note: the signing/verification engine lives at the repository root
# (utils.py, sign_poster.py, verify_poster.py, ...) and backend/app/core/
# trust_shield_adapter.py reaches up three levels to import it. So the image
# keeps that same shape: engine at /app, backend package at /app/backend.

FROM python:3.11-slim

# OpenCV-headless and numpy still need a couple of shared libraries that the
# slim image omits. libgomp1 provides the OpenMP runtime both use for threading.
#
# ffmpeg is deliberately NOT installed: it adds ~200 MB and a slow build, and
# the product API only accepts PNG/JPG/PDF. video_support.py degrades cleanly
# when ffmpeg is absent (it probes with shutil.which). Add it here if you later
# expose video signing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so code edits don't invalidate the pip layer.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r backend/requirements.txt

# Engine at the root, then the backend package.
COPY *.py ./
COPY backend/ backend/

# All runtime writes land on the mounted persistent disk at /data so the
# registry, audit trail and encrypted keys survive a redeploy.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DTS_DATA_DIR=/data \
    LOCAL_UPLOAD_DIR=/data/uploads \
    SECURE_KEYS_DIR=/data/secure_private_keys \
    USE_LOCAL_STORAGE=true

RUN mkdir -p /data/uploads /data/secure_private_keys

WORKDIR /app/backend
EXPOSE 8000

# Needs a shell so ${PORT} expands (Render injects the port to bind), but
# `exec` hands the process over to uvicorn so it receives SIGTERM directly
# and shuts down promptly on redeploy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
