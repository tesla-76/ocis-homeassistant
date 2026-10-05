# ownCloud Infinite Scale for Home Assistant

Lightweight HACS integration to monitor OCIS 8.x: version, users, storage used, quota states, file activity and account switches.

## Why this design (efficient + light)

- **App token, no OIDC refresh**: uses `ocis auth-app create` token sent as Basic `username:token`. No background token refresh, no extra auth calls.
- **~4 tiny HTTP calls per cycle**: `status.php` (unauthenticated) + `users` + `drives` + `groups` (best-effort, in parallel). Default every 15 min, configurable 1–60. Account switches use one PATCH call each, only when toggled.
- **No extra dependencies**: only HA-provided `aiohttp`. No Prometheus debug port needed.
- **Coordinator with `always_update=False`**: no state writes when data is unchanged.

Alternative considered and rejected: OIDC password grant (fragile behind reverse proxy, short-lived tokens), Prometheus `/metrics` (needs debug port 9205 open, only proxy counters), WebDAV PROPFIND per drive (N calls, heavier).

## Prerequisites (OCIS side)

1. Enable app auth once on the OCIS host:
   `OCIS_ADD_RUN_SERVICES=auth-app`, `PROXY_ENABLE_APP_AUTH=true`, restart `ocis server`.
2. Create token: `ocis auth-app create --user-name=admin --expiration=8760h`
3. OCIS reachable via reverse proxy (e.g. `https://ocis.example.com`). For self-signed certs, untick "Verify SSL" during setup.
4. Account enable/disable switches need a write-enabled user backend (default internal IDM is fine). With a read-only LDAP they report an error when toggled, without breaking polling.

## Install via HACS (custom repo)

1. HACS → Integrations → ⋮ → Custom repositories → add this repo URL, category Integration.
2. Install, restart HA, Settings → Devices & Services → Add Integration → ownCloud Infinite Scale.
3. Enter base URL, username, app token. Set polling in Options (default 15 min).

## Entities

Server device `OCIS <host>` (version, users, storage, online) + one device per
OCIS user (account switch + that user's Space sensors + latest own activity) +
`OCIS shared spaces` for project/shared Spaces with no single owner.

Globals: version, edition, users total/disabled, groups total (may be unavailable if forbidden), spaces total, storage used (GB), worst quota state across Spaces, latest activity overall. Per user: account switch + own Spaces (used in GB, quota state with translated `normal`/`nearing`/`critical`/`exceeded`) + latest own activity. Binary `online`. Switches are never created for the primary account used in setup (matched by user id, username fallback).

Entities of deleted users, deleted Spaces and removed sensor types are cleaned up automatically.

## Known limitations

- Drives listed are those visible to the token user; an admin token sees all.
- `quota.total = 0` means unlimited in OCIS (with `remaining` = max-int64).
- Global storage used counts real Spaces only; virtual drives (Shares) are excluded. It is a sum of Space quotas, not host disk: for real host-disk free space, monitor the OCIS machine itself (e.g. SNMP on the LXC).
- Groups count is best-effort; polling still succeeds if forbidden.

## Translations

UI and entity names ship in English and Italian and follow the HA language. To add a language, copy `custom_components/ocis/translations/en.json` to `<code>.json` (e.g. `fr.json`), translate the values keeping all keys, and open a PR.

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

---

# ownCloud Infinite Scale per Home Assistant (Italiano)

Integrazione HACS leggera per monitorare OCIS 8.x: versione, utenti, spazio usato, stati quota, attività file e interruttori account.

## Perché questo design (efficiente e leggero)

- **App token, niente refresh OIDC**: usa il token di `ocis auth-app create` inviato come Basic `username:token`. Nessun refresh in background, nessuna chiamata extra.
- **~4 piccole chiamate HTTP per ciclo**: `status.php` (senza auth) + `users` + `drives` + `groups` (best-effort, in parallelo). Default ogni 15 min, configurabile 1–60. Gli interruttori usano una chiamata PATCH ciascuno, solo quando azionati.
- **Nessuna dipendenza extra**: solo `aiohttp` già fornito da HA. Nessuna porta debug Prometheus.
- **Coordinator con `always_update=False`**: nessuno stato scritto se i dati non cambiano.

Alternative scartate: grant password OIDC (fragile dietro reverse proxy, token brevi), Prometheus `/metrics` (richiede la porta debug 9205, solo contatori proxy), PROPFIND WebDAV per Space (N chiamate, più pesante).

## Prerequisiti (lato OCIS)

1. Abilita app auth una volta sull'host OCIS:
   `OCIS_ADD_RUN_SERVICES=auth-app`, `PROXY_ENABLE_APP_AUTH=true`, riavvia `ocis server`.
2. Crea il token: `ocis auth-app create --user-name=admin --expiration=8760h`
3. OCIS raggiungibile via reverse proxy (es. `https://ocis.example.com`). Con certificati self-signed togli la spunta "Verifica SSL" nel setup.
4. Gli interruttori abilita/disabilita richiedono un backend utenti in scrittura (l'IDM interno va bene). Con LDAP in sola lettura danno errore all'uso, senza rompere il polling.

## Installazione via HACS (repo personalizzato)

1. HACS → Integrazioni → ⋮ → Repository personalizzati → aggiungi l'URL di questo repo, categoria Integrazione.
2. Installa, riavvia HA, Impostazioni → Dispositivi e servizi → Aggiungi integrazione → ownCloud Infinite Scale.
3. Inserisci URL base, username, app token. Imposta il polling in Opzioni (default 15 min).

## Entità

Device server `OCIS <host>` (versione, utenti, spazio, online) + un device per
utente OCIS (interruttore account + sensori dei suoi Space + ultima attività
propria) + `OCIS shared spaces` per gli Space progetto/condivisi senza singolo
proprietario.

Globali: versione, edizione, utenti totali/disabilitati, gruppi totali (può non essere disponibile), spazi totali, spazio usato (GB), stato quota peggiore, ultima attività generale. Per utente: interruttore account + propri Space (usato in GB, stato quota tradotto `normale`/`quasi pieno`/`critico`/`superata`) + ultima attività propria. Binary `online`. Gli interruttori non vengono mai creati per l'account primario del setup (riconosciuto per id, fallback username).

Entità di utenti/Spazi cancellati e di tipi sensore rimossi si puliscono da sole.

## Limiti noti

- Gli Space elencati sono quelli visibili all'utente del token; con token admin si vedono tutti.
- `quota.total = 0` in OCIS significa illimitato (con `remaining` = max-int64).
- Lo spazio usato globale conta solo gli Space reali; i drive virtuali (Shares) sono esclusi. È una somma di quote, non il disco host: per lo spazio reale del disco monitora la macchina OCIS (es. SNMP su LXC).
- Il conteggio gruppi è best-effort; il polling continua anche se vietato.

## Traduzioni

UI e nomi entità in inglese e italiano, seguono la lingua di HA. Per altre lingue copia `custom_components/ocis/translations/en.json` in `<codice>.json` (es. `fr.json`), traduci i valori mantenendo le chiavi e apri una PR.

## Test

```bash
pip install pytest-homeassistant-custom-component==<for-your-HA>
pytest tests/ -v
```

Come sopra per la suite inglese; stessi requisiti (HA 2025+, Python 3.13, CI).

## Rimozione

Impostazioni → Dispositivi e servizi → OCIS → Elimina. Revoca inoltre il token sull'host OCIS.
