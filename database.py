from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "sqlite:///./licenses.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
