"""
Structural test: enforce that no raw litellm.completion() call exists
outside backend/app/llm/router.py.

If this test fails, a developer has added an LLM call that bypasses
the redaction gate. The fix is to route through llm/router.py which
always calls redact() before dispatching.
"""

import subprocess
import sys
from pathlib import Path


def test_no_raw_litellm_completion_outside_router():
    app_dir = Path(__file__).parent.parent / "app"
    router_file = app_dir / "llm" / "router.py"

    result = subprocess.run(
        ["grep", "-rn", r"litellm\.completion", str(app_dir)],
        capture_output=True,
        text=True,
    )

    violations = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        # Normalise path for comparison
        file_path = line.split(":")[0]
        if Path(file_path).resolve() != router_file.resolve():
            violations.append(line)

    assert not violations, (
        "Raw litellm.completion() calls found outside llm/router.py — "
        "these bypass the redaction gate:\n" + "\n".join(violations)
    )


def test_no_raw_litellm_acompletion_outside_router():
    app_dir = Path(__file__).parent.parent / "app"
    router_file = app_dir / "llm" / "router.py"

    result = subprocess.run(
        ["grep", "-rn", r"litellm\.acompletion", str(app_dir)],
        capture_output=True,
        text=True,
    )

    violations = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        file_path = line.split(":")[0]
        if Path(file_path).resolve() != router_file.resolve():
            violations.append(line)

    assert not violations, (
        "Raw litellm.acompletion() calls found outside llm/router.py:\n"
        + "\n".join(violations)
    )
