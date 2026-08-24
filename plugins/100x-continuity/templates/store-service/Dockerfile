# The store service, as an image. Deployment is yours — this only says how to build and
# what the process needs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTINUITY_DB=/data/store.sqlite3 \
    CONTINUITY_TRANSPORT=http \
    PORT=8080

WORKDIR /srv

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY server.py ./

# Publications and the access table live here. Mount a volume, or the store is empty
# again on every restart.
VOLUME ["/data"]

# Object bytes do NOT live here. The service mints URLs against object storage it never
# reads through; give it credentials for that bucket in the environment.
EXPOSE 8080

# One process on purpose: the access table is SQLite. Scale by putting a real database
# behind it, not by running more copies against the same file.
CMD ["python", "server.py"]
