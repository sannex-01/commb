# Contributing to CommB

Thanks for your interest in CommB. This document covers the licence, how
contributions are handled, and how to get a development environment running.

## Licence and contributor agreement

CommB is licensed under the **GNU Affero General Public License v3.0 or later**
(AGPL-3.0-or-later). See [LICENSE](LICENSE).

What that means in practice:

- **Using and self-hosting CommB is free and unrestricted.** Run it for your own
  business, modify it however you like, and you owe nothing to anyone.
- **If you modify CommB and offer it to others over a network**, the AGPL
  requires you to make your modified source available to those users under the
  same licence.

### Contributor Licence Agreement (CLA)

By submitting a pull request, you agree that:

1. You wrote the contribution yourself, or otherwise have the right to submit it
   under the project's licence.
2. You grant **Sannex Tech LTD** a perpetual, worldwide, non-exclusive,
   royalty-free licence to use, modify, sublicense and relicense your
   contribution, including as part of a commercially hosted service.

Point 2 exists so the project can keep offering managed hosting at
[commb.app](https://commb.app) and, if ever needed, adjust licensing without
having to track down every past contributor. Your contribution remains available
to everyone under the AGPL regardless.

If you are contributing on behalf of an employer, make sure you have their
permission before opening a PR.

## Development setup

```bash
git clone https://github.com/sannex-01/commb.git
cd commb

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env           # then fill in what you need
python doctor.py               # pre-flight check
uvicorn app.main:app --port 8422 --reload
```

Open <http://localhost:8422/_/admin> for the admin UI and
<http://localhost:8422/docs> for the OpenAPI explorer.

### Running the tests

```bash
python -m pytest tests/ -q
```

Please make sure the suite passes before opening a pull request, and add tests
covering any behaviour you change.

## Pull request guidelines

- **Keep PRs focused.** One logical change per PR is much easier to review than
  a large mixed diff.
- **Match the surrounding code.** The codebase favours explanatory comments that
  say *why* something is done, not *what* the line does — follow that style.
- **Don't commit secrets.** `.env` and every `.env.*` variant are gitignored; if
  you need a new setting, add it to `.env.example` with a safe placeholder.
- **Note breaking changes explicitly** in the PR description, including any
  environment variables or API responses that change shape.

## Reporting security issues

Please do **not** open a public issue for a security vulnerability. Email
<info@sannex.ng> instead, and allow reasonable time for a fix before any public
disclosure.
