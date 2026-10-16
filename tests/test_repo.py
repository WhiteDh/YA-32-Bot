"""Repository-wide invariants: versions agree, migrations match the models."""

from __future__ import annotations

import re
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import ya32_bot
from ya32_bot.config import Settings
from ya32_bot.db.models import Base
from ya32_bot.db.session import _upgrade

ROOT = Path(__file__).resolve().parents[1]


def test_versions_agree():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert pyproject is not None
    assert {version, pyproject.group(1), Settings().version, ya32_bot.__version__} == {version}


def test_migrations_match_models(tmp_path: Path):
    path = (tmp_path / "m.db").as_posix()
    _upgrade(f"sqlite+aiosqlite:///{path}")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"models changed without a migration: {diff}"
