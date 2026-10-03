# Image for running tests the agent wrote. The harness starts it with no network,
# a read-only file system and resource limits; the network is used only to build it.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

RUN useradd --create-home guard
USER guard
WORKDIR /work
