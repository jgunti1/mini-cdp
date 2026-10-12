# AI Log

How I used AI on this project, and every place it was wrong.git 

## How I worked with AI

- **I decided, AI drafted.** I made the design decisions (dedupe and merge rules, linking rules, the
  webhook design, the PII approach, the channel report's definitions). AI drafted most of the code.
- **Explain it back.** Before moving on from any piece of code, I explained what it did and why. Where
  I couldn't, we slowed down on that part.
- **Check against real data.** Every count the code produced was compared with the numbers I found by
  hand while profiling (8 blank rows, 85 duplicates, 2 invalid emails, 2,900 subscribers, 8,441 linked
  visits).
- **Tests.** Each data problem and webhook rule I found became an automated test.

## Where AI was wrong

### 1. Sampling missed a rare data problem (Oct 3)
- **What happened:** AI suggested looking for hidden whitespace in emails by printing a random sample
  of 40 rows. The sample looked clean.
- **Reality:** 22 of about 3,000 emails had leading or trailing spaces, too few to show up in a sample.
- **How it was caught:** a direct check (comparing each email with its stripped version) found all 22.
- **Lesson:** test for rare problems directly; don't sample for them.

### 2. Too many tasks at once (Oct 3)
- **What happened:** during profiling, AI gave several tasks and questions in each message.
- **Reality:** I lost track of what I was doing and why.
- **How it was caught:** I asked to slow down. We switched to one step per message.
- **Lesson:** smaller steps, each with a clear purpose.

### 3. A misleading hint about the database (Oct 4)
- **What happened:** AI hinted that the `UNIQUE` rule on `profiles.email` would cause an error if the import ran twice.
- **Reality:** `get_or_create_profile` finds existing profiles, so no duplicate was created. The failure would have come from the `subscribers` primary key.
- **How it was caught:** AI corrected itself after my answer.
- **Lesson:** trace the code path instead of reasoning from the schema alone.

### 4. Describing code that wasn't there (Oct 4)
- **What happened:** AI described the merge function as "ten lines" and pointed to the
  "unsubscribed wins" rule as if it were written in the code.
- **Reality:** the function was nine lines, and the rule had no name or comment. It was only my name for it in DECISIONS.md.
- **How it was caught:** I read the function and asked whether it was hallucinating.
- **Fix:** added comments naming the rule each `if` block implements.

### 5. Wrong guesses about a deployment problem (Oct 5)
- **What happened:** Railway kept serving an old version. AI first guessed the commit wasn't pushed, then that the new deploy had crashed.
- **Reality:** `git status` and `git log` showed the commit was pushed, and there was no failed deploy. Railway's GitHub app was authorized for login but not installed on the repo, so it never saw pushes.
- **How it was caught:** I found "Auto deploy unavailable / Could not load branches" in Railway's settings.
- **Lesson:** check each guess against real output before acting on it.

### 6. Login prompt didn't appear (Oct 6)
- **What happened:** after adding password protection, the page only showed "Not authenticated".
- **Reality:** the protection worked. The browser pane I was using doesn't show HTTP login prompts. AI hadn't anticipated this.
- **How it was caught:** testing with `curl` and in Chrome, where the prompt appeared.

### 7. Copy instructions deleted files (Oct 6)
- **What happened:** AI told me to copy the new `app`, `scripts` and `tests` folders into the repo and "let them merge".
- **Reality:** on a Mac, dragging a folder onto one with the same name replaces it. Seven files that weren't in the download were deleted (`auth.py`, `normalize.py`, `config.py`, `__init__.py` and three test files), and the app failed with `ModuleNotFoundError: No module named 'app.auth'`.
- **How it was caught:** the error, then `git ls-files --deleted`. All files were recovered with `git restore`.
- **Fix:** later updates were installed with `unzip -o`, which only writes the files in the zip.
- **Lesson:** commit often; it turned this into three commands instead of lost work.

### 8. Start command stopped being detected (Oct 7)
- **What happened:** AI relied on `railway.json` to tell Railway how to start the app.
- **Reality:** later builds failed with "No start command detected".
- **How it was caught:** Railway's build error. I set the start command in the service settings.

### 9. Package installed where the server couldn't see it (Oct 8)
- **What happened:** AI's install and run commands didn't account for two Python setups being active at once (the project's `.venv` and conda's `base`).
- **Reality:** `anthropic` was installed in one, and the server ran from the other, giving `ModuleNotFoundError`.
- **How it was caught:** the error message.
- **Fix:** use `python -m pip` and `python -m uvicorn` so both use the same Python.

### 10. Error handling hid the real error (Oct 8)
- **What happened:** the assistant page showed only the error type (`BadRequestError`), not the reason.
- **Reality:** the explanation from the API was being thrown away, so diagnosing took extra steps.
- **How it was caught:** I ran the assistant from the terminal to see the full error.
- **Fix:** the page now shows the first part of the error message.

### 11. Tests passed, real call failed (Oct 8)
- **What happened:** the assistant passed every test against a stand-in for the AI service.
- **Reality:** the first real call failed with `messages.1.content.0.thinking.thinking: Field required`. The code rebuilt the model's reply in a simplified form and dropped its "thinking" blocks, which the stand-in never produced.
- **How it was caught:** the full error message from item 10.
- **Fix:** send the model's reply back unchanged; added a test with a thinking block.
- **Lesson:** a fake service only tests the behavior you thought to put in it.

## Overall
AI was fast at building structure and wrong about details it couldn't see: rare data problems, how my machine and hosting were set up, and what the real API returns. Checking its output against real data and real errors caught every one of these mistakes.
