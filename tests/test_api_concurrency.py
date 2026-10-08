"""Other changes to the same request at the same moment, through the API.

Two callers who saw the same version: exactly one change may win; the other
is told its version is stale (I3), and the request shows only the winner's
change (I4). A change committed right after ours must not leak into our
response ("Request detail", consistency guarantees).
"""

import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select

import app.api
from app.domain import Actor
from app.domain import decide as decide_in_domain
from app.domain import revise as revise_in_domain
from app.models import ExceptionRequest, Outcome, Role
from tests.helpers import create, decide, get, request_id_for, revise

APPROVE = {"outcome": "APPROVED", "comment": "Fits policy."}
DECLINE = {"outcome": "DECLINED", "comment": "Too high."}
CHANGE = {"discount_bps": 35, "reason": "Second competing offer."}
NOTHING = (None, None)


def in_force(detail: dict) -> tuple:
    """The approval in force as a request detail names it: revision and discount."""
    return (detail["approved_revision_number"], detail["approved_discount_bps"])


def slowed(change):
    """Pause after the request was loaded and before it is changed."""

    def wrapper(*args, **kwargs):
        # Widens the window in which broken locking shows. Correct code gives
        # the same result without it; no assertion depends on timing.
        time.sleep(0.2)
        return change(*args, **kwargs)

    return wrapper


def meet_before_write_begin(client) -> None:
    """Hold each write transaction just before BEGIN until a second one arrives.

    Both writes then try to begin at the same moment. They meet before the
    write lock is requested, so correct code cannot deadlock here; if the
    second write never arrives, the wait times out and the request fails.
    Relies on two internals from app/db.py: the engine behind the sessions,
    and the sqlite_begin option that only write sessions carry.
    """
    engine = client.app.state.read_sessions.kw["bind"]
    meeting = threading.Barrier(2, timeout=5)

    def before_statement(conn, _cursor, statement, *_args):
        if statement.startswith("BEGIN") and "sqlite_begin" in conn.get_execution_options():
            meeting.wait()

    event.listen(engine, "before_cursor_execute", before_statement)


def nothing_approved(client) -> tuple[str, int]:
    """Alice's request on APP-1001 at 20 bps: PENDING at version 1."""
    return create(client).json()["id"], 1


def approved_then_revised(client) -> tuple[str, int]:
    """Approved at 20 bps in revision 1, then revised to 30 bps: PENDING at version 3."""
    request_id = create(client).json()["id"]
    assert decide(client, request_id, expected_version=1, **APPROVE).status_code == 201
    more = revise(client, request_id, expected_version=2, discount_bps=30, reason="More.")
    assert more.status_code == 201
    return request_id, 3


# Each call is listed with the approval that must be in force if it wins. The value
# is written out here: the winner's response and the stored request come from the
# same code and would agree on a wrong one.
@pytest.mark.parametrize(
    ("start", "calls"),
    [
        (
            nothing_approved,
            [
                (decide, {"user": "carol", **APPROVE}, (1, 20)),
                (decide, {"user": "dave", **DECLINE}, NOTHING),
            ],
        ),
        (
            nothing_approved,
            [
                (revise, {"user": "alice", **CHANGE}, NOTHING),
                (decide, {"user": "carol", **APPROVE}, (1, 20)),
            ],
        ),
        (
            approved_then_revised,
            [
                (decide, {"user": "carol", **APPROVE}, (2, 30)),
                (decide, {"user": "dave", **DECLINE}, (1, 20)),
            ],
        ),
        (
            approved_then_revised,
            [
                (revise, {"user": "alice", **CHANGE}, (1, 20)),
                (decide, {"user": "carol", **APPROVE}, (2, 30)),
            ],
        ),
    ],
    ids=[
        "approve-and-decline",
        "revise-and-approve",
        "approve-and-decline-with-an-approval-in-force",
        "revise-and-approve-with-an-approval-in-force",
    ],
)
def test_only_one_of_two_concurrent_changes_wins(client, monkeypatch, start, calls):
    request_id, version = start(client)
    monkeypatch.setattr(app.api, "decide", slowed(app.api.decide))
    monkeypatch.setattr(app.api, "revise", slowed(app.api.revise))
    meet_before_write_begin(client)
    responses, errors = {}, []

    def run(index, call, body):
        try:
            responses[index] = call(client, request_id, expected_version=version, **body)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(index, call, body))
        for index, (call, body, _) in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    # Whoever won, the stored status is the decision on the latest revision, or
    # PENDING when that revision has none. Checked first, so that it is seen to
    # fail by itself when both changes get through.
    current = get(client, request_id).json()
    decision = current["revisions"][-1]["decision"]
    assert current["status"] == (decision["outcome"] if decision else "PENDING")
    assert sorted(r.status_code for r in responses.values()) == [201, 409]
    [won] = [index for index, r in responses.items() if r.status_code == 201]
    [lost] = [index for index, r in responses.items() if r.status_code == 409]
    assert responses[lost].json()["code"] == "STALE_VERSION"
    assert responses[won].json()["version"] == version + 1
    assert get(client, request_id).json() == responses[won].json()
    assert in_force(current) == calls[won][2]


