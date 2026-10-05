"""Regression guards for I10: replaying a committed create returns the stored response."""

from tests.helpers import create, decide, get


def test_replay_of_a_committed_create_returns_the_stored_original_response(client):
    first = create(client)
    assert first.status_code == 201

    replay = create(client)

    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_replay_is_never_answered_with_request_already_exists_after_the_request_changed(client):
    first = create(client)
    request_id = first.json()["id"]
    assert decide(
        client, request_id, expected_version=1, outcome="DECLINED", comment="Too high."
    ).status_code == 201

    replay = create(client)

    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_replay_changes_no_state(client):
    first = create(client)
    request_id = first.json()["id"]
    before = get(client, request_id).json()

    create(client)

    assert get(client, request_id).json() == before
