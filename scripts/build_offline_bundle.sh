#!/usr/bin/env bash
# Build release artifacts for an air-gapped Linux machine (run ONCE, with internet).
#   dist/beans-offline-<ver>.tar.gz   code + ui/dist + GeoIP DBs + pip wheelhouse (bare-metal install, Python 3.12)
#   dist/beans-docker-<ver>.tar.gz    `docker save` of the image (optional: pass --docker)
# On the target machine:
#   tar xzf beans-offline-<ver>.tar.gz && cd beans && ./install_offline.sh && make demo
#   or: docker load < beans-docker-<ver>.tar.gz && docker run --network none -p 8000:8000 beans:<ver>
set -euo pipefail
cd "$(dirname "$0")/.."
VER=${VER:-$(git describe --tags --always 2>/dev/null || echo dev)}
OUT=dist; STAGE=$(mktemp -d)/beans
mkdir -p "$OUT" "$STAGE"

echo "==> wheelhouse (pip download)"
python3 -m pip download -q -r requirements.txt -d "$STAGE/wheelhouse"

echo "==> sources"
git ls-files -z | grep -zvE '^(data/synth/|docs/archive/)' | xargs -0 cp --parents -t "$STAGE"
cp -r ui/dist "$STAGE/ui/"
cat > "$STAGE/install_offline.sh" <<'INNER'
#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links wheelhouse -r requirements.txt
echo "Installed. Run: make demo   (dashboard on http://127.0.0.1:8000)"
INNER
chmod +x "$STAGE/install_offline.sh"
tar -C "$(dirname "$STAGE")" -czf "$OUT/beans-offline-$VER.tar.gz" beans
echo "==> $OUT/beans-offline-$VER.tar.gz ($(du -h "$OUT/beans-offline-$VER.tar.gz" | cut -f1))"

if [[ "${1:-}" == "--docker" ]]; then
    docker build -t "beans:$VER" .
    docker save "beans:$VER" | gzip > "$OUT/beans-docker-$VER.tar.gz"
    echo "==> $OUT/beans-docker-$VER.tar.gz ($(du -h "$OUT/beans-docker-$VER.tar.gz" | cut -f1))"
fi
