# Mini CDP

The purpose of this is to consolidate the  newsletter, the website, and the mobile app into one space so the Growth team can increase user engagement by looking people up, building segments, comparing channels, and asking questions. 

**Live:** https://mini-cdp-production.up.railway.app (login details sent with the submission)
**Webhook:** POST https://mini-cdp-production.up.railway.app/webhooks/app

## What it does

The lookup page allows you to see the newsletter info, app account and activity, and every site visit of a user on each of the platforms.

The segments page allows you to build a list of subscribers by source, status, opens and app use.

The channels page shows which acquistion channels bring readers who stay: retention rates per channel, with a comparison and small-sample warnings.

The assitant page allows you to prompt an AI agent with questions about the data and the answers come back as counts, tables, or segments, and the model never sees the subscriber emails. 

Webhooks recieves event from the mobile as they happen, handles any repeats, late arrivals, logins, or unknown users, and inserts it into the database without having to re-import. It only accepts events signed with the shared secret and shows up on the person's Lookup page and in segments, immediately.

## Run it locally
1. Clone, create a virtual environment, `python -m pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in the three values
3. Create your settings file from the template, then fill in the values:
```bash
   cp .env.example .env
```
   - `UI_PASSWORD`: any password; you'll log in with username `growth`
   - `WEBHOOK_SECRET`: any long random string, e.g. from
     `python -c "import secrets; print(secrets.token_hex(32))"`
   - `ANTHROPIC_API_KEY`: your own key from console.anthropic.com (needed only for the Assistant page)
3. `python -m uvicorn app.main:app --reload`, then open http://127.0.0.1:8000 in a regular browser
4. Tests: `python -m pytest`

## Sending a webhook event

Every request must be signed with the shared secret (`WEBHOOK_SECRET`), or it is refused.

### The quick way

`scripts/send_event.py` builds, signs and sends one event. It reads the secret from `.env`.

```bash
# An anonymous event from a new device
python scripts/send_event.py --event app_open --device-id d_demo1

# The device logs in: earlier anonymous events from d_demo1 attach to this user
python scripts/send_event.py --event login --device-id d_demo1 --user-id u_2b6447a3

# Send to the live site instead of your machine
python scripts/send_event.py --url https://mini-cdp-production.up.railway.app/webhooks/app \
    --event read_story --device-id d_demo1 --user-id u_2b6447a3 --story supreme-court-ruling-explained
```

Reuse an ID with `--event-id` to test duplicates.

### Signing your own requests

Send two headers:

- `X-Webhook-Timestamp`: the current Unix time in seconds
- `X-Webhook-Signature`: `sha256=` followed by the hex HMAC-SHA256 of `<timestamp>.<raw body>`, using the shared secret

Requests signed more than 5 minutes ago are rejected, which stops replays.

Example with `curl` and `openssl`:

```bash
BODY='{"event_id":"evt_test1","event":"app_open","user_id":null,"device_id":"d_test","timestamp":"2026-09-28T14:22:05Z","properties":{}}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')
curl -X POST https://mini-cdp-production.up.railway.app/webhooks/app \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

### Responses

| Response | Meaning |
|---|---|
| `200 {"status": "stored"}` | New event saved |
| `200 {"status": "duplicate"}` | Already received; nothing changed |
| `401` | Missing, wrong or expired signature |
| `422` | Signed correctly, but not a valid event (e.g. unknown `event` type) |
| `503` | `WEBHOOK_SECRET` is not set on the server |

## How it's built
Mini CDP is a Python app built with FastAPI (served by uvicorn), Jinja2 templates for the pages, SQLite for storage, the Anthropic API for the assistant, and pytest for tests, deployed on Railway. SQLite fits because the data is small and lives in one file, with no separate database server to run; on Railway it sits on a persistent volume. When the app starts, it loads the three CSVs, normalizes emails and sources, merges duplicate subscribers, links web visits and app accounts to one profile per person, and sets bad rows aside in a rejects table. The mobile app sends events to the webhook as they happen, and each verified event is stored in the same database and attached to the right profile. Every page queries the database on each request, and the assistant calls the same queries through tools, so everything shows live data.

| Table | One row is | Worth knowing |
|---|---|---|
| `profiles` | a person | The hub every other table points to. `email` is empty for app users we've never seen an email for. |
| `subscribers` | a profile's newsletter record | Duplicates already merged (earliest signup, latest open, unsubscribed wins). |
| `app_users` | an app account | Links `user_id` to a profile; includes unknown users created by the webhook. |
| `web_events` | a site visit | `profile_id` is empty for visitors who never gave an email. |
| `app_events` | an event from the mobile app | `event_id` is unique, so repeats are refused; the profile is empty until the device logs in. |
| `devices` | a device | Remembers which profile owns it, so anonymous and late events can be attached. |
| `rejected_rows` | a CSV row that couldn't be loaded | Keeps the original row, its file and the reason (currently the two invalid emails). |
## Keeping PII away from the AI model

The model runs on Anthropic's servers, so anything sent to it leaves this app.
The design keeps subscriber data out of everything that is sent:

