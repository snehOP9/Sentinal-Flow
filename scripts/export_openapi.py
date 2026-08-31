"""Export the versioned FastAPI contract without starting external dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from fraud_platform.api.app import create_app
from fraud_platform.config import Settings


def main() -> None:
    app = create_app(Settings(_env_file=None))
    Path("docs/openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
