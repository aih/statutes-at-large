"""deploy/comps-walk.sh stops on the summary line that says a run loaded nothing."""

import os
import subprocess
from pathlib import Path

import pytest

from ingest.comps import NOTHING_NEW, PollReport, summary_line

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "comps-walk.sh"


def _report(**fields: int) -> PollReport:
    report = PollReport(collection="COMPS", since="1990-01-01T00:00:00+00:00", checked_at="now", seen=2685)
    for name, value in fields.items():
        setattr(report, name, value)
    return report


def test_a_run_of_failures_only_loaded_nothing() -> None:
    assert NOTHING_NEW in summary_line(_report(skipped=2675, fetched=10, failed=10))
    assert NOTHING_NEW in summary_line(_report(skipped=2685))
    assert NOTHING_NEW in summary_line(_report(fetched=10, unchanged=10))


def test_a_run_that_loaded_something_is_not_the_end() -> None:
    assert NOTHING_NEW not in summary_line(_report(fetched=317, new=307, failed=10))
    assert NOTHING_NEW not in summary_line(_report(fetched=1, new_versions=1))


def _walk(tmp_path: Path, lines: list[str]) -> tuple[int, str]:
    """Run the script with a fake `make comps-walk` that prints one summary line per
    run, in order, then repeats the last."""
    fake = tmp_path / "fake-poll.sh"
    counter = tmp_path / "count"
    counter.write_text("0")
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f"n=$(cat '{counter}'); n=$((n + 1)); echo $n > '{counter}'\n"
        + "".join(f"[ $n -le {i + 1} ] && {{ echo {line!r}; exit 0; }}\n" for i, line in enumerate(lines))
        + f"echo {lines[-1]!r}\n"
    )
    fake.chmod(0o755)
    log = tmp_path / "comps-walk.log"
    env = {
        **os.environ,
        "WALK_CMD": str(fake),
        "INTERVAL": "0",
        "MAX_RUNS": "3",
        "LOG": str(log),
        "DATA_ROOT": str(tmp_path),
    }
    completed = subprocess.run(["bash", str(SCRIPT)], env=env, cwd=ROOT, capture_output=True, text=True, timeout=30)
    return completed.returncode, log.read_text()


@pytest.mark.skipif(os.name != "posix", reason="a bash script")
def test_the_walk_ends_on_the_first_run_that_loaded_nothing(tmp_path: Path) -> None:
    status, log = _walk(
        tmp_path,
        [
            summary_line(_report(fetched=400, new=400)),
            summary_line(_report(skipped=2675, fetched=10, failed=10)),
        ],
    )
    assert status == 0
    assert log.count("=== ") and "run 2 exit 0" in log
    assert "walk complete after 2 run(s)" in log
    assert "run 3" not in log


@pytest.mark.skipif(os.name != "posix", reason="a bash script")
def test_the_walk_stops_at_max_runs_when_every_run_loads_something(tmp_path: Path) -> None:
    status, log = _walk(tmp_path, [summary_line(_report(fetched=400, new=400))])
    assert status == 1
    assert "run 3 exit 0" in log
    assert "walk stopped after 3 runs" in log
