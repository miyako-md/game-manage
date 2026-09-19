# Public Release Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for execution, with independent security and deployment tasks dispatched in parallel.

**Goal:** Resolve the public-readiness audit and publish the existing repository with sanitized history, while preserving local account data.

**Architecture:** Apply a single local API protection policy; make clean dependency installation and upgrades reproducible; distribute GPL-3.0 code and original placeholder icons. Rewrite only sensitive historical content and remove unlicensed bundled game artwork before publishing.

**Tech Stack:** FastAPI, Python 3.11+, Vue/Vite, Node 22.12+, PowerShell, GitHub Actions.

**Spec:** User-approved 2026-09-18 public-readiness audit; user selected GPL-3.0 on 2026-09-19.

## Global Constraints

- Preserve config.toml, data/, saved logins and unrelated working files.
- Do not send SMS or notifications during verification.
- Keep a private local Git bundle before rewriting history; never publish that backup.
- Verify both remote branch histories are sanitized before changing repository visibility.
- Supported deployment is Windows localhost; do not claim Linux or public multi-user hosting support.

## Review Focus

- Foreign Origin/Host requests cannot mutate or disclose local account data; normal UI and allowed localhost requests still work.
- A changed frontend lock triggers dependency installation even when Vite is already installed; failed installation does not advance the stamp.
- Clean dev installation has all test dependencies; optional OCR use fails clearly when its extra is absent.
- Existing account data remains outside Git and untouched by history cleanup.
- Source and historical text contain no real fixture identities, personal paths or unauthorized bundled artwork.

## Tasks

- [ ] API protection: add regression tests for hostile Host, simple cross-site POST, missing header and accepted UI requests; implement shared guard and update frontend refresh headers; run relevant tests.
- [ ] Deployment: reproduce missing OCR dependency and stale npm installation; add explicit extras and lock fingerprint handling, official npm URLs, CI and documented installation/update/support boundaries; run tests.
- [ ] Licensing/assets: add official GPL-3.0 text, third-party notices and original game identifier SVGs; remove downloaded game artwork from public tracked content.
- [ ] Privacy: replace real fixture identity and personal directories with synthetic values; scan tracked files and all reachable history using private replacement rules.
- [ ] Acceptance: fresh clone/venv installation, full backend/frontend tests, build, isolated startup, dependency audit and independent code review.
- [ ] Publication: private backup; rewrite remote branches with explicit leases; verify a fresh remote clone; set repository public and independently verify anonymous access.

No user confirmation is pending: repairs, history cleanup and publication are authorized; license is GPL-3.0.
