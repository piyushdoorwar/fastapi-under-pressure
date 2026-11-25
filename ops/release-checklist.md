# Release checklist

Before a change goes to production. Each line points to
the chapter whose incident it prevents.

## Code

- [ ] No blocking call inside `async def` (3).
- [ ] No connection held across a call to a partner (4).
- [ ] New relationships are `lazy="raise_on_sql"`; new list
      endpoints are paginated (5).
- [ ] Every outbound call has a timeout inside a budget (6).
- [ ] Every cache has a size limit and an expiry (7).
- [ ] You can point to the line where each write commits,
      and nothing irreversible happens before it (8).
- [ ] No read-then-write of a counter in Python; the
      arithmetic happens in SQL (9).
- [ ] Endpoints that create things accept an
      Idempotency-Key (10).
- [ ] Models that parse partner data have no defaults on
      fields we use; money is Decimal (11).
- [ ] Nothing a customer was promised is in
      BackgroundTasks (12).
- [ ] Worker calls to the outside send an idempotency key;
      failures are sorted into permanent and temporary (13).
- [ ] Anything fetched from another service has a lifetime
      and survives a failed refresh (15).

## Database

- [ ] Migrations are additive (expand), or the code that
      needed the old shape is already gone (contract) (14).

## API contract

- [ ] Response changes are additive; no field changes
      meaning without a new name.
- [ ] Requests that become stricter (a required header, a
      tighter email check) are announced to clients first.

## Before deploy

- [ ] `make test` passes.
- [ ] `make drills` passes against staging.
- [ ] Every new alert has a runbook in `ops/runbooks/`.
