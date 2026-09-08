"""Small shared repository helpers; no generic repository abstraction."""

from sqlalchemy.exc import IntegrityError

from app.application.errors import PersistenceIntegrityError


def require_session(session):
    if session is None or not hasattr(session, "execute") or not hasattr(session, "flush"):
        raise TypeError("session must be an AsyncSession-like object")
    return session


def map_integrity(error: IntegrityError, message: str) -> PersistenceIntegrityError:
    return PersistenceIntegrityError(message)


def is_named_constraint(error: IntegrityError, name: str) -> bool:
    text = str(error)
    orig = getattr(error, "orig", None)
    constraint_name = getattr(orig, "constraint_name", None)
    return constraint_name == name or name in text
