# Roadmap — Data Engineering Hardening

Tracking doc for the improvements we agreed to prioritize. Scope is intentionally
narrow (5 items) so we don't lose focus — expand only after these are done.

## 1. Idempotent loads
- [ ] Replace `to_sql(name='staging_excel', if_exists='replace', ...)` in `main.py`
      with an incremental/upsert strategy (or at minimum a delete-by-`fecha`+reinsert
      per processed file, not a full-table wipe every run).
- [ ] Define a natural/dedup key for `staging_excel` rows (e.g. `nombres + apellidos + fecha + sucursal`)
      so re-running the pipeline on the same month doesn't create duplicate history rows
      downstream in `employee_position_history` / `payroll_detail`.
- [ ] Same concern applies to `transform_financial.sql`: it currently `TRUNCATE ... CASCADE`s
      every fact table on every run — fine for full-refresh today, but document it as a
      deliberate decision (or move to a partition/date-scoped delete) before it's relied on
      for incremental runs.

**Why it matters:** right now re-running `main.py` for a month you've already loaded silently
duplicates or corrupts relational history (`employee_position_history`, `payroll_detail`).

**Progress (2026-09-19):** found and fixed a related bug while investigating this — bare
`ON CONFLICT DO NOTHING` on `type_employee`, `position`, `employee`, and `payroll` was a
silent no-op because those tables had no `UNIQUE` constraint to trigger a conflict against
(`division` did). Fixed in `src/sql/schema_fixes.sql`, verified against the live DB (no
duplicates, constraints in place, script is idempotent). Also removed a stray
`WHERE pr.id = 2` in `orquestacion_modelo.sql` that was hardcoding the `payroll_detail` load
to one payroll run. `extract_financial.py`'s 4 staging loads switched `append` → `replace`
to stop duplicating on re-run. The three checkboxes above (staging_excel dedup key,
TRUNCATE CASCADE decision) are still open. See `PROGRESS.md` for full detail.

## 2. Config & secrets
- [x] Move `DATABASE_URL` out of `main.py`, `src/extract_financial.py`, and
      `src/transform_financial.py` (hardcoded in all three) into a `.env` file, loaded via
      `python-dotenv`. Done 2026-09-19 — see `PROGRESS.md`.
- [x] Confirm `.env` is in `.gitignore`. Already covered (`.env` under "Environments");
      confirmed 2026-09-19.
- [x] Fix `requirements.txt` — was corrupted/UTF-16 (classic PowerShell `pip freeze >` artifact).
      Re-saved as plain UTF-8 while building the downloader (item 5); also added `openpyxl`,
      `pyarrow`, `requests`, which the code already depended on but were missing from the file.
- [ ] Consider pinning with a lockfile (`uv` or `poetry`) instead of a hand-edited
      `requirements.txt`.

**Why it matters:** a checked-in DB password is a real credential leak risk the moment this
repo is pushed anywhere shared; the corrupted `requirements.txt` currently can't be
`pip install -r`'d reliably.

## 3. Orchestration & scheduling
- [ ] Turn `main.py` into a small CLI (`argparse` or `click`) that can run:
      - the payroll pipeline (current `run_pipeline()`), and
      - the financial pipeline (`extract_financial.py` / `transform_financial.py`,
        which currently have no loader/orchestration wired up).
- [ ] Once both pipelines run from one entry point, evaluate a real orchestrator
      (Airflow / Dagster / Prefect) for retries, scheduling, and per-task observability —
      only after the CLI split, so there's something meaningful to orchestrate.

**Why it matters:** the financial pipeline files exist but aren't callable yet; there's no
way to run "just financial" or "just payroll" today.

## 4. Testing
- [ ] Unit tests for `NominaExtractor._homologar_columnas` / `reparar_y_extraer`
      (edge cases: missing columns, singular `nombre`/`apellido` vs `nombres`/`apellidos`,
      malformed `sueldo_nominal` values like `$1,234.56`).
- [ ] Unit tests for `NominaTransformer.transformar_mes` (`_convertir_fecha_excel` edge
      cases: Excel serial dates, the 1900 leap-year bug, unparseable strings, the
      género/fecha_contratacion maestro fallback logic).
- [ ] Small fixture `.xlsx` files under `tests/fixtures/` instead of relying on real data.
- [ ] Integration test that runs `orquestacion_modelo.sql` against a throwaway/test
      Postgres schema and asserts row counts land correctly.

