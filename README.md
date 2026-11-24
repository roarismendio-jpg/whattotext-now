# @whattotext.now engine

The exact words for hard moments. A fully automated Instagram account. Runs on GitHub Actions every 15 minutes (free for public repos): renders posts, hosts media on GitHub Pages, publishes through Instagram's official API, measures, tests, and keeps learning. The playbook is in `CLAUDE.md`.

- Dashboard: https://roarismendio-jpg.github.io/whattotext-now/dashboard.html
- Content queue: `content/*.json`
- Private state (database, comment log, token) is encrypted in `data/*.enc`.

Secrets (Settings → Secrets and variables → Actions): `IG_ACCESS_TOKEN`, `TOKEN_KEY` (any long random phrase).
Variable: `PUBLISH` = `on` to post, anything else = dry run.
