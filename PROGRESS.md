# Progress Log

Chronological record of what's actually been completed from `ROADMAP.md`, with enough
detail to pick the work back up without re-deriving it. Newest entry on top.

---

## 2026-09-19 (b) — Roadmap item 1: closed out

Continuation of the same-day session below. Closed the two remaining item-1 checkboxes.

### What was done
- Read `src/load.py`, `src/sql/orquestacion_modelo.sql`, and `src/sql/transform_financial.sql`
  in full to check every `ON CONFLICT` target in the relational orchestration against the
  live DB's actual constraints (`pg_constraint`). Result: **all 9 tables now have a real
  `UNIQUE`/PK backing their `ON CONFLICT` clause** — `division`, `department`,
  `department_position`, `employee_position_history`, and `payroll_detail` already had theirs;
  `type_employee`, `position`, `employee`, `payroll` got theirs from the morning's
  `schema_fixes.sql`.
- Confirmed `main.py` re-globs and re-reads *every* `.xlsx` under `data/raw/nomina/` on each
  run (no "new files only" filter) — `staging_excel`'s `if_exists='replace'` is therefore a
  full rebuild-and-immediately-consume scratch table, not accumulated history. Documented
  this as a deliberate decision directly in `main.py` at the `to_sql` call site (roadmap item
  1's ask), rather than building an incremental/upsert path that the current design doesn't
  need.
- Documented `transform_financial.sql`'s `TRUNCATE ... CASCADE` (on all 4 fact tables) as a
  deliberate full-refresh decision in a comment above the first `TRUNCATE`, with the
  condition to revisit it (data volume grows, or a need to retain history across corrected
  source files).

### Verified end-to-end
- Captured row counts for all 9 relational tables (`division` 180, `type_employee` 3,
  `department` 454, `position` 317, `department_position` 1806, `employee` 1422,
  `employee_position_history` 5091, `payroll` 16, `payroll_detail` 20229).
- Re-ran `NominaLoader.ejecutar_inserts_relacionales()` against the same, already-loaded
  `staging_excel` (no new source data) — every table's count was identical afterward (delta
  +0 across the board). Confirms the full relational load is idempotent on re-run.

### Known limitation, accepted (not fixed)
`ON CONFLICT DO NOTHING` means a correction to an already-loaded month (e.g. a re-uploaded
Excel with a fixed salary) is silently skipped, not applied, on re-run. Would need `DO
UPDATE` targets instead. Not needed today; noted in `ROADMAP.md` in case the workflow changes.

### Roadmap status
Item 1 is now fully checked off in `ROADMAP.md`. Item 2 was already closed (see entry below).
Next up per the roadmap: item 3 (CLI split for payroll + financial pipelines).

---

## 2026-09-19 (a) — Roadmap item 2 (done) + item 1 (partial): secrets out of code, real dedup bug fixed

### Item 2 — Config & secrets
- `main.py`, `src/extract_financial.py`, `src/transform_financial.py` now build
  `DATABASE_URL` from `DATABASE_HOST` / `DATABASE_PASSWORD` env vars via `python-dotenv`
  (`load_dotenv()`), instead of a hardcoded connection string in all three files.
- `.env` already existed and was already covered by `.gitignore` (`.env` under
  "Environments") — confirmed, not committed.
- Remaining/parked: pinning `requirements.txt` with a lockfile (`uv`/`poetry`) — optional,
  not blocking.

### Item 1 — Idempotent loads (partial)
- **New `src/sql/schema_fixes.sql`**: adds missing `UNIQUE` constraints on
  `type_employee.description`, `position.name`, `employee.name`, and
  `payroll.payroll_date`. Without these, `orquestacion_modelo.sql`'s bare
  `ON CONFLICT DO NOTHING` on those tables was a silent no-op (no constraint to trigger
  a conflict against), so every pipeline re-run inserted duplicate rows. `division` already
  had its constraint. Verified against the live DB (2026-09-19): all four constraints exist,
  zero duplicate keys in any of the four tables, and re-running the script is a clean no-op
  (each block is guarded with `IF NOT EXISTS`).
- **`orquestacion_modelo.sql`**: removed a stray `WHERE pr.id = 2` on the `payroll_detail`
  insert — it was hardcoding the load to a single payroll run instead of processing all of
  them. Real bug, not a style fix.
- **`extract_financial.py`**: the 4 `staging_*` loads switched from
  `to_sql(..., if_exists='append')` to `if_exists='replace')`. `append` was duplicating the
  full staging table on every re-run; `replace` matches how these staging tables are meant to
  be used (full refresh per run, consumed immediately by `transform_financial.sql`).
