import pathlib
from sqlalchemy import create_engine, text


def engine_for(url):
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=2,
                         connect_args={'connect_timeout': 10}, hide_parameters=True)


def migrate(engine):
    folder = pathlib.Path(__file__).resolve().parent.parent / 'migrations'
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(185115001)'))
        for path in sorted(folder.glob('*.sql')):
            connection.connection.driver_connection.execute(path.read_text())


def audit(conn, owner, action, resource=None, correlation=None):
    conn.execute(text('INSERT INTO audit_events(owner_id,action,resource_id,correlation_id) VALUES (:o,:a,:r,:c)'),
                 {'o': owner, 'a': action, 'r': resource, 'c': correlation})

