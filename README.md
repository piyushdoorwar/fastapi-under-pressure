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

## Run it locally

Python 3.13 and PostgreSQL 16 or later.

    python -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"
    createdb secondloop && createdb secondloop_test
    make seed
    make partner     # terminal 1
    make mailer      # terminal 2 (from chapter 8)
    make api         # terminal 3
    make load        # terminal 4

Or with Docker: `docker compose up --build`, then
`docker compose exec api python -m secondloop.seed`.

MIT licence.
