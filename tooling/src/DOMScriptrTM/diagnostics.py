"""Optional diagnostics policy; zero expensive artifact work on normal success."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True, **({"slots": True} if sys.version_info >= (3, 10) else {}))
class Diagnostics:
    """Failure-only browser artifacts and lightweight runtime error collection."""

    trace_on_failure: bool = False
    screenshot_on_failure: bool = False
    artifact_dir: str | Path = ".domscriptr-artifacts"
    collect_console_errors: bool = True
    collect_page_errors: bool = True
    collect_request_failures: bool = False

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.trace_on_failure,
                self.screenshot_on_failure,
                self.collect_console_errors,
                self.collect_page_errors,
                self.collect_request_failures,
            )
        )

    @property
    def path(self) -> Path:
        return Path(self.artifact_dir)
