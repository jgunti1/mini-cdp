"""The AI assistant.

The model's only job is to turn a plain-English question into a choice of tool and
filter values, and then to phrase the answer. It never sees a subscriber:

  - The question is scrubbed of emails and IDs before it is sent.
  - Tools run on our server. The model gets back counts and totals only.
  - Lists of people go straight from our database to the web page.
  - Everything sent to the model passes assert_no_pii first, and is kept in a
    trace that the page shows under "What the model saw".
"""
import json
import os

from app import insights
from app.config import TODAY
from app.pii import assert_no_pii, scrub_text
from app.segments import build_segment, list_sources

MODEL = os.environ.get("ASSISTANT_MODEL", "claude-haiku-5-5")
MAX_ROUNDS = 5
SMALL_COUNT = 5  # counts below this are reported to the model as "fewer than 5"

TOOLS = [
    {
        "name": "build_segment",
        "description": (
            "Build a list of newsletter subscribers matching filters. You receive only the count;"
            " the list itself is shown to the user by the application. Use for 'how many' and"
            " 'build me a list' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Acquisition source, or 'any'."},
                "status": {"type": "string", "enum": ["active", "unsubscribed", "any"]},
                "engagement": {
                    "type": "string",
                    "enum": ["any", "not_opened_in_days", "never_opened"],
                    "description": "'not_opened_in_days' = opened before but not in the last `days` days (went cold).",
                },
                "days": {"type": "integer", "minimum": 1, "maximum": 365},
                "has_app": {"type": "string", "enum": ["any", "yes", "no", "used_recently"]},
                "signup_from": {"type": "string", "description": "Earliest signup date, YYYY-MM-DD."},
                "signup_to": {"type": "string", "description": "Latest signup date, YYYY-MM-DD."},
            },
        },
    },
    {
        "name": "breakdown",
        "description": "Count subscribers grouped by one dimension.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["source", "status", "signup_month"]},
                "status": {"type": "string", "enum": ["active", "unsubscribed", "any"]},
            },
            "required": ["dimension"],
        },
    },
    {
        "name": "first_pages",
        "description": "For subscribers who signed up on or after a date, the first website page each one visited, counted per page.",
        "input_schema": {
            "type": "object",
            "properties": {"signup_from": {"type": "string", "description": "YYYY-MM-DD. Defaults to 30 days ago."}},
        },
    },
    {
        "name": "channel_report",
        "description": (
            "Compare acquisition channels by how well their subscribers stay engaged:"
            " % stayed, gone cold, never opened, unsubscribed, and each channel's share of the total."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "most_engaged",
        "description": "Rank active subscribers by engagement score. You receive only how many were listed; the list is shown to the user.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        },
    },
]


def system_prompt(sources):
    return (
        "You help a newsletter's Growth team explore subscriber data.\n"
        f"Today's date is {TODAY}. Use it for anything time-based.\n"
        f"Acquisition sources: {', '.join(sources)}.\n"
        "Answer by calling a tool. You never see individual subscribers: tools return counts and"
        " totals to you, and the application shows any list of people to the user itself.\n"
        "If the question is about one specific person, say that the Lookup page is the place for that.\n"
        "Reply in two or three plain sentences. State which filters you used so the user can check them."
    )


def safe_count(number):
    return number if number >= SMALL_COUNT else f"fewer than {SMALL_COUNT}"


