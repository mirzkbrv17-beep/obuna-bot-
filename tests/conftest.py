import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config  # noqa: E402
from database import Database  # noqa: E402
from services.emoji import emoji  # noqa: E402
from services.settings import settings  # noqa: E402

TEST_DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def cfg():
    return Config(bot_token="1:x", admin_ids=(1000,), database_url=TEST_DSN or "")


@pytest.fixture
async def db(cfg):
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL o'rnatilmagan (PostgreSQL kerak)")
    d = Database(TEST_DSN, max_size=20)
    await d.connect()
    await d.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await d.migrate()
    settings.bind(d, cfg)
    await settings.load()
    emoji.ids, emoji.enabled = {}, True
    yield d
    await d.close()


async def make_user(db, uid, balance=0, vip=False):
    await db.execute(
        "INSERT INTO users(id, username, full_name, balance, is_vip) VALUES($1,$2,$3,$4,$5) "
        "ON CONFLICT (id) DO NOTHING", uid, f"u{uid}", f"User {uid}", balance, vip)
