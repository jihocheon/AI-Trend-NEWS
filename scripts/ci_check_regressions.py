"""Reject empty/skipped/non-successful unittest runs; preserve the runner's exit too."""
import os
import re
import sys
from pathlib import Path


def check(path):
    output = Path(path).read_text()
    count = re.search(r"^Ran (\d+) tests? in ", output, re.MULTILINE)
    if not count or int(count[1]) == 0:
        raise SystemExit("CI requires a nonempty unittest run")
    if not re.search(r"^OK$", output, re.MULTILINE) or re.search(
        r"skipped=|expected failures=|unexpected successes=|\.\.\. skipped", output
    ):
        raise SystemExit("CI requires all executed regression tests to pass without skips")
    if os.getenv("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as report:
            report.write(f"test_count={count[1]}\n")
    print(f"Regression gate: {count[1]} tests passed; 0 skipped")


if __name__ == "__main__":
    check(sys.argv[1])
