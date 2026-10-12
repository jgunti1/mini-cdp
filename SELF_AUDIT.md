# Self-audit

Raw output of the assessment's audit prompt, unedited.
Run on 2026-10-12 in a fresh Claude session against commit `a0cdd00`.

---
# Self Audit: mini-cdp

Audit date: 2026-10-12. Based on a full read of `app/`, `tests/`, `scripts/`, `notebooks/`, the three docs, and all 26 commits. The test suite was run: **43 passed in 0.13s**.

## 1. Architecture

- **Stack:** Python with FastAPI, served by uvicorn. Pages are server-side Jinja2 templates. Deployed on Railway.
- **Store:** a single SQLite file (`app/db.py:5`, default `cdp.db`). `profiles` is the hub table, and `subscribers`, `app_users`, `web_events`, `devices` and `app_events` all point to it (`db.py:7-57`).
- **CSV to store:** at startup, `lifespan` runs `run_import()` only if `profiles` is empty (`main.py:26-34`). The import normalizes, merges and links the three CSVs into those tables.
- **Webhook to store:** app events come in through `POST /webhooks/app` and are written by `process_event` (`webhook.py:70-117`).
- **Store to UI:** four GET pages, each behind Basic auth, query SQLite on every request. The assistant calls the same query functions as tools (`assistant.py:104-171`).

## 2. Normalization

There is one shared function, `normalize_email` (`app/normalize.py:9-16`), which strips, lowercases and checks a regex. Production code calls it from these places:

- `importer.py:59`: subscribers
- `importer.py:96`: app users
- `importer.py:118`: web events
- `queries.py:7`: Lookup search

`normalize_source` (`normalize.py:19-26`) is used at `importer.py:67`, `importer.py:131` and `segments.py:36`.

The only duplicated logic is in `notebooks/profile.py:37,61,74`, which re-implements strip and lowercase in pandas. That is profiling code, not the pipeline. One small inconsistency: `pii.py:11` uses a different, looser email regex to detect emails in free text.

## 3. Dedupe and linking

