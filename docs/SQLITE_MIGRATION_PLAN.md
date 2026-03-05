# Examination: Moving Everything to SQLite (No Postgres)

## 1. App DB (orchestrator state: requests, plans, step_results)

| Location | Current | Change |
|----------|---------|--------|
| **src/data_access/app_db/backends.py** | Chooses Postgres vs SQLite from env; uses `open_postgres_connection` when not SQLite. | Use SQLite only. Remove Postgres branch and `open_postgres_connection` import. Require `SQLITE_APP_PATH` or `DATABASE_URL=sqlite://...`. |
| **src/data_access/app_db/postgres_conn.py** | asyncpg wrapper for app DB. | **Delete** (no longer used). |
| **src/data_access/app_db/sqlite_conn.py** | SQLite backend. | Keep as-is (already used). |
| **src/orchestrator/session.py** | Uses abstract connection (works with both). | No change. |
| **src/orchestrator/main.py** | Calls `open_app_db_connection(env)`. | No change. |
| **scripts/migrate.py** | Runs Postgres or SQLite migration based on env. | Run **only** SQLite migration. Require `SQLITE_APP_PATH` or `DATABASE_URL`. Remove `run_migration_postgres` and asyncpg. |

## 2. Relational “connected” DBs (e.g. manufacturing – used by `query_facts` tool)

| Location | Current | Change |
|----------|---------|--------|
| **src/data_access/factory.py** | For `rel_db` + `engine: "postgres"` calls `create_pg_engine(url)` and stores Postgres URL in `clients[id]`. | Support only `engine: "sqlite"`. Read path from env (`connection_id`), store path in `clients[id]`. Remove import and use of `create_pg_engine`. |
| **src/data_access/relational/postgres.py** | SQLAlchemy async Postgres engine/session. | No longer used by factory. **Leave file** for now (or delete and fix `relational/__init__.py`). |
| **src/tools/registry.py** | Picks first client that is `str` and `startswith("postgresql")` and passes to `create_query_facts_tool(pg_url)`. | Pick first non-`app_db` client that is a string (SQLite path). Pass path to tool. |
| **src/tools/rel_db/query.py** | Uses **asyncpg** to run read-only SQL. | Use **aiosqlite** only. Accept `db_path: str` (path to .sqlite file), run SELECT via aiosqlite, return rows. |

## 3. Config and domain JSON

| Location | Current | Change |
|----------|---------|--------|
| **src/core/config/models.py** | `DataSourceConfig.engine`: `"postgres" \| "chroma"`. `SessionStoreConfig.type`: `"postgres"`. | `engine`: `"sqlite" \| "chroma"`. `session_store.type`: `"sqlite"`. |
| **config/domains/manufacturing.json** | `data_sources`: app_db and manufacturing_db use `engine: "postgres"`, `connection_id: "POSTGRES_APP_URL"` / `"POSTGRES_MANUFACTURING_URL"`. `session_store`: `type: "postgres"`, `connection_id: "POSTGRES_APP_URL"`. | Use `engine: "sqlite"`, `connection_id: "SQLITE_APP_PATH"` and `"SQLITE_MANUFACTURING_PATH"` (or one path). `session_store`: `type: "sqlite"`, `connection_id: "SQLITE_APP_PATH"`. |

## 4. Env and docs

| Location | Current | Change |
|----------|---------|--------|
| **.env.example** | `POSTGRES_APP_URL`, `POSTGRES_MANUFACTURING_URL`. | Remove Postgres vars. Use `SQLITE_APP_PATH`, `SQLITE_MANUFACTURING_PATH` (or single path). |
| **config/env/.env.example** | Same. | Same. |
| **README.md** | References Postgres setup, `POSTGRES_APP_URL`, migration, architecture. | Replace with SQLite-only setup, env vars, and architecture. |

## 5. Dependencies

| Location | Current | Change |
|----------|---------|--------|
| **requirements.txt** | `asyncpg>=0.29.0`, `aiosqlite>=0.20.0`. | **Remove** `asyncpg`. Keep `aiosqlite`. |
| **pyproject.toml** | Same. | Same. |

## 6. Migrations and misc

| Location | Current | Change |
|----------|---------|--------|
| **migrations/versions/001_initial_sqlite.sql** | SQLite schema. | The only migration; run via `scripts/migrate.py`. |
| **migrations/env.py** | Comment says POSTGRES_APP_URL. | Update comment to SQLite. |

## 7. Optional cleanup

- **src/data_access/relational/__init__.py**: Exports from `postgres`. If we delete `postgres.py`, this breaks. Either keep `postgres.py` unused or add a minimal `sqlite_engine.py` and export that (only if something needs SQLAlchemy for SQLite). For “everything SQLite” we do **not** need SQLAlchemy for the connected DB – only aiosqlite in `query.py`. So: leave `relational/postgres.py` in place but unused, or delete it and make `relational/__init__.py` export empty/dummy so no code imports from it. Factory will no longer import from `relational.postgres`.

---

## Summary of file-level actions

| Action | Files |
|--------|--------|
| **Edit** | `backends.py`, `migrate.py`, `factory.py`, `registry.py`, `query.py`, `config/models.py`, `manufacturing.json`, `.env.example`, `config/env/.env.example`, `README.md`, `requirements.txt`, `pyproject.toml`, `migrations/env.py`, `main.py` (comment only). |
| **Delete** | `src/data_access/app_db/postgres_conn.py`. |
| **Leave unchanged** | `session.py`, `sqlite_conn.py`, `001_initial_sqlite.sql`. |

Implementing these changes next.
