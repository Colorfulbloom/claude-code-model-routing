"""The one place that decides how strict a wall-clock assert is.

A test that asserts on elapsed time keeps its strict limit for a local run. That limit
is the real target, such as 250 ms for a Review route or 1 s for a 1 MiB line. Under
CI, which GitHub sets, the same test asks this module for its limit instead.

Two kinds of limit exist, because two things make a runner slow.

- ``limit`` is for work the CPU does. A GitHub runner has two shared vCPUs, and the
  python 3.11 job runs under coverage's C tracer with pytest-xdist. That job measured
  4 to 12 times slower than a laptop (run 42928016422). Python 3.14 ran the same
  tests 2.4 times faster (run 42914526705), and coverage 7.17.2 defaults to its
  cheaper ``sys.monitoring`` core there (``SYSMON_DEFAULT`` in coverage/env.py).
  ``limit`` multiplies the local limit by ``CI_FACTOR``.
- ``wait_limit`` is for a deadline the code itself sets with a timer, such as the
  gate's 3 s body timeout. A tracer does not slow a sleep, so a factor would only
  hide a wrong timeout. It adds ``CI_WAIT_SLACK_S`` for a stalled runner instead.

``CI_FACTOR`` is 10. The slowest 3.11 measurements against their local targets were
4.5 times (warm Setup check, 89 ms against 20 ms), 4.0 times (Review median, 993 ms
against 250 ms) and 3.6 times (cold Setup, 1087 ms against 300 ms). A factor of 10
leaves about 2 times headroom over those on 3.11 and about 5 times on 3.14. It still
fails a real slowdown of an order of magnitude. A quadratic regression in a linear
scan is far past that. The old ``mask_url`` regex took about 480 s on 1 MiB, against
0.09 s now, and the limit there is 10 s.

A test that asserts on a CI limit carries the ``timing`` marker. The python 3.11
coverage job deselects it (``-m "not timing"`` in ``.github/workflows/bartab.yml``),
and the python 3.14 job runs it. ``test_timing_policy.py`` fails when a test module
reads the clock and neither uses this module nor is listed there with its reason.
"""

import os

CI_FACTOR = 10.0
CI_WAIT_SLACK_S = 10.0


def in_ci() -> bool:
    """Return True when GitHub (or anything else that sets ``CI``) runs the tests."""
    return bool(os.environ.get("CI"))


def limit(local: float) -> float:
    """Return the limit for work the CPU does, in the unit of ``local``.

    Args:
        local: The strict limit that holds on a developer's machine.

    Returns:
        ``local`` on a local run, and ``local`` times ``CI_FACTOR`` under CI.
    """
    return local * CI_FACTOR if in_ci() else local


def wait_limit(local: float) -> float:
    """Return the limit for a deadline a timer sets, in seconds.

    Args:
        local: The strict limit in seconds that holds on a developer's machine.

    Returns:
        ``local`` on a local run, and ``local`` plus ``CI_WAIT_SLACK_S`` under CI.
    """
    return local + CI_WAIT_SLACK_S if in_ci() else local
