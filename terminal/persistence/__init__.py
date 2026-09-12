"""SQLite persistence boundary for the Manual Trading Terminal."""

from .paper_protection_obligations import install as _install_paper_protection_obligations

_install_paper_protection_obligations()
del _install_paper_protection_obligations
