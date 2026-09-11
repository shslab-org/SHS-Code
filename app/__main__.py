"""SHS Code canonical module entry point.

Allows ``python -m app`` (equivalent to the ``shscode`` console script
defined in pyproject ``[project.scripts]`` as ``app.cli:main``).

Note on ``python -m shscode`` (spec §2): there is intentionally NO
top-level ``shscode`` import package — the distribution name is
``shscode`` but the import package is ``app/`` (see pyproject
``[tool.setuptools.packages.find]`` which includes only ``app*``).
The ``shscode`` console script maps to ``app.cli:main``. The supported
module execution paths are therefore ``python -m app``,
``python -m app.cli`` and ``python -m app.server``.
"""
from app.cli import main

if __name__ == "__main__":
    main()
