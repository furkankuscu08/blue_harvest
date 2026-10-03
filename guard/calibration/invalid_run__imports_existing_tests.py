"""Calibration: no test of its own, only the existing tests imported. It must be an invalid run.

Before this case existed, the harness ran these imported tests against a full baseline, so
the withheld reference tests came back and were reported as caught.
"""

from test_domain import *  # noqa: F403
