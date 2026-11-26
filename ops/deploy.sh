#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:?Usage: ops/deploy.sh freshledger:TAG}"
if [[ ! "$image" =~ ^freshledger:[a-zA-Z0-9._-]{1,120}$ ]]; then
  echo "Expected a local FreshLedger image tag such as freshledger:a1b2c3." >&2
  exit 2
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deploy_dir="${DEPLOY_DIR:-/srv/freshledger}"
if [[ ! -f "$deploy_dir/.env" ]]; then
  echo "Create $deploy_dir/.env from .env.example before deploying." >&2
  exit 2
fi
deploy_dir="$(cd "$deploy_dir" && pwd)"
mkdir -p "$deploy_dir/releases"
exec 9>"$deploy_dir/deploy.lock"
flock -w 60 9

project="${DEPLOY_PROJECT:-freshledger-release}"
release="$(mktemp -d "$deploy_dir/releases/${image#*:}.XXXXXXXX")"
previous="$(readlink "$deploy_dir/current" || true)"
started=$SECONDS

cp "$source_dir/compose.yaml" "$release/compose.yaml"
mkdir -p "$release/ops"
cp -R "$source_dir/ops/prometheus" "$source_dir/ops/grafana" "$release/ops/"
printf '%s\n' "$image" > "$release/image"

compose() {
  local selected="$1" target_image
  shift
  target_image="$(cat "$selected/image")" || return
  APP_IMAGE="$target_image" docker compose --project-name "$project" --project-directory "$selected" \
    --env-file "$deploy_dir/.env" -f "$selected/compose.yaml" "$@"
}

activate() {
  local selected="$1"
  compose "$selected" up -d --no-build --wait --wait-timeout 150 db &&
  compose "$selected" run --rm --no-deps init &&
  compose "$selected" up -d --no-build --no-deps --wait --wait-timeout 120 app &&
  compose "$selected" up -d --no-build --no-deps --wait --wait-timeout 120 worker prometheus grafana &&
  compose "$selected" exec -T app python - <<'PY_CHECKS'
import base64
import json
import os
import time
from urllib.request import Request, urlopen

checks = {
    "inventory API": "http://127.0.0.1:8000/api/dashboard",
    "Prometheus": "http://prometheus:9090/-/ready",
    "Grafana": "http://grafana:3000/api/health",
}
for name, url in checks.items():
    headers = {}
    if name == "inventory API" and os.getenv("APP_USERNAME"):
        credentials = (os.environ["APP_USERNAME"] + ":" + os.environ["APP_PASSWORD"]).encode()
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode()
    for attempt in range(15):
        try:
            with urlopen(Request(url, headers=headers), timeout=3) as response:
                if name == "inventory API":
                    assert "summary" in json.load(response)
                if name == "Grafana":
                    assert json.load(response)["database"] == "ok"
            print(name + " passed its deployment check.")
            break
        except (OSError, ValueError, KeyError, AssertionError):
            if attempt == 14:
                raise
            time.sleep(2)
PY_CHECKS
}

pointer="$deploy_dir/.current.$$"
trap 'rm -f "$pointer"' EXIT
if activate "$release" && ln -s "$release" "$pointer" && mv -Tf "$pointer" "$deploy_dir/current"; then
  printf 'deploy_seconds=%s\n' "$((SECONDS - started))"
  echo "Activated $image."
  exit 0
fi

echo "Deployment failed for $image." >&2
compose "$release" logs --no-color --tail=80 app worker prometheus grafana >&2 || true
if [[ -n "$previous" && -f "$previous/image" ]]; then
  echo "Restoring the previous release." >&2
  activate "$previous" || echo "Rollback failed. Check the Compose logs." >&2
else
  compose "$release" stop app worker prometheus grafana >&2 || true
fi
exit 1
