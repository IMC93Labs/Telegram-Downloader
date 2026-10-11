# Release privacy review

The Windows v1.25 EXE was inspected before publication on 2026-10-11.

## Checks performed

- Enumerated the PyInstaller archive and unpacked its entries and Python modules: **6,751 entries checked**.
- Searched the decompressed content for known private credentials from local development/runtime configuration and local Windows profile references: **no matches**.
- Checked for private `.env`, authenticated `.session` files, saved connections, configuration, download history, test modules and local QA data: **none included**.
- Reviewed the installer file allowlist: executable, blank `.env.example` and application icon only.
- Prepared the repository from an explicit source/assets allowlist; excluded local data, environments, build caches and prior binaries.
- Captured documentation screenshots using simulated data; no personal profile path or real credentials shown.

This is a release-specific inspection against known private values, not a formal security audit or a guarantee that all possible information can be detected. Public application names, branding and bundled third-party dependencies are intentionally included.

## Local data after installation

Credentials and sessions are stored in `%LOCALAPPDATA%\TelegramDownloader`. Credentials are not encrypted. Do not share that directory, `.env`, `connections.json` or authenticated session files. The application sends service requests to Telegram, AllDebrid and qBittorrent when the corresponding integrations are used.

Release assets include `SHA256SUMS.txt` for integrity verification. Hashes establish file identity, not publisher identity or code signing.