1. **The model never queries data.** It only chooses a tool and its filters (`app/assistant.py`); the tools run here, on the server.
2. **Tools return counts and totals only.** Lists of people go straight from the database to the logged-in user's browser and are never sent (`run_tool` builds a separate result for each).
3. **Small counts are hidden.** Any count under 5 is reported as "fewer than 5" (`safe_count`).
4. **Typed PII is scrubbed.** Emails and IDs in the question are replaced before sending (`app/pii.py`, `scrub_text`).
5. **A final check.** Everything is inspected just before each call, and the request is refused if an email or ID slipped through (`assert_no_pii`).
6. **One exit point.** A single line in `answer_question` sends data to the model, so there is one place to audit.
7. **Visible proof.** Every answer has a "What the AI model saw" panel showing exactly what was sent and received.

## How I built it

### Plan
I used agile sprints instead of a waterfall plan. Each sprint ended with working, deployed code.

| Sprint | Dates | Delivered |
|---|---|---|
| 0 | Oct 2–4 | Repo, data profiling, first deploy |
| 1 | Oct 4–5 | Import: normalize, dedupe, link, with tests |
| 2 | Oct 5–6 | Lookup and segments, password protection |
| 3 | Oct 6–7 | Signed webhook, persistent storage |
| 4 | Oct 7–9 | AI assistant, channel report |
| Wrap | Oct 9–18 | README, self-audit, Loom |

### Where the plan slipped
Profiling took longer than planned because I found every data problem by hand. To make up time,
I changed how I worked: I made the decisions and wrote the rules, AI drafted the code, and I made
sure I could explain each piece before moving on.

### How I used AI
I used AI to draft code and to help with debugging. I made the design decisions, including the dedupe and merge rules, the 30-day cutoff for the channel report, and signatures instead of a shared token for the webhook (all in [DECISIONS.md](DECISIONS.md)). I checked the AI's work by comparing every count against my own profiling, explaining each piece back, and adding tests.

### Where AI was wrong
- **Data:** it suggested sampling 40 rows to look for whitespace, which missed a problem affecting 22 of about 3,000 rows. A direct check found them.
- **Deployment:** it guessed twice at why Railway was serving an old version. I found the real cause: Railway's GitHub app was authorized but not installed on the repo.
- **Instructions:** it told me to copy folders in and let them merge. On a Mac the folder replaced the existing one and deleted seven files, which I recovered with git.
- **Code:** the assistant passed every test against a stand-in AI service, then failed on its first real call because it dropped "thinking" blocks from the model's reply. Its error handling also hid the details, so I ran it from the terminal to find the cause.

AI was fast at building structure and wrong about details it couldn't see. Checking its output against real data and real errors caught every mistake. The full list is in [AI_LOG.md](AI_LOG.md).

## Known limitations and what I'd do next

**Data and identity**
- Web visits are linked by browser (`visitor_id`). A shared or public computer can attribute other people's visits to a subscriber, and visits from a second browser aren't linked at all.
- If several people use one phone, its anonymous app events go to whoever logged in first.
- An app user first seen through the webhook (no email) isn't merged with a CSV profile if their email turns up later.
- The CSV timestamps have no time zone, so UTC is assumed; webhook times are stored in UTC.
- "Today" is fixed at 2026-09-28, as the brief specifies.
- Names typed into the assistant reach the model. The scrubber removes emails, app, device, and visitor IDs because they follow a pattern, but names don't, so a question like “What has Julia Evans been reading?” is sent with the name in it. The risk is limited because the model has not tool that can look a person up: every tool returns counts or totals, so it can't find or reveal that person's data. A fix would be to build a list of known names from subscriber emails and scrub those too, though names that are also common words (Hope, Joy, Grace) would cause false matches.

**Scale and operations**
- SQLite is a single file, which suits this data size but not many simultaneous writers.
- The import reads whole CSV files into memory.
- There's no rate limiting on the webhook or the assistant.
- One shared login for the whole UI; there are no individual user accounts or audit trail of who viewed what.

**Features**
- Segments show the first 200 rows and can't be exported yet.
- Channel differences are a few percentage points on synthetic data: a signal, not a verdict.
- The assistant answers one question at a time and doesn't remember earlier questions.

## What I'd do next

In priority order:

1. **Watch the Growth team use it.** Sit with two or three teammates while they try to answer real questions, and note where they get stuck or what they can't ask. I'd also review the questions asked of the assistant (the text is already scrubbed of emails). This comes first because it decides which features are worth building next.
2. **Run it on real, full-size data.** Load a real export and look for cases the import doesn't handle yet: new kinds of messy emails, missing columns, unexpected source names. Then time the import and the pages. Reading whole files into memory and SQLite's single writer are the first things likely to slow down or break.
3. **Export segments to the newsletter tool.** A segment the team can't send to is only a report. A CSV download (or a direct beehiiv integration) turns the CDP into something they act on.
4. **Rate limiting on the webhook and the assistant.** Protects against floods of events and runaway AI costs.
5. **Merge app users whose email shows up later.** Today a webhook-only profile and a CSV profile for the same person stay separate.
6. **Send-time optimization, at the audience level.** Pick the send time from when readers are actually active. I'd stop short of per-person timing, which starts to feel intrusive. The synthetic data has no daily pattern, so this needs real data first.