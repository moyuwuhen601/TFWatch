from alembic import context

from tfwatch import models
from tfwatch.config import Config
from tfwatch.db import database


def run():
    url = Config().database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=models.Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = database(url).kw["bind"]
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=models.Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run()