def run_tool(conn, name, args):
    """Run one tool. Returns (what the model is told, what the page shows).

    The first value is built by hand from counts and labels only. Rows that contain
    emails appear only in the second value, which never leaves this server except to
    the logged-in user's browser.
    """
    if name == "build_segment":
        allowed = {"source", "status", "engagement", "days", "has_app", "signup_from", "signup_to"}
        filters = {key: value for key, value in args.items() if key in allowed}
        rows = build_segment(conn, **filters)
        for_model = {"count": safe_count(len(rows)), "filters_used": filters}
        for_page = {
            "title": f"Segment: {len(rows)} subscribers",
            "note": ", ".join(f"{key} = {value}" for key, value in filters.items()) or "no filters",
            "columns": ["Email", "Signed up", "Status", "Source", "Last open"],
            "rows": [
                [row["email"], row["signup_date"], row["status"], row["acquisition_source"] or "", row["last_open_date"] or "never"]
                for row in rows[:200]
            ],
        }
        return for_model, for_page

    if name in ("breakdown", "first_pages"):
        if name == "breakdown":
            rows = insights.breakdown(conn, args.get("dimension"), args.get("status", "active"))
            title = f"Subscribers by {args.get('dimension')}"
        else:
            rows = insights.first_pages(conn, args.get("signup_from"))
            title = "First page visited by new subscribers"
        for_model = {"rows": [{"label": row["label"], "subscribers": safe_count(row["subscribers"])} for row in rows]}
        for_page = {
            "title": title,
            "note": "",
            "columns": ["", "Subscribers"],
            "rows": [[row["label"], row["subscribers"]] for row in rows],
        }
        return for_model, for_page

    if name == "channel_report":
        report = insights.channel_report(conn)
        # Percentages and counts per channel only; no person appears in this.
        for_model = {"rules": insights.CHANNEL_RULES, "channels": report}
        for_page = {
            "title": "Which channels bring readers who stay",
            "note": insights.CHANNEL_RULES,
            "columns": ["Channel", "Subscribers", "% of total", "% stayed", "% gone cold",
                        "% never opened", "% unsubscribed", ""],
            "rows": [
                [r["channel"], r["subscribers"], r["share_of_total"], r["stayed_pct"], r["gone_cold_pct"],
                 r["never_opened_pct"], r["unsubscribed_pct"], "small sample" if r["small_sample"] else ""]
                for r in report
            ],
        }
        return for_model, for_page

    if name == "most_engaged":
        rows = insights.most_engaged(conn, args.get("limit", 25))
        for_model = {"listed": len(rows), "scoring_rule": insights.ENGAGEMENT_RULE}
        for_page = {
            "title": f"Most engaged readers (top {len(rows)})",
            "note": insights.ENGAGEMENT_RULE,
            "columns": ["Email", "Source", "Last open", "Score"],
            "rows": [[row["email"], row["acquisition_source"] or "", row["last_open_date"] or "never", row["score"]] for row in rows],
        }
        return for_model, for_page

    raise ValueError(f"unknown tool: {name}")


def block_to_dict(block):
    """Turn one piece of the model's reply into a plain dictionary, keeping every field.

    The reply has to be sent back unchanged on the next round. That includes "thinking"
    blocks, which the API rejects if any of their fields are missing.
    """
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    return dict(vars(block))  # the stand-in objects used in tests


def answer_question(conn, question, client=None):
    """Answer one question. Returns the answer text, tables for the page, and the trace."""
    cleaned, removed = scrub_text(question.strip())
    system = system_prompt(list_sources(conn))
    messages = [{"role": "user", "content": cleaned}]
    trace = []      # everything sent to and received from the model, shown on the page
    displays = []   # tables for the page; these may contain emails and never go to the model

    if client is None:
        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    assert_no_pii(system)
    trace.append({
        "direction": "instructions sent with every request",
        "content": {"system": system, "tools": [tool["name"] for tool in TOOLS]},
    })

    answer = ""
    for _ in range(MAX_ROUNDS):
        # The single exit point to the model. Nothing is sent without passing this check.
        assert_no_pii({"system": system, "messages": messages})
        trace.append({"direction": "sent to model", "content": messages[-1]["content"]})

        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=system, tools=TOOLS, messages=messages
        )
        reply = [block_to_dict(block) for block in response.content]
        trace.append({"direction": "received from model", "content": reply})
        messages.append({"role": "assistant", "content": reply})

        tool_calls = [block for block in reply if block["type"] == "tool_use"]
        if not tool_calls:
            answer = " ".join(block["text"] for block in reply if block["type"] == "text")
            break

        results = []
        for call in tool_calls:
            try:
                for_model, for_page = run_tool(conn, call["name"], call["input"])
                displays.append(for_page)
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": json.dumps(for_model)})
            except (ValueError, TypeError) as error:
                results.append({
                    "type": "tool_result", "tool_use_id": call["id"], "is_error": True,
                    "content": f"Could not run {call['name']}: {error}",
                })
        messages.append({"role": "user", "content": results})
    else:
        answer = "I could not finish answering that. Try asking it a different way."

    answer, _ = scrub_text(answer)  # belt and braces: the reply should never contain an email
    return {"answer": answer, "displays": displays, "trace": trace, "question_was_scrubbed": removed}
