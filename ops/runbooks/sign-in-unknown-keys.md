# Sign-in: unknown signing keys

From chapter 15.

More than 20 tokens in 5 minutes were signed with a key
the API doesn't have.

Check: `idp_keys_fetched` and `idp_keys_fetch_failed` log
lines; the identity provider's JWKS and status page. A
rotation is picked up within 30 s, so a burst that lasts
longer means the API can't fetch the keys, or the tokens
are forged.

Act: if fetches are failing, fix the route to the
provider. Restarting the API only helps if the provider
can be reached.
