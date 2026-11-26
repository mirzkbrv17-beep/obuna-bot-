-- ABU SUB BOT: boshlang'ich sxema

CREATE TABLE users (
    id          BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT NOT NULL DEFAULT '',
    balance     BIGINT NOT NULL DEFAULT 0,
    is_vip      BOOLEAN NOT NULL DEFAULT FALSE,
    is_banned   BOOLEAN NOT NULL DEFAULT FALSE,
    referrer_id BIGINT REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT no_self_referrer CHECK (referrer_id IS NULL OR referrer_id <> id)
);
CREATE INDEX users_username_idx ON users (lower(username));

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE emoji (
    key       TEXT PRIMARY KEY,
    custom_id TEXT NOT NULL
);

CREATE TABLE orders (
    id             BIGSERIAL PRIMARY KEY,
    owner_id       BIGINT NOT NULL REFERENCES users(id),
    chat_id        BIGINT NOT NULL,
    chat_title     TEXT NOT NULL,
    chat_username  TEXT,
    chat_type      TEXT NOT NULL,
    invite_link    TEXT NOT NULL,
    quantity       INT NOT NULL CHECK (quantity > 0),
    done_count     INT NOT NULL DEFAULT 0 CHECK (done_count >= 0),
    price_per_sub  INT NOT NULL,
    cost           BIGINT NOT NULL DEFAULT 0,
    is_free        BOOLEAN NOT NULL DEFAULT FALSE,
    status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    post_chat_id   BIGINT,
    post_message_id BIGINT,
    post_has_photo BOOLEAN NOT NULL DEFAULT FALSE,
    post_dirty     BOOLEAN NOT NULL DEFAULT FALSE,
    post_deleted   BOOLEAN NOT NULL DEFAULT FALSE,
    post_attempts  INT NOT NULL DEFAULT 0,
    owner_notified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    CONSTRAINT done_le_quantity CHECK (done_count <= quantity)
);
CREATE UNIQUE INDEX one_active_order_per_chat ON orders (chat_id) WHERE status = 'active';
CREATE INDEX orders_owner_idx ON orders (owner_id, id DESC);
CREATE INDEX orders_post_idx ON orders (status, post_deleted);

CREATE TABLE earnings (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    chat_id         BIGINT NOT NULL,
    order_id        BIGINT NOT NULL REFERENCES orders(id),
    amount          INT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT earnings_user_chat_unique UNIQUE (user_id, chat_id)
);
CREATE INDEX earnings_check_idx ON earnings (status, last_checked_at);

CREATE TABLE join_events (
    chat_id   BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE transactions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id),
    amount        BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    kind          TEXT NOT NULL,
    ref_id        BIGINT,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX transactions_user_idx ON transactions (user_id, id DESC);

CREATE TABLE referrals (
    invited_id  BIGINT PRIMARY KEY REFERENCES users(id),
    referrer_id BIGINT NOT NULL REFERENCES users(id),
    rewarded    BOOLEAN NOT NULL DEFAULT FALSE,
    rewarded_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT referral_not_self CHECK (invited_id <> referrer_id)
);
CREATE INDEX referrals_referrer_idx ON referrals (referrer_id);

CREATE TABLE admin_logs (
    id         BIGSERIAL PRIMARY KEY,
    admin_id   BIGINT NOT NULL,
    action     TEXT NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    details    TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
