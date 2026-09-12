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

## Publish order (this is not arbitrary)

The steps below depend on each other, so run them in this order:

```
1. PyPI: commb-agent   ──┐
2. PyPI: commb           │  commb depends on commb-agent>=0.3.0
3. npm:  @commb/agent    │  Docker installs commb-agent from PyPI
4. Docker: samakins/commb ┘
```

**The Docker image cannot be built until `commb-agent` is live on PyPI.**
`Dockerfile` line 32 runs `pip install -r requirements.txt`, which resolves
`commb-agent>=0.3.0` from the registry. Build it before that upload lands and it
fails with `No matching distribution found for commb-agent>=0.3.0`. Publishing
`commb` before `commb-agent` is likewise a broken release: anyone installing it
gets an unresolvable dependency.

npm (step 3) is independent of the Python packages and can happen any time.

---

## Manual publish — Python (`commb-agent` first, then `commb`)

Create an API token at <https://pypi.org/manage/account/token/>. For the very
first upload the token must be account-scoped, since the project does not exist
yet; afterwards, replace it with a project-scoped token or trusted publishing.

```bash
# --- SDK: publish this FIRST, commb depends on it ---
cd ~/Documents/Projects/commb-agent/packages/python
rm -rf dist build
python -m build                       # -> dist/commb_agent-0.3.0*
python -m twine check dist/*
python -m twine upload dist/*
```

Wait for it to resolve before continuing — PyPI's index can lag the upload by a
few moments:

```bash
pip index versions commb-agent        # must list 0.3.0 before you go on
```

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

Verify:

```bash
pip index versions commb
pip install commb                     # then: commb version
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

> **Requires `commb-agent` to already be on PyPI.** The image installs it from
> the registry during the build, so this step must come last. If it is not yet
> published the build fails at the `pip install -r requirements.txt` layer.

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

> **Ordering hazard on version bumps.** `pypi-publish.yml` and `docker-publish.yml`
> are separate workflows triggered by the same `v*` tag, with no `needs:` between
> them — they run concurrently. The same dependency from the first release still
> applies: if a release bumps `commb-agent` and the Docker build starts before that
> new version is on PyPI, the image build fails (or silently pins the older SDK,
> depending on the requirement floor).
>
> So when a release moves both packages: push `py-v*` in `commb-agent` first, wait
> for PyPI, then push `v*` in `commb`. A `commb`-only release has no such
> constraint.
>
> Note also that `docker-publish.yml` triggers on every push to `main`, not just
> on tags — so `main` must never reference an unpublished `commb-agent` version.

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
