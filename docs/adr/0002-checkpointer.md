# ADR 0002: SQLite checkpointer + store instead of Postgres for this build
Status: accepted for the single-machine build. `AsyncSqliteSaver` / `SqliteStore` give the same
durability semantics (crash-and-resume verified across processes). Postgres (`langgraph-checkpoint
-postgres`, `AsyncPostgresSaver`) is a drop-in swap in `agent/runner.py` / `apps/api/service.py`
and is what the compose file provisions for deployment. Trade-off: no concurrent multi-writer
scaling on SQLite.
