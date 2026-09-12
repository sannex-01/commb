# Releasing CommB

Two ways to publish: **manually from a terminal** (needed for the very first
release of a package) and **via GitHub Actions** (everything after that).

> **Why the first release must be manual:** PyPI Trusted Publishing is configured
> *per project*, and a project only exists once something has been uploaded to it.
> You can either use PyPI's "pending publisher" flow, or — simpler — publish v1 by
> hand with a token, then configure trusted publishing and let CI take over.

---

## One-time account setup

| What | Where | Notes |
| :--- | :--- | :--- |
| GitHub repo `sannex-01/commb` | github.com/new | Public |
| GitHub repo `sannex-01/commb-agent` | github.com/new | Public |
| PyPI project `commb` | pypi.org | Created by the first upload |
| PyPI project `commb-agent` | pypi.org | Created by the first upload |
| npm org `@commb` | npmjs.com → Add Organization | Free for public packages |
| Docker Hub `samakins/commb` | hub.docker.com | Created by the first push |

---

## First push of the repositories

Remotes are already pointed at the new locations. After creating the two empty
GitHub repos (no README, no .gitignore — the history supplies them):

```bash
cd ~/Documents/Projects/commb
git push -u origin main

cd ~/Documents/Projects/commb-agent
git push -u origin main
```

---

## Publish order

The packages are independent — `commb-agent` is only an **optional** extra of
`commb` (`pip install commb[telemetry]`), never a hard dependency, because a
self-hosted CommB must be able to run without ever phoning home. So there is no
required ordering and no cross-registry waiting:

```
PyPI:   commb           (server, AGPL-3.0)
PyPI:   commb-agent     (telemetry SDK, MIT — optional extra)
npm:    @commb/agent    (telemetry SDK, MIT)
Docker: samakins/commb  (builds from requirements.txt; no SDK needed)
```

> **Do not add `commb-agent` to `requirements.txt`.** It belongs only in
> `pyproject.toml` under `[project.optional-dependencies] telemetry`. Listing it
> as a hard requirement makes the Docker build fail (`No matching distribution
> found`) whenever the SDK version is not yet on PyPI, and silently turns
> phone-home into a mandatory install for self-hosters.

---

## Manual publish — Python

Create an API token at <https://pypi.org/manage/account/token/>. For the very
first upload the token must be account-scoped, since the project does not exist
yet; afterwards, replace it with a project-scoped token or trusted publishing.

```bash
# --- main app ---
cd ~/Documents/Projects/commb
rm -rf dist build *.egg-info

# The widget bundle ships inside the package, so build it first.
# Check the output is FRESH — a stale widget/dist from before a rebrand or UI
# change will silently ship the old bundle; the file existing is not enough.
cd widget && npm ci && npm run build && cd ..

python -m pip install --upgrade build twine
python -m build                       # -> dist/commb-0.2.0{.tar.gz,-py3-none-any.whl}
python -m twine check dist/*

# Sanity-check the wheel: widget bundled, node_modules not
python -c "import zipfile;n=zipfile.ZipFile('dist/commb-0.2.0-py3-none-any.whl').namelist();print('widget:',any(x.endswith('widget/dist/widget.js') for x in n));print('node_modules:',sum('node_modules' in x for x in n))"

# Dry run against TestPyPI first (optional but recommended)
python -m twine upload --repository testpypi dist/*

# Real upload — username is literally __token__
python -m twine upload dist/*
```

```bash
# --- telemetry SDK (independent of the server release) ---
cd ~/Documents/Projects/commb-agent/packages/python
rm -rf dist build
python -m build                       # -> dist/commb_agent-0.3.0*
python -m twine check dist/*
python -m twine upload dist/*
```

Verify:

```bash
pip index versions commb
pip install commb                     # then: commb version
pip install 'commb[telemetry]'        # only when pointing at a collector
```

## Manual publish — npm (`@commb/agent`)

```bash
cd ~/Documents/Projects/commb-agent/packages/js
npm login                             # must be a member of the @commb org
npm ci
npm run build
npm publish --access public           # --access public is REQUIRED for a scoped package
```

`--access public` matters: scoped packages default to *restricted*, which fails
on a free account.

## Manual publish — Docker (`samakins/commb`)

> The image installs only `requirements.txt`, which deliberately excludes the
> telemetry SDK — so it builds regardless of what is on PyPI, and the resulting
> container never phones home.

```bash
cd ~/Documents/Projects/commb
docker login
docker build -t samakins/commb:v0.2.0 -t samakins/commb:latest .
docker push samakins/commb:v0.2.0
docker push samakins/commb:latest
```

The Dockerfile builds the widget itself in stage 1, so no local `widget/dist` is
needed here — unlike the Python package above.

---

## After the first release: switch to CI

Once each PyPI project exists, configure trusted publishing so no token is ever
stored in GitHub:

**`commb`** — <https://pypi.org/manage/project/commb/settings/publishing/>
| Field | Value |
| :--- | :--- |
| Owner | `sannex-01` |
| Repository | `commb` |
| Workflow | `pypi-publish.yml` |
| Environment | `pypi` |

**`commb-agent`** — <https://pypi.org/manage/project/commb-agent/settings/publishing/>
| Field | Value |
| :--- | :--- |
| Owner | `sannex-01` |
| Repository | `commb-agent` |
| Workflow | `publish-pypi.yml` |
| Environment | `pypi` |

Then in each GitHub repo, create the environments the workflows bind to
(Settings → Environments): `pypi` in both, plus `npm` in `commb-agent` holding
an `NPM_TOKEN` secret (a granular automation token scoped to the `@commb` org).
Docker Hub needs `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` in `commb`.

### Release tags

The two SDK workflows are scoped to separate tag prefixes so publishing one
package never publishes the other:

| Tag | Publishes |
| :--- | :--- |
| `v*` in `commb` | PyPI `commb` (`pypi-publish.yml`) **and**, separately, the Docker image (`docker-publish.yml`) |
| `py-v*` in `commb-agent` | PyPI `commb-agent` |
| `js-v*` in `commb-agent` | npm `@commb/agent` |

`pypi-publish.yml` and `docker-publish.yml` are separate workflows triggered by
the same `v*` tag and run concurrently. That is safe: the Docker image does not
install the SDK, so neither job depends on the other. Note that
`docker-publish.yml` also triggers on every push to `main`, not just on tags.

```bash
git tag v0.2.1 && git push origin v0.2.1          # commb
git tag py-v0.3.1 && git push origin py-v0.3.1    # commb-agent, Python only
git tag js-v0.3.1 && git push origin js-v0.3.1    # commb-agent, npm only
```

---

## Version bump checklist

Keep these in sync before tagging (see also `AGENTS.md`):

**`commb`** — `pyproject.toml` `version`, `app/core/config.py` `APP_VERSION`,
and the version assertions in `tests/test_reports_and_system.py` and
`tests/test_system_and_releases.py`.

**`commb-agent`** — `packages/python/pyproject.toml`, `packages/python/commb_agent/__init__.py`
(`__version__`), and `packages/js/package.json`. If the Python SDK's floor moves,
update the `commb[telemetry]` extra in the main repo's `pyproject.toml` to match.
