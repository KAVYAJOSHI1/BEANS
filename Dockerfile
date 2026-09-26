# BEANS: offline image. Build once with internet; run with `--network none`.
FROM python:3.12-slim

# WeasyPrint (PDF evidence packs) needs Pango/HarfBuzz + a font; LightGBM needs OpenMP (libgomp1); openssl = RFC 3161 TSA
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core libgomp1 openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY beans beans
COPY ui/dist ui/dist
COPY data/geoip data/geoip
COPY data/intel data/intel
COPY models models
COPY scripts/docker_entrypoint.sh /usr/local/bin/beans-entrypoint

ENV PYTHONUNBUFFERED=1 N_TX=2000
EXPOSE 8000
ENTRYPOINT ["beans-entrypoint"]
