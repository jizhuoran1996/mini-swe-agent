"""Reject generated replacements for required upstream inputs before execution."""
from pathlib import Path


def review(task_id: str, solution: Path) -> str | None:
    source=(solution/'main.py').read_text()
    if task_id=='BUILDv1-F01' and ('PLACEHOLDER_LICENSE' in source or 'ensure_submodule_stubs' in source):
        return 'Generated licenses or CMake stubs replace genuine upstream submodule inputs; all 75 locked modules are already provided.'
    if task_id=='BUILDv1-C10' and 'ExternalData_Add_Target' in source and 'suppressed (offline)' in source:
        return 'An upstream ExternalData operation was replaced with a no-op; genuine frozen fixtures or supported options are required.'
    if task_id=='BUILDv1-A02' and 'PAGER_C' in source:
        return 'A synthetic pager replaces the official CLI test dependency; the real less executable is required.'
    return None
