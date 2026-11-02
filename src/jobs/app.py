import procrastinate
from procrastinate import PsycopgConnector

from settings import settings

# The plain postgresql:// DSN: procrastinate speaks psycopg, not asyncpg. This module imports no
# Stage code, so the CLI (`procrastinate --app jobs.app.job_app ...`) can load it cheaply;
# procrastinate imports jobs.tasks itself through import_paths when the worker starts.
job_app = procrastinate.App(
    connector=PsycopgConnector(conninfo=settings.postgres_dsn),
    import_paths=["jobs.tasks"],
)
