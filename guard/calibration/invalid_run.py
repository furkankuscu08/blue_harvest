"""Calibration: a test that cannot even be collected. It must be an invalid run."""

from app.domain import does_not_exist  # noqa: F401


def test_never_runs():
    assert True
