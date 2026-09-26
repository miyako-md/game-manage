# Changelog

## Unreleased

- Arknights: Endfield (official server): Hypergryph account SMS login, account card, headhunting records synced from the official API into a local ledger (seqId de-duplication, resumable first sync, gap-aware pity counts), record list and export.
- Endfield Bilibili source (UID 1265652806) with an announcement parser for version-name titles, relative starts, “until the next version update” ends resolved from the next maintenance notice, dependent ends and multi-phase times.
- Bilibili rule version 5 keeps Endfield notices whose body mentions web events.
- Existing installations must add `endfield = "1265652806"` under `[bilibili_sources]` in `config.toml`. Endfield endpoints are not yet verified against a real account.

## 0.1.0 — 2026-09-19

First public source release of the Windows localhost game dashboard.

- Vue dashboard and compact activity timeline for Wuthering Waves, NTE and League of Legends.
- Community login, source-backed account data, public announcements and local data storage.
- Consistent API Host/Origin checks and explicit write-request headers.
- Reproducible dependency lock, clean installation CI, optional OCR dependencies and frontend dependency fingerprinting.
- GPL-3.0-only licensing, third-party notices and original game identifier icons.
- Synthetic test identities and sanitized published Git history.

This release supports Windows local single-user use. Linux, public multi-user hosting, real SMS flows for arbitrary accounts and upstream data accuracy are not certified by automated tests. NTE stamina/city activity can be delayed by the official data source. See README for installation, upgrade and current feature boundaries.
