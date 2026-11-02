from sqlalchemy.orm import DeclarativeBase

# Only users and notebooks are mapped;
# every other table is read and written with text()


class Base(DeclarativeBase):
    def __repr__(self) -> str:
        cols = ", ".join(
            f"{c.key}={getattr(self, c.key)!r}"
            for c in self.__table__.columns
            if c.key not in ("search_vector", "embedding", "password_hash")
        )
        return f"<{self.__class__.__name__} {cols}>"
