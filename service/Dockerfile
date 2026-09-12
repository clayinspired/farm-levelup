# Build context is the REPO ROOT (see scripts/deploy-service.sh), so the container
# uses the same vm0047 package as the research pipeline instead of a second copy.
FROM python:3.12-slim

# rasterio's manylinux wheel bundles GDAL but still links libexpat at runtime,
# which python:*-slim does not ship.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      aiohttp==3.14.3 \
      "python-telegram-bot==22.8" \
      numpy==2.5.3 \
      rasterio==1.4.3

WORKDIR /app
COPY service/main.py .
COPY service/app/ ./app/
COPY src/vm0047/ ./vm0047/

ENV DB_PATH=/data/plots.db CACHE_PATH=/data/elig_cache.json PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "main.py"]
