"""The triage: a decision package prepared from one message.

Three implementations of the same contract: the Claude API (production), a rules-based
classifier (an offline baseline that also serves the demo for messages without a
recording) and the recorded readings of the fixture inbox (demo). Whatever prepares the
package, `checks.py` verifies it against the area's directory and rules."""

from .checks import check_package
from .fixture import FixtureTriager
from .rules import RuleTriager
from .types import TriageInput, Triager

__all__ = ["FixtureTriager", "RuleTriager", "TriageInput", "Triager", "check_package"]
