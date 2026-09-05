"""SHS Code — application package.

Single source of truth for the product version. Every surface (CLI banner,
server /healthz, pyproject metadata, installers) must import from here so
they can never drift apart again (they historically showed 4 different
numbers: 5.1.1 / 3.0.3 / 2.1.0 / 2.0.0).
"""

__version__ = "3.0.3"
