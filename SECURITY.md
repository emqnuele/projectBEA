# Security

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:
[Report a vulnerability](https://github.com/emqnuele/projectBEA/security/advisories/new).

Include what you ran, what you got, and what an attacker could do with it. You
will get a reply within a few days. This is a side project, not a vendor with
an on-call rotation, and it is better to say so than to promise an SLA nobody
is holding.

## What is in scope

The web API and the control room, the Discord/Telegram/Twitch/Minecraft
surfaces, the setup wizard, the Docker image, and anything that lets input from
one of those reach the filesystem, the database or a shell.

## What is already known, and is not a vulnerability

**The web API has no authentication.** This is by design, and it is why the
server binds to `127.0.0.1` unless `--host` says otherwise and why
`docker-compose.yml` publishes to `127.0.0.1:8000` rather than `0.0.0.0`.
Putting it on a public address as it stands exposes every endpoint, including
the ones that write to her memory and change her configuration. Reports that
amount to "the API is open if you expose it" are documented behaviour.

If you have found a way to reach the API *without* exposing it (an SSRF from a
skill, a CSRF from a page the owner visits, a WebSocket that ignores its
origin), that is in scope and worth reporting.

**She runs on your keys.** Model API keys live in `.env` and are read at
startup. A skill or a prompt that convinces her to reveal them is in scope. Keys
sitting in a file on your own machine are not.

## Supported versions

The latest commit on `main`. There is no backport branch.
