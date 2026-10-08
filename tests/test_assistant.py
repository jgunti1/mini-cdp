import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.assistant import answer_question, run_tool
from app.db import SCHEMA
from app.pii import PIILeak, assert_no_pii, scrub_text


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for number in range(1, 9):
        conn.execute("INSERT INTO profiles (id, email) VALUES (?, ?)", (number, f"person{number}@example.com"))
        conn.execute(
            "INSERT INTO subscribers VALUES (?, '2026-07-01', 'active', 'instagram', '2026-08-01')", (number,)
        )
    return conn


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool_use(name, arguments):
    return SimpleNamespace(type="tool_use", id="toolu_1", name=name, input=arguments)


class FakeClient:
    """Stands in for the real AI service: replies with whatever it was given, and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []
        self.messages = self

    def create(self, **request):
        self.sent.append(json.dumps(request, default=str))
        return SimpleNamespace(content=self.replies.pop(0))


def test_scrub_removes_emails_and_ids():
    cleaned, removed = scrub_text("What has Sam.Mitchell35@gmail.com (u_2b6447a3) been reading?")
    assert removed
    assert "@" not in cleaned
    assert "u_2b6447a3" not in cleaned


def test_scrub_leaves_ordinary_questions_alone():
    assert scrub_text("How many Instagram signups went cold?") == ("How many Instagram signups went cold?", False)


def test_assert_no_pii_blocks_an_email():
    with pytest.raises(PIILeak):
        assert_no_pii({"messages": [{"content": "person1@example.com"}]})


def test_tool_result_for_model_has_no_emails(conn):
    for_model, for_page = run_tool(conn, "build_segment", {"source": "instagram"})
    assert for_model["count"] == 8
    assert "@" not in json.dumps(for_model)
    assert "person1@example.com" in json.dumps(for_page)  # the page does get the list


def test_small_counts_are_hidden_from_the_model(conn):
    for_model, _ = run_tool(conn, "build_segment", {"source": "facebook"})
    assert for_model["count"] == "fewer than 5"


def test_nothing_sent_to_the_model_contains_an_email(conn):
    client = FakeClient(
        [tool_use("build_segment", {"source": "instagram", "engagement": "not_opened_in_days", "days": 30})],
        [tool_use("most_engaged", {"limit": 5})],
        [text("There are 8 such subscribers.")],
    )
    result = answer_question(conn, "List cold instagram signups, like person1@example.com", client=client)

    assert len(client.sent) == 3
    for request in client.sent:
        assert "@" not in request
    assert result["question_was_scrubbed"]
    assert result["answer"] == "There are 8 such subscribers."
    assert len(result["displays"]) == 2
    assert "@" not in json.dumps(result["trace"])


def test_bad_tool_arguments_do_not_crash(conn):
    client = FakeClient([tool_use("build_segment", {"status": "bogus"})], [text("Sorry, I could not do that.")])
    result = answer_question(conn, "anything", client=client)
    assert result["answer"].startswith("Sorry")


def test_thinking_blocks_are_sent_back_complete(conn):
    """The real model can reply with a thinking block; it must go back with every field."""
    thinking = SimpleNamespace(type="thinking", thinking="The user wants a segment.", signature="sig123")
    client = FakeClient(
        [thinking, tool_use("build_segment", {"source": "instagram"})],
        [text("There are 8.")],
    )
    answer_question(conn, "how many instagram signups?", client=client)
    second_request = json.loads(client.sent[1])
    sent_back = second_request["messages"][1]["content"][0]
    assert sent_back == {"type": "thinking", "thinking": "The user wants a segment.", "signature": "sig123"}
