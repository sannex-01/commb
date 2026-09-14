#!/usr/bin/env bash
#
# Build and publish the CommB instance image.
#
# This is the local stand-in for .github/workflows/docker-publish.yml, for when
# GitHub Actions is unavailable. It publishes the same tags that workflow does,
# so either path produces an equivalent result:
#
#   <repo>:latest          moving tag, what provisioning pulls by default
#   <repo>:<version>       from pyproject.toml
#   <repo>:sha-<short sha> immutable, the only tag that identifies exact code
#
# Why this matters beyond convenience: commb-cloud can provision instances
# either by having Coolify build from git (~8 min per instance, repeated for
# every customer) or by pulling a prebuilt image (seconds). The registry path
# is only safe if a current image actually exists -- so publishing has to be
# reliable, not a step someone remembers.
#
# Usage:
#   ./scripts/release-docker.sh              # build + push
#   ./scripts/release-docker.sh --dry-run    # build only, no push
#
set -euo pipefail

IMAGE="${COMMB_IMAGE_REPO:-samakins/commb}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

cd "$(dirname "$0")/.."

# --- preflight -------------------------------------------------------------
# Each of these fails loudly here rather than halfway through a push.

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker is not running." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "warning: working tree is dirty. The image will be built from your" >&2
  echo "         WORKING COPY, but tagged with the last commit's sha -- so the" >&2
  echo "         sha tag would name code that is not what shipped." >&2
  read -r -p "Continue anyway? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || exit 1
fi

SHA="$(git rev-parse --short HEAD)"
VERSION="$(grep -m1 '^version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')"

if [[ -z "$VERSION" ]]; then
  echo "error: could not read version from pyproject.toml" >&2
  exit 1
fi

echo "repo    : $IMAGE"
echo "version : $VERSION"
echo "commit  : $SHA"
echo

# --- build -----------------------------------------------------------------
# Built once and tagged three ways, so all tags are bit-identical rather than
# three separate builds that could drift.

docker build \
  --tag "$IMAGE:latest" \
  --tag "$IMAGE:$VERSION" \
  --tag "$IMAGE:sha-$SHA" \
  --file ./Dockerfile \
  .

if [[ "$DRY_RUN" == "1" ]]; then
  echo
  echo "dry run: built but not pushed."
  exit 0
fi

# --- push ------------------------------------------------------------------

if ! docker push "$IMAGE:sha-$SHA"; then
  echo >&2
  echo "error: push failed. If this is an auth problem, run: docker login" >&2
  exit 1
fi
docker push "$IMAGE:$VERSION"
docker push "$IMAGE:latest"

echo
echo "published:"
echo "  $IMAGE:latest"
echo "  $IMAGE:$VERSION"
echo "  $IMAGE:sha-$SHA   <- pin to this for a reproducible deploy"
