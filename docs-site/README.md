# CommB Docs

The source for [docs.commb.app](https://docs.commb.app), built with [Docusaurus](https://docusaurus.io/).

## Local development

```bash
npm install
npm run start
```

Starts a local server with live reload.

## Build

```bash
npm run build
```

Generates static output into `build/`.

## How the hosted docs are deployed

`docs.commb.app` is served by **Cloudflare Pages**, connected directly to this
repository. Every push to `main` that touches `docs-site/` triggers a Pages
build automatically — nothing to run by hand, no server involved.

Pages settings (for reference, not something you configure here):

- Root directory: `docs-site`
- Build command: `npm run build`
- Build output directory: `build`

## Self-hosting these docs

If you've forked CommB and want to run your own copy of the docs (for example
alongside a self-hosted CommB instance), the `Dockerfile` and `nginx.conf` in
this directory build and serve them as a standalone container:

```bash
docker build -t commb-docs .
docker run -p 8080:80 commb-docs
```

That path is **not** what powers docs.commb.app — it's kept here only as a
self-hosting option, since CommB is open source and a fork won't have access
to this project's Cloudflare Pages setup.