**Subscriber dedupe:** two rows are the same subscriber when their emails match exactly after `strip().lower()` and the regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`. Rows are merged in `merge_subscriber` (`importer.py:38-46`):

- The earliest `signup_date` wins, and its `acquisition_source` comes with it.
- The latest `last_open_date` wins.
- If any row says `unsubscribed`, the status is unsubscribed.

**Web linking:** a two-pass rule (`importer.py:115-120`). The first valid email seen for a `visitor_id`, in file order, assigns that visitor to a profile, and every row for that visitor gets that profile.

**App linking:** `app_users.user_id` is joined to the profile with the same normalized email (`importer.py:96-105`). On the webhook, a device belongs to the first user_id it is seen with (`webhook.py:82-93`).

**Edge cases it misses:**

- **Gmail aliases:** dots and `+tags` are not collapsed, so `j.doe+news@gmail.com` and `jdoe@gmail.com` stay two people.
- **Blank `signup_date`:** it is only `.strip()`ed and never validated. In a string comparison `""` sorts earliest, so a blank date would win the merge and carry its source with it (`importer.py:40,65`).
- **Statuses:** they are not validated. Anything other than `unsubscribed` (`bounced`, `cleaned`, a typo) is kept as-is, and segments that filter on `status='active'` silently drop it.
- **Unsubscribe dates:** the merge has none, so a later re-subscribe can never win.
- **Web visitors with two emails:** a shared computer goes to whichever email comes first in the file, not first in time. `rows` is never sorted by timestamp (`importer.py:113,119`).
- **Invalid web emails:** they are silently left unlinked rather than sent to `rejected_rows`.
- **Duplicate app `user_id`:** with a different email, the second row is silently dropped by `INSERT OR IGNORE` (`importer.py:103`), yet `counts["loaded"]` still goes up (`importer.py:106`). The import report overstates loads.
- **Webhook-first users:** a user created by the webhook has a NULL email. If the CSV later has their email, the same `INSERT OR IGNORE` keeps the emailless profile forever. The README admits this (line 148).
- **Shared devices:** the device mapping is never updated (`webhook.py:82`). If a second person logs in on the same phone, every later anonymous event still goes to the first person.

## 4. Webhook

- **Deduplication:** `SELECT` on `event_id` and return `"duplicate"` (`webhook.py:73-75`), backed by the primary key (`db.py:44`). For a race between two copies, `main.py:152-158` rolls back and re-checks. Nothing compares content, so a different payload that reuses an `event_id` is silently dropped as a "duplicate".
- **Out-of-order events:** there is no reordering. The event's own timestamp is converted to UTC and stored (`webhook.py:98-111`), and the Lookup page sorts by it (`queries.py:46-49`). Naive timestamps are assumed to be UTC. Future-dated timestamps are accepted without question.
- **Login after anonymous events:** any event with a `user_id` (not only `event == "login"`) on a device not seen before does two things. It inserts a `devices` row, and it runs `UPDATE app_events SET profile_id=? WHERE device_id=? AND user_id IS NULL AND profile_id IS NULL` (`webhook.py:82-93`). Anonymous events that arrive late are then attached through the device lookup (`webhook.py:96`). Time is never checked: events from months before the login, or after a logout, go to the same person.
- **Unknown `user_id`:** creates a new `profiles` row with a NULL email and an `app_users` row with a NULL `created_at` (`webhook.py:57-67`). There is no cap, so any valid signer can create unlimited profiles.
- **Authentication:** HMAC-SHA256 over `"<timestamp>.<body>"`, with a ±300s window and `compare_digest` (`webhook.py:28-48`). It fails closed when no secret is set (`main.py:123-125`).
  - The 64KB size check runs after `await request.body()` has already read the whole body into memory (`main.py:127-129`).
  - A request can be replayed inside the 5-minute window. Only the `event_id` dedupe stops it.
  - The README describes events as coming "from the mobile app". If the app signs requests on the device, the shared secret ships inside every install and can be extracted.

## 5. PII and the assistant

**Answer: Yes.** No email or raw subscriber row from the database can reach the model in the current code. A name, or an email written in a form the regex doesn't catch, can reach the model if the user types it.

The question goes out after a regex scrub:

```python
cleaned, removed = scrub_text(question.strip())          # assistant.py:187
messages = [{"role": "user", "content": cleaned}]         # :189
```

`scrub_text` removes only emails and `u_/d_/v_/evt_` IDs (`pii.py:11-13,20-24`). A name like "Julia Evans" passes through, and so does `julia dot evans at gmail`. The README admits the name case (line 151). The same input then gets past `assert_no_pii` (`pii.py:27-31`), because that check uses the same two regexes.

The system prompt includes acquisition source names from the database (`assistant.py:92,188`):

```python
f"Acquisition sources: {', '.join(sources)}.\n"
```

Tool results are built by hand from counts:

```python
for_model = {"count": safe_count(len(rows)), "filters_used": filters}             # :115
for_model = {"rows": [{"label": row["label"], "subscribers": safe_count(...)}]}   # :134
for_model = {"rules": insights.CHANNEL_RULES, "channels": report}                 # :146
for_model = {"listed": len(rows), "scoring_rule": insights.ENGAGEMENT_RULE}       # :162
```

Rows containing emails only ever go into `for_page`, which goes to the browser.

The single send happens at `assistant.py:206-211`:

```python
assert_no_pii({"system": system, "messages": messages})
response = client.messages.create(model=MODEL, ..., system=system, tools=TOOLS, messages=messages)
```

Caveats:

- **Responses:** the model's reply is scrubbed for emails and IDs only (`:236`). A typed name the model echoes back comes through.
- **Small-count suppression is inconsistent:** `channel_report` sends exact counts and percentages with no `safe_count` (`:146`). The `signup_from`/`signup_to` filters allow single-day ranges, so counts can be narrowed down and differenced.
- **Logs, not the model:** both forms use GET (`index.html:20`, `assistant.html:24`). The unscrubbed question, with any email in it, lands in server logs and browser history.

## 6. Tests

There are 43 tests in 6 files, and all pass:

- `tests/test_normalize.py`: 12, parametrized
- `tests/test_webhook.py`: 11
- `tests/test_assistant.py`: 8, using a `FakeClient` stub
- `tests/test_segments.py`: 6
- `tests/test_importer.py`: 4, `merge_subscriber` only
- `tests/test_channels.py`: 2

**Not covered:**

- Any HTTP route: there is no `TestClient`, so auth, the 401/413/422/503 paths and the IntegrityError branch are untested.
- The import itself: `run_import`, `load_subscribers`, `load_app_users`, `load_web_events`. The documented counts (2,900 subscribers, 8,441 linked visits) are not asserted anywhere.
- `queries.lookup_profile`, plus `insights.breakdown`, `first_pages` and `most_engaged`.
- Device re-login, and an `event_id` reused with different content.

## 7. Three most serious security issues

1. **One shared password guards every subscriber email.** `auth.py:13-14` uses a single Basic-auth credential with a default username of `growth`. There is no rate limiting or lockout (README line 157), no per-user accounts and no audit trail. Anyone with that password can pull every email through the 200-row segment tables (`segments.html:65`, `assistant.py:122`). Because the forms use GET, searched emails and questions end up in Railway logs and browser history.
2. **The webhook trusts whoever holds the secret to claim devices and create people.** A signed event with any `user_id` on a device not seen before permanently claims that `device_id`, plus all of its past and future anonymous events (`webhook.py:82-96`). Unknown `user_id`s create unlimited profiles (`:62`). There is no rate limit, and the body is read in full before the size check (`main.py:127`). If the secret lives in the mobile client, all of this is open to anyone.
3. **PII reaches a third party, and the assistant has no cost controls.** Typed names go to Anthropic (section 5). Any logged-in user can trigger up to 5 model calls per request with no rate limit. Raw exception text is shown on the page (`main.py:111`).

Also worth checking: real-looking PII CSVs, about 3,900 email rows, are committed to git (`data/*.csv` in `git ls-files`). That matters if the GitHub repo is public; its visibility was not confirmed in this audit. `.env` and `cdp.db` are correctly untracked, and neither appears anywhere in git history.

## 8. Unfinished, hardcoded or mocked

There are no `TODO` or `FIXME` markers in the code.

**Hardcoded:**

- `TODAY = "2026-09-28"` (`config.py:4`). Live webhook events are compared against this frozen date, so "used recently" (`segments.py:64-70`) counts anything after Sept 21, including future dates.
- Only one source alias, `twitter→x` (`normalize.py:6`).
- Model, rounds and suppression: `MODEL` default `claude-haiku-5-5`, `MAX_ROUNDS=5` and `SMALL_COUNT=5` (`assistant.py:20-22`).
- `SMALL_SAMPLE=200` (`insights.py:82`) and the 200-row display caps.
- In `scripts/send_event.py:37,42`: a localhost URL and a fixed timestamp.

**Mocked:** `FakeClient` (`test_assistant.py:33`).

**Known gaps the author left open:** GET forms, no rate limiting, no later email merge for webhook users, name scrubbing (README 143-157).

**Dead or leftover material:**

- `railway.json`: the AI_LOG (#8) says Railway stopped reading it.
- `notebooks/profile.py`: scratch code with commented-out prints.
- `pandas`, `numpy` and `pytest` sit in the production `requirements.txt`.
- `DECISIONS.md:69-70`: empty `### Import and Linking` and `### Segments` headings.
- `DECISIONS.md:83`: still contains a drafting note: *"(Your healthcare cell-suppression experience is the natural "why" here.)"*.
- `AI_LOG.md:3`: a stray `.git`. `AI_LOG.md:86`: a malformed, duplicated heading for item 12.
- An untracked `app/.DS_Store` is still on disk.

## 9. Provenance

Estimate: about **85–95% of the application and test code is AI-generated**. Most of the prose in `DECISIONS.md`, `AI_LOG.md` and the commit messages, plus `notebooks/profile.py`, is hand-written. The README is mixed.

**Evidence for AI-generated code:**

- `AI_LOG.md:8` says "AI drafted most of the code".
- `AI_LOG.md` #7 describes installing code drops from downloaded zips with `unzip -o`.
- Commits are whole-feature drops with tests included, for example `0351e87` (+541 lines) and `bbb66cb` (+432).
- The style is uniform across files: plain-English docstrings, `# Rule:` comments, "fail closed" and "belt and braces" phrasing, and the same security idioms (`compare_digest`, parameterized SQL with whitelisted fragments). The AI_LOG's correction details (thinking blocks, venv confusion) are consistent with a back-and-forth with a coding assistant.
- The drafting note left in `DECISIONS.md:83` is a direct sign that prose was drafted with AI as well.

**Evidence for hand-written work:**

- The notebook is iterative and messy.
- The docs and commit messages have consistent typos: "acquistion", "DOn't", "line csvs", "othere", "no PII sent to mode".
- The design decisions are stated in the author's own, less polished voice.

In short: the author's own work is the data profiling and the rules. The implementation looks largely AI-generated, and was then reviewed and corrected.