**Why it matters:** none of the column-homologation or date-parsing logic — the parts most
likely to silently break on a new month's file format — has any test coverage today.

## 5. Automated download from datos.gob.do (financial data source)
**Status: core script done and tested against the live portal (2026-09-07). See `PROGRESS.md` for details.**

- [x] Confirmed the 4 datasets under "Banco Agrícola" on `datos.gob.do` are served via the
      CKAN Action API (public, no auth needed) and map 1:1 to the 4 staging tables in
      `transform_financial.sql`:

      | Dataset (CKAN `package_id`) | Maps to |
      |---|---|
      | `desembolsos-y-cobros-bagricola-2025-2026` (`3bc9bd7a-59e3-4535-8d4e-3494d85672d5`) | `staging_desembolsos` |
      | `cartera-de-prestamos` (`79edae9a-4b58-4746-b026-01a060f4a170`) | `staging_cartera` |
      | `areasfinanciadasporsucursales` (`102b343f-a4c4-4aba-b253-77bff9ee4000`) | `staging_areas` |
      | `montos-otorgados-por-destino` (`6064d590-5ebd-498c-9c20-9bedae54280c`) | `staging_destinos` |

      Each is tagged `"periodicidad": "Mensual"` and each resource has a stable `resource_id`
      whose `last_modified` timestamp changes when the government republishes the file.
- [x] Built a standalone acquisition layer, separate from `extract_financial.py`:
      `src/ingestion/ckan_client.py` (CKAN API + download + hashing + manifest I/O),
      `src/ingestion/datasets_config.py` (dataset definitions), and the CLI entry point
      `download_datos_gob.py` at the repo root (mirrors `main.py`'s convention).
- [x] Detects "is there something new" via `package_show` and compares `resources[].last_modified`
      + a `sha256` of the downloaded bytes against `data/raw/financial/manifest.json`; skips
      the download when unchanged.
- [x] **Format decision (changed from the original plan):** prefer **XLSX** first, fall back to
      **CSV** only if XLSX is missing or unusable; **ODS is never used**, per explicit instruction.
      In practice 2 of the 4 datasets (`areas`, `destinos`) currently fall back to CSV because
      their XLSX resources are published in "Strict OOXML", a variant `openpyxl`/`pandas` can't
      read — the CSV fallback (with the portal's actual `;`-delimited, Windows-1252-encoded
      format) covers it automatically.
- [x] Dataset `package_id`s + format preference live in `src/ingestion/datasets_config.py`,
      not hardcoded inline.
- [x] Saves the current file at the exact name `extract_financial.py` expects, plus an
      immutable timestamped snapshot in `data/raw/financial/history/`, and updates
      `manifest.json` (`last_modified`, `sha256`, `local_path`, `pulled_at`, `format`).
- [x] Retry/backoff on HTTP calls (`urllib3.Retry`, 3 attempts) and per-dataset error handling —
      one dataset failing doesn't stop the others; the script exits non-zero if any failed.
- [x] Validates the downloaded file: column count must match what `extract_financial.py`
      expects, **and** the resource's own URL must reference the expected dataset's filename.
      That second check caught a real portal bug during testing: `desembolsos`'s XLSX/ODS
      resources are mislabeled and actually point to the `cartera-de-prestamos` file — same
      column count, wrong data. The URL check rejects it and falls back to CSV (which is
      correctly labeled), rather than silently loading the wrong numbers.
- [x] Updated `extract_financial.py` to read either `.xlsx` or `.csv` per dataset (whichever
      the downloader produced), including the `;`-delimiter/Windows-1252 handling for CSV.
- [ ] Expose it as a CLI subcommand (`python main.py --refresh-data`) once the CLI split from
      item 3 exists, rather than a separate script to remember to run.
- [ ] Unit-test against a mocked `package_show` JSON response (no real network calls) —
      pairs with the "Testing" item above.

**Why it matters:** the Excel files currently in the repo were downloaded manually and are
already stale; the financial pipeline had no way to pull fresh data without someone doing it
by hand every month.

---
*Out of scope for now (parked, not forgotten): data quality validation layer, structured
logging, Dockerization, CI, dbt/Alembic migration of the SQL layer. Revisit after the 4
items above are done.*
