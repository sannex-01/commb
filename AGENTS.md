# CommB — Agent & Developer Guidelines

## Repository Structure

```
commb/
├── app/
│   ├── admin_ui/        # Vanilla SPA management portal (HTML/CSS/JS)
│   ├── ai/              # LLM engine, memory, RAG, & flow engine
│   ├── api/             # FastAPI REST & webhook routes
│   ├── core/            # Config, database, security, & logger
│   ├── models/          # SQLAlchemy ORM models
│   ├── services/        # Commerce, email, payment, & sync services
│   ├── cli.py           # Standalone CLI entrypoint (`commb start`, `commb doctor`)
│   └── main.py          # FastAPI application entrypoint
├── widget/              # Embeddable website chat widget (Vite/TS bundle)
├── tests/               # Pytest suite (unit, integration, API tests)
├── .github/workflows/   # CI/CD: Docker Hub, GHCR, & PyPI publishing
├── Dockerfile           # Multi-stage production container build
├── docker-compose.yml   # Multi-container stack (Postgres + CommB)
├── pyproject.toml       # PyPI packaging & script definitions
└── requirements.txt     # Python runtime dependencies
```

---

## Synchronized Files on Every Version Bump

Before cutting a new release, you **MUST** bump the version across all of the following files:

1. **Python Package Config**: `pyproject.toml`
   ```toml
   [project]
   version = "X.Y.Z"
   ```
2. **App Core Config**: `app/core/config.py`
   ```python
   APP_VERSION: str = "X.Y.Z"
   ```
3. **CommB README**: `README.md`
   - Update version badges or release notes.
4. **Documentation Site** (`Projects/agentOS/docs-site`):
   - Add/update release blog: `docs-site/blog/YYYY-MM-DD-vX.Y.Z-release.md`
   - Update quickstart or feature notes if new flags/APIs were introduced.

---

## Versioning Standards (SemVer)

- **PATCH (`0.1.0` &rarr; `0.1.1`)**: Bug fixes, minor UI tweaks, internal retry logic, or database migration patches.
- **MINOR (`0.1.x` &rarr; `0.2.0`)**: New channels, payment providers, RAG capabilities, or additive CLI flags.

- **MAJOR (`0.x.y` &rarr; `1.0.0`)**: Breaking database schema alterations, removed CLI commands, or breaking API changes.

---

## Release & Git Tagging Standard

Releases are triggered via Git tags matching `v*`.

### Automated Release Workflow

1. **Verify Local Tests & Build**:
   ```bash
   # Run full test suite
   pytest tests/ -v

   # Verify CLI & Doctor
   python -m app.cli doctor

   # Verify widget build
   cd widget && npm install && npm run build && cd ..
   ```

2. **Commit Code & Version Bump**:
   ```bash
   git add pyproject.toml app/core/config.py README.md
   git commit -m "chore(release): bump version to vX.Y.Z"
   git push origin main
   ```

3. **Tag & Push Release**:
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z: Summary of features"
   git push origin vX.Y.Z
   ```

4. **GitHub Actions Execution**:
   - `.github/workflows/docker-publish.yml` builds and pushes to GHCR (`ghcr.io`) and Docker Hub.
   - `.github/workflows/pypi-publish.yml` builds the wheel/sdist and uploads to PyPI.

---

## Required Repository Secrets

Configure in **GitHub Repo &rarr; Settings &rarr; Secrets and variables &rarr; Actions**:

| Secret Name | Source | Purpose |
|---|---|---|
| `PYPI_API_TOKEN` | [pypi.org](https://pypi.org) &rarr; Account Settings &rarr; API Tokens | Uploading `commb` to PyPI |
| `DOCKERHUB_USERNAME` | [hub.docker.com](https://hub.docker.com) | Docker Hub username |
| `DOCKERHUB_TOKEN` | [hub.docker.com](https://hub.docker.com) &rarr; Security &rarr; Access Tokens | Docker Hub authentication |

*Note: Ensure **Settings &rarr; Actions &rarr; General &rarr; Workflow permissions** is set to **"Read and write permissions"**.*

---

## Manual Fallback Publishing

### A. Publish to PyPI
```bash
pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

### B. Publish Docker Image
```bash
docker build -t samakins/commb:vX.Y.Z -t samakins/commb:latest .
docker push samakins/commb:vX.Y.Z
docker push samakins/commb:latest
```
