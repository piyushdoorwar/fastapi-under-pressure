# fastapi-under-pressure

Companion code for *FastAPI Under Pressure* by Piyush Doorwar.

The repo holds SecondLoop's shop API, a fake ParcelPath
shipping partner and the tools used in the book. Each
chapter has a git tag: check out the tag to get the code
exactly as the chapter shows it.

| Tag | State |
| --- | --- |
| `ch01` | The service as the book opens; checkout times out under load |
| `ch02` | Logs, metrics and the event-loop lag monitor added |
| `ch03-broken` | Same as `ch02`, plus the chapter 3 tests (one fails) |
| `ch03-fixed` | ParcelPath called through a shared async client; all tests pass |
| `ch04-broken` | Pool metrics added, plus the chapter 4 tests (two fail) |
| `ch04-fixed` | Short transaction before the partner call; full pool fails fast with 503 |
| `ch05-broken` | 2,000-product catalogue with warehouse stock; query counter; chapter 5 tests (two fail) |
| `ch05-fixed` | Stock loaded with `selectinload`; keyset pagination |
| `ch06-broken` | Fake ParcelPath can be made slow or failing at runtime; chapter 6 tests (four fail) |
| `ch06-fixed` | Time budget, fallback shipping estimate and circuit breaker for ParcelPath |
| `ch07-broken` | Product search with an in-memory cache; memory tools; chapter 7 tests (three fail) |
| `ch07-fixed` | Search cache keyed on the query, with a size limit and a time limit |
| `ch08-broken` | Orders with a confirmation email; fake email provider; chapter 8 tests (two fail) |
| `ch08-fixed` | Explicit transaction, stock check, email only after the commit |
| `ch09-broken` | Concurrent order tests and `tools/race.py` (three fail) |
| `ch09-fixed` | Stock taken with a conditional update, rows locked in SKU order |
| `ch10-broken` | Idempotency tests, slow mode for the fake email provider, `tools/storefront.py` (three fail) |
| `ch10-fixed` | `Idempotency-Key` for `POST /orders`, claimed in the order transaction |
| `ch11-broken` | ParcelPath v1.4 mode in the fake, rate parsing tests (six fail) |
| `ch11-fixed` | Complete rate models, money as `Decimal`, unreadable rates fall back to the estimate |
| `ch12-broken` | Confirmation email in `BackgroundTasks`; outbox tests and `tools/stop.py` (four fail) |
| `ch12-fixed` | Outbox written with the order; `secondloop.worker` sends it |

## Run it locally

Python 3.13 and PostgreSQL 16 or later.

    python -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"
    createdb secondloop && createdb secondloop_test
    make seed
    make partner     # terminal 1
    make mailer      # terminal 2 (from chapter 8)
    make api         # terminal 3
    make worker      # terminal 4 (from chapter 12)
    make load        # terminal 5

Moving back to an earlier tag after a later one? The
later tags add tables that the earlier seed doesn't
know about. Reset the database first:

    psql secondloop -c "drop schema public cascade; create schema public"

Or with Docker: `docker compose up --build`, then
`docker compose exec api python -m secondloop.seed`.

MIT licence.
