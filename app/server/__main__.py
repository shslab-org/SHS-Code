"""SHS Code server module execution entry point.

Allows ``python -m app.server`` (equivalent to the ``shscode-server``
console script defined in pyproject ``[project.scripts]``).
"""
from app.server.main import serve

if __name__ == "__main__":
    serve()