- **Still open for item 1**: the natural/dedup key for `staging_excel` rows feeding
  `employee_position_history` / `payroll_detail` (payroll pipeline, not financial), and
  documenting/deciding on the `TRUNCATE ... CASCADE` behavior in `transform_financial.sql`.

### Verified
- `schema_fixes.sql` executed against the live DB: applies cleanly, idempotent on re-run.
- `type_employee`, `position`, `employee`, `payroll`: 0 rows with a duplicated natural key.
- `main.py`, `src/extract_financial.py`, `src/transform_financial.py` compile
  (`python -m py_compile`).

### Left for later (tracked in `ROADMAP.md` item 1)
- Dedup key for `staging_excel` / incremental strategy for the payroll pipeline's
  `to_sql(if_exists='replace')` in `main.py`.
- Decision/documentation on `transform_financial.sql`'s `TRUNCATE ... CASCADE`.
- Item 3 (CLI split) is next after item 1 is fully closed out.

---

## 2026-09-07 — Roadmap item 5: automated download from datos.gob.do

**Status: done and tested against the live portal.** Not yet wired into a CLI (blocked on
item 3) and no unit tests yet (item 4).

### What was built
- `src/ingestion/ckan_client.py` — CKAN API client: `fetch_package`, `select_resource`,
  `download_resource` (streamed, retry/backoff via `urllib3.Retry`), `sha256_of_file`,
  `load_manifest`/`save_manifest`.
- `src/ingestion/datasets_config.py` — the 4 dataset definitions (CKAN `package_id`,
  preferred formats, target filename, expected column count).
- `download_datos_gob.py` (repo root, mirrors `main.py`'s convention) — the CLI:
  `python download_datos_gob.py [--force] [--dataset <key>]`.
- Updated `src/extract_financial.py` to read either `.xlsx` or `.csv` per dataset (whichever
  the downloader actually produced), including `;`-delimited/Windows-1252 CSV handling.
- Fixed `requirements.txt`: it was UTF-16 (classic PowerShell `pip freeze > requirements.txt`
  artifact) and missing `openpyxl`, `pyarrow`, `requests` even though the existing code
  already depended on them. Re-saved as plain UTF-8 with those added.

### Format decision (changed mid-implementation)
Original roadmap plan said "prefer CSV over XLSX". The user overrode this explicitly:
**prefer XLSX; fall back to CSV only if XLSX isn't available or usable; never ODS.**
`datasets_config.py` and `download_datos_gob.py` implement that order.

### Two real data-quality bugs found on the source portal while testing
These aren't bugs in our code — they're bugs in what `datos.gob.do` actually serves, and the
downloader now defends against both automatically:

1. **`areas` and `destinos` XLSX resources are "Strict OOXML"**, a rare Excel variant that
   `openpyxl`/`pandas` cannot parse at all (`0 worksheets found`). `cartera` and `desembolsos`
   publish normal "Transitional" OOXML and work fine as XLSX.
2. **`desembolsos`'s XLSX/ODS resources are mislabeled** — their URLs (and content) actually
   point to the `cartera-de-prestamos` file, not desembolsos data. Same column count (5), so a
   naive column-count check doesn't catch it; it would have silently loaded the wrong numbers
   into `staging_desembolsos`. Caught by checking that the resource's own URL contains the
   expected dataset's filename before downloading it.

Net effect after the CSV fallback: `cartera` downloads as XLSX; `desembolsos`, `areas`, and
`destinos` currently download as CSV. This is automatic and re-evaluated on every run — if the
portal ever fixes the source files, the script will pick XLSX back up on its own.

### CSV format specifics (discovered, not assumed)
All 4 CSV resources on this portal use `;` as the delimiter and Windows-1252 ("ANSI") encoding,
not comma-CSV / UTF-8. `_read_csv_flexible` (in `download_datos_gob.py`) and `_leer_fuente`
(in `extract_financial.py`) both try `utf-8-sig` first and fall back to `cp1252`.

### Verified end-to-end
- Full run (`--force`): all 4 datasets land correctly (1 XLSX, 3 CSV, see above).
- Re-run without `--force`: all 4 correctly report "sin cambios" and skip re-downloading,
  confirming the `last_modified` + `sha256` manifest check works.
- Spot-checked `desembolsos` content after the fix: correct `Desembolsos (RD$)` / `Cobros (RD$)`
  columns, not `cartera`'s `Cantidad de Préstamos` / `Valor (RD$)`.
- `manifest.json` and `history/` snapshots confirmed written correctly under
  `data/raw/financial/`.

### Left for later (tracked in `ROADMAP.md` item 5)
- CLI subcommand integration into `main.py` (depends on item 3's CLI split).
- Unit tests mocking `package_show` (item 4) — a real example payload is already captured in
  this session if needed as a fixture basis.
