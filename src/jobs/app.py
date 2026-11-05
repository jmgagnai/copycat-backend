import procrastinate
from procrastinate import PsycopgConnector

from settings import settings

job_app = procrastinate.App(
    connector=PsycopgConnector(conninfo=settings.postgres_dsn),
    import_paths=["jobs.tasks"],
)
