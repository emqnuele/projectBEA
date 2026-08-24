# Donations

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

A donation is the one input that always deserves a reaction. Any provider that
can call a webhook — StreamElements, Ko-fi, Streamlabs — posts to
`POST /webhook/donation`, and it becomes a perception, a roster entry, a person
card and a "right now" fact in one pass.

**File:** `src/core/skills/donation/surface.py`

---

## Why it always gets through

The donor's `Author` carries the amount in `extra`:

```python
Author(platform="donation", native_id=donor_id,
       extra={"amount": 25.0, "currency": "EUR", "message": "..."})
```

`is_addressed()` reads that and returns `addressed:donation`, which is an
**unconditional react** — past the cooldown, past quiet hours, no score
computed. Cheers from [Twitch](twitch.md) carry `bits` and take the same path.

---

## What one donation writes

```
receive()
    ├─ de-duplicate on event_id           providers retry webhooks
    ├─ roster.record(donation=amount)     the tally
    ├─ people.create_from_entry(...)      promoted immediately, not by the dreamer
    ├─ people.add_fact("donated 25 EUR")  and their message, if any
    ├─ hot.add("X just donated 25 EUR")   a fact she can mention for a while
    └─ bus.put(Perception(salience=1.0, conversation_key="stage"))
```

Money is the strongest promotion trigger there is: a donor gets a person card
**immediately** rather than waiting for the nightly dreamer, so the very next
thing she says already knows who they are.

De-duplication matters more than it looks: providers retry, and without
`event_id` tracking a retry would be a second donation, a second thank-you and a
wrong total. Seen ids are kept for 24 hours.

---

## Tools

| Tool | Effect |
|---|---|
| `recall_donors(limit)` | who has given her money, and how much |

---

## The endpoint

```
POST /webhook/donation?secret=<shared secret>
```

```json
{
  "name": "marco",
  "amount": 5.0,
  "currency": "EUR",
  "message": "ciao bea",
  "platform": "kofi",
  "donorId": "optional stable id",
  "eventId": "optional id used to ignore retries"
}
```

Returns `{"status": "perceived"}`, or `{"status": "duplicate"}` when `eventId`
has already been handled. `503` if the skill is off, `403` on a bad secret.

**Anyone who can reach this endpoint can fake a donation.** A shared secret is
checked whenever one is configured; with none set the endpoint is open, which is
acceptable on loopback and nowhere else. Set `DONATION_SECRET` before exposing
the server.

---

## Configuration

```json
"donations": {
  "enabled": false,
  "secret": ""
}
```

| Key | Description |
|---|---|
| `secret` | Shared secret checked against the `?secret=` query param. Prefer the `DONATION_SECRET` env var |
