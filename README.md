# ownCloud Infinite Scale for Home Assistant

Lightweight HACS integration to monitor OCIS 8.x: version, users, groups, storage totals and per-Space quota.

## Why this design (efficient + light)

- **App token, no OIDC refresh**: uses `ocis auth-app create` token sent as Basic `username:token`. No background token refresh, no extra auth calls.
- **~4 tiny HTTP calls per cycle**: `status.php` (unauthenticated) + `users` + `drives` + `groups` (best-effort, in parallel). Default every 15 min, configurable 1–60.
- **No extra dependencies**: only HA-provided `aiohttp`. No Prometheus debug port needed.
- **Coordinator with `always_update=False`**: no state writes when data is unchanged.

Alternative considered and rejected: OIDC password grant (fragile behind reverse proxy, short-lived tokens), Prometheus `/metrics` (needs debug port 9205 open, only proxy counters), WebDAV PROPFIND per drive (N calls, heavier).

## Prerequisites (OCIS side)

1. Enable app auth once on the OCIS host:
   `OCIS_ADD_RUN_SERVICES=auth-app`, `PROXY_ENABLE_APP_AUTH=true`, restart `ocis server`.
2. Create token: `ocis auth-app create --user-name=admin --expiration=8760h`
3. OCIS reachable via reverse proxy (e.g. `https://ocis.example.com`). For self-signed certs, untick "Verify SSL" during setup.

## Install via HACS (custom repo)

1. HACS → Integrations → ⋮ → Custom repositories → add this repo URL, category Integration.
2. Install, restart HA, Settings → Devices & Services → Add Integration → ownCloud Infinite Scale.
3. Enter base URL, username, app token. Set polling in Options (default 15 min).

## Entities

Server device `OCIS <host>` (version, users, storage, online) + one device per
OCIS user (account switch + that user's Space sensors) + `OCIS shared spaces`
for project/shared Spaces with no single owner.

Globals: version, edition, users total/active/disabled, groups total (may be unavailable if forbidden), spaces total, storage used (GB), worst quota state across Spaces, latest Space activity. Binary `online`. Switches: one per account to enable/disable it — never created for the primary account used in setup (matched by user id, username fallback).

Per-drive (both enabled by default): used (GB) and quota state (`normal`/`nearing`/`critical`/`exceeded`). Extra attributes: drive name/type/owner. Entities of removed sensor types are cleaned up automatically.

## Known limitations

- Drives listed are those visible to the token user; an admin token sees all.
- `quota.total = 0` means unlimited in OCIS (with `remaining` = max-int64).
- Global storage used counts real Spaces only; virtual drives (Shares) are excluded.
- Groups count is best-effort; polling still succeeds if forbidden.
- Storage totals are sums of returned Spaces, not host disk. For real host-disk
  free space, monitor the OCIS machine itself (e.g. SNMP on the LXC).

## Tests

```bash
pip install pytest-homeassistant-custom-component==<for-your-HA>
pytest tests/ -v
```

`test_helpers.py` covers quota math (incl. `total=0` unlimited and virtual
drives) and URL normalization; `test_config_flow.py` covers success,
`cannot_connect` and `invalid_auth`. The suite needs HA 2025+ (Python 3.13)
and runs in CI. Locally without HA, at minimum run `py_compile` on all files
plus JSON validation of the manifests.

## Removal

Settings → Devices & Services → OCIS → Delete. Tokens should additionally be revoked on the OCIS host.
