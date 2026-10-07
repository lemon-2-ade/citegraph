"""Write the API's OpenAPI schema to stdout (or ``--out FILE``).

The schema is produced from the FastAPI app object without starting it, so no database or
other service is needed. The frontend generates its TypeScript types from this output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write to this file instead of stdout")
    args = parser.parse_args()

    # Settings are only read, never used to connect; dummy values keep the export
    # independent of a developer's .env.
    os.environ.setdefault("NEO4J_PASSWORD", "openapi-export")
    os.environ.setdefault("APP_ENV", "development")

    from app.main import create_app

    schema = create_app().openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
