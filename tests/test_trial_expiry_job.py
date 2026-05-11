from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import sessionmaker

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.user import User


def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@pytest.fixture
def db_session():
    _coerce_postgres_types()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def test_expired_trials_get_downgraded(db_session):
    from backend.app.backstage.scheduler import _run_trial_expiry_sweep

    user = User(
        id=uuid.uuid4(),
        email="expired@example.com",
        subscription_status="trialing",
        access_tier="pro",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(user)
    db_session.commit()

    count = _run_trial_expiry_sweep(db_session)
    db_session.commit()

    db_session.refresh(user)
    assert user.subscription_status == "expired"
    assert user.access_tier == "free"
    assert count == 1


def test_active_trials_not_touched(db_session):
    from backend.app.backstage.scheduler import _run_trial_expiry_sweep

    user = User(
        id=uuid.uuid4(),
        email="active_trial@example.com",
        subscription_status="trialing",
        access_tier="pro",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(user)
    db_session.commit()

    count = _run_trial_expiry_sweep(db_session)
    db_session.commit()

    db_session.refresh(user)
    assert user.subscription_status == "trialing"
    assert count == 0
