"""Export the OpenAPI schema offline, for the generated TypeScript types.

Run ``python openapi_export.py`` to write ``app/web/src/api/openapi.json``. It builds
the app in process with dummy settings, so it needs no network and no running server.
The file has sorted keys, 2-space indent and a trailing newline, so a rerun produces
the same bytes. ``npm run api-types`` then turns it into ``schema.d.ts``.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from main import Settings, build_app

DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent / "web" / "src" / "api" / "openapi.json"
)


def build_schema() -> dict[str, object]:
    """Build the OpenAPI schema from an app made with dummy settings.

    Returns:
        The schema as a plain dict.
    """
    settings = Settings(
        port=1,
        data_dir=Path("/work/data"),
        dist_dir=Path("/work/dist"),
        # Edits on, so the schema holds preview, save and undo. A server with edits off
        # answers those paths with edits_off and has no schema for them.
        edits="on",
    )
    return build_app(settings).openapi()


def render_schema() -> str:
    """Return the schema as the text that is written to disk."""
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


def write_schema(out: Path) -> None:
    """Write the schema file.

    Args:
        out: The file to write.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_schema(), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the export from the command line.

    Args:
        argv: Arguments without the program name.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(prog="openapi_export.py")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    write_schema(parser.parse_args(argv).out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
