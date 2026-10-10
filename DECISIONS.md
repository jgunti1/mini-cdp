## Data quality findings

### subscribers.csv
- **Finding:** 8 rows are blank in every column
  **Rule:** This row is skipped, but the record is recorded as skipped.
  **Why:** Nothing we can do about this lack of information. If we have future information of a lot of blank rows, we will be able ot track it easier. 

  - **Finding:** 0 exact duplicates. 63 hidden by capitilzation. 22 more have leading and trailing space. 85 duplicate rows in total, 2902 unique subscribers.
  **Rule:** Strip leading and trailing space, and lowercase.
  **Why:** So we are not duplicating people.

  - **Finding:** No rows with duplicate entries varying in status or dates, but handling in case. 
  **Rule:** merge duplicates
  -- Signup date: Earliest Date
  -- Last Open Date: Latest Date
  -- Status: Unsubscribed if any row says so. 
  -- Acquistion source: Keep the source from the row with the earliest signup date. 
  **Why:** so we don't spam people and so we have the most up to date information. Earliest sign up date is for when they actually joined. 

 - **Finding:** 2 rows with invalid emails entries. 
  **Rule:** Send to a rejected table.
  **Why:** DOn't want to try sending invalid emails information.

- **Finding:** 2900 valid subscribers. 

  - **Finding:** Mismatched source names. Capitilzation problems and twitter-x
  **Rule:** Lowercase everything and twitter maps to x.
  **Why:** So we know the sources and are duplicating them .

- **Finding:** Web events are have multiple rows. 
  **Rule:** Once a visitor ID has an email on any row, every row with that visitor ID belongs to that subscriber. 
  **Why:** If we don't, every subscriber would show exactly one visit to the same page, which tells nothing. 


- **Finding:** 30 unmatched app users. 
  **Rule:** Unseen user_id still gets a profile and is not dropped. 
  **Why:** According to the rules. 

  ## Design decisions

- **Decision:** Creating a dictionary for checking source aliases. Ex: Twitter to X.
  **Alternative:** Hardcode a list of common sources. 
  **Why:** In the off-chance that some name does change, it should be a simple fix. Unnecessary to change now. 


- **Decision:** Separating profiles and subscribers.
  **Alternative:** Have everyone in subscribers. 
  **Why:** A profile is a person but people might be null, but we still need to create a profile for them, for example, if they are a app user but not a subscriber. 

- **Decision:** Today is fixed at 2026-09-28 defined once in config.py.
  **Alternative:** Use real date.
  **Why:** Eventually the webhook and assistant would end up with different values, which would give different answers to the same questions. 


- **Decision:** Segments include active subscribers only by default
  **Alternative:** Include everyone and the let the user filter.
  **Why:** Don't want to email people who aren't subscribed. 


- **Decision:** "Not opened in N days" means they opened before and then stopped. People who never opened are excluded and have their own filter.
  **Alternative:** Count people who have never opened as cold if they signed up more than N days ago. 
  **Why:** Probably better to assume they don't use it and get more interaction than they use it less than what we think. 

- **Decision:** Filter values are checked against a fixed list on server.
**Alternative:** Trust the dropdowns. 
**Why:** A user could manually change it to something invalid. 


### Import and Linking
### Segments
### Webhook
Duplicates: event_id is the primary key, so a repeated event is ignored and answered as "duplicate". Alternative: check by event content (same user, device and timestamp). Why: So we don't keep track of duplicate events and chart a user as more active than actually are. 
Out of order: each event keeps its own timestamp and pages sort by it. Alternative: reorder events as they arrive. Why: So we can see the where a user is most likely to go after logging or doing any task. 
Anonymous then login: a devices table remembers which person each device belongs to. Anonymous events are attached when the login arrives, and late arrivals are attached as they come in. Alternative: attach only at the moment of login. Why: So we know which user is logged in. 
Unknown user_id: gets a profile with no email plus an app_users row. Alternative: reject or drop the event. Why: So people we can still get people who don't subscribe. 
Authentication: an HMAC signature over the timestamp and body, with a 5-minute window. Alternative: a shared secret token in a header. Why: More secure than header since a person can always edit the header. 
Storage: a Railway volume holds the database. Alternative: rebuild from CSVs on each deploy. Why: It is faster.
Re-import: the import no longer deletes profiles or app users. Why: Don't have to worry about inserting the same user. 
### Assistant
What the model does: it only chooses a tool and filter values, then phrases the answer. Alternative: send it subscriber rows (with or without ids) and let it pick. Why: A lot of work. 
What the model receives back: counts and totals only. Lists of people go straight to the page. Alternative: pseudonymized rows. Why: Anonynimity reasons. 
Typed PII: emails and IDs are stripped from the question before sending. Alternative: trust users not to type them. Why: So we don't release PII information on accident. 
Small counts: anything under 5 is reported to the model as "fewer than 5". Alternative: exact counts. (Your healthcare cell-suppression experience is the natural "why" here.) Why: Could be identified if it is small enough. 
Defense in depth: assert_no_pii checks everything before every call. Why: So we don't send naything we shouldn't 
Single choke point: exactly one line sends data to the AI service. Why: We know exactly where the problem is if one arises. 
Transparency: the page shows "What the AI model saw" for every answer. Alternative: log it privately. Why: so we can see what went wrong immediately. 

  ## Limitations

**Limitation 2:** Page shows the first 200 rows and no export.
**Solution:** Add export and/or show more rows. 

**Limitation 3:** If two or more people share a device, anonymous events all go to whoever logged in first. 
**Solution:** Unsure.