def change_right_after_the_next_commit(client, change) -> None:
    """Commit `change` in another session as soon as the endpoint has committed."""
    sessions = client.app.state.write_sessions
    done = []

    def after_commit(_session):
        if not done:
            done.append(True)
            with sessions() as other:
                change(other)
                other.commit()

    event.listen(sessions, "after_commit", after_commit)


def load_app_1002(session) -> ExceptionRequest:
    return session.scalar(
        select(ExceptionRequest).where(ExceptionRequest.application_id == "APP-1002")
    )


def approve_by_carol(session):
    request = load_app_1002(session)
    decide_in_domain(
        request,
        Actor("carol", frozenset({Role.REVIEWER})),
        expected_version=request.version,
        outcome=Outcome.APPROVED,
        comment="Approved in between.",
        now=datetime.now(UTC),
    )


def revise_by_alice(session):
    request = load_app_1002(session)
    revise_in_domain(
        request,
        Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER})),
        expected_version=request.version,
        discount_bps=15,
        reason="Revised in between.",
        now=datetime.now(UTC),
    )


def history(detail: dict) -> list[tuple]:
    return [
        (r["number"], r["discount_bps"], r["decision"] and r["decision"]["outcome"])
        for r in detail["revisions"]
    ]


@pytest.mark.parametrize(
    (
        "call",
        "body",
        "expected_status",
        "expected_history",
        "later_change",
        "later_status",
        "later_in_force",
    ),
    [
        (
            revise,
            {"user": "alice", **CHANGE},
            "PENDING",
            [(1, 25, None), (2, 35, None)],
            approve_by_carol,
            "APPROVED",
            (2, 35),
        ),
        (
            decide,
            {"user": "carol", **DECLINE},
            "DECLINED",
            [(1, 25, "DECLINED")],
            revise_by_alice,
            "PENDING",
            NOTHING,
        ),
    ],
    ids=["revise", "decide"],
)
def test_response_shows_the_state_this_change_produced(
    client,
    call,
    body,
    expected_status,
    expected_history,
    later_change,
    later_status,
    later_in_force,
):
    # Seed: APP-1002 is PENDING at 25 bps, created by alice; version 1.
    request_id = request_id_for(client, "APP-1002")
    change_right_after_the_next_commit(client, later_change)

    response = call(client, request_id, expected_version=1, **body)

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == (expected_status, 2)
    assert history(body) == expected_history
    # Nothing was approved when this change was made; the approval that follows
    # in the revise case must not show up in its response.
    assert in_force(body) == NOTHING
    latest = body["revisions"][-1]
    changed_at = latest["decision"]["decided_at"] if latest["decision"] else latest["created_at"]
    assert body["updated_at"] == changed_at
    # The later change did happen, so the response could have shown it.
    current = get(client, request_id).json()
    assert (current["status"], current["version"]) == (later_status, 3)
    assert in_force(current) == later_in_force
