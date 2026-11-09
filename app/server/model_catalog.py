"""The model catalog and model name matching.

The catalog is the ``models`` list in ``data/rules.json``. Each entry names a
model id, its display name and its aliases. ``normalize_model`` turns any name a
transcript or a setting can carry into a catalog id and says which form the name
had. This is the one piece of the old resolver the usage views and prices need.

Only ``load_rules`` and ``load_catalog`` read a file. Nothing here reads a clock
or the environment.
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
RULES_PATH = DATA_DIR / "rules.json"

# A catalog entry is a JSON object from rules.json. It holds mixed value types
# (strings, lists, null, quote objects), so its values stay Any.
CatalogEntry = Mapping[str, Any]
Catalog = Sequence[CatalogEntry]

_NAME_PATTERNS = (
    (re.compile(r"^(.+)\[1m\]$"), "context_1m"),
    (re.compile(r"^(.+)-\d{8}$"), "dated"),
    (re.compile(r"^(?:[a-z0-9-]+\.)?anthropic\.(.+)-v\d+:\d+$"), "provider"),
    (re.compile(r"^(.+)@\d{8}$"), "provider"),
)


def load_rules(path: Path | str | None = None) -> dict[str, Any]:
    """Return the rules.json document. It does not validate.

    Args:
        path: A rules file. The default is ``data/rules.json`` beside this module.

    Returns:
        The parsed document.
    """
    target = Path(path) if path is not None else RULES_PATH
    with target.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(path: Path | str | None = None) -> list[CatalogEntry]:
    """Return the ``models`` list of the rules file, aliases included.

    Args:
        path: A rules file. The default is ``data/rules.json`` beside this module.

    Returns:
        The catalog entries in file order.
    """
    return list(load_rules(path)["models"])


def normalize_model(name: object, catalog: Catalog) -> tuple[str | None, str | None]:
    """Return ``(catalog id, name form)`` for a model name, or ``(None, None)``.

    Forms are canonical (the catalog id), alias, dated (``<id>-YYYYMMDD``),
    context_1m (``<id>[1m]``) and provider
    (``<region>.anthropic.<id>-v<n>:<n>`` or ``<id>@<date>``).

    Args:
        name: A model name from a transcript or a setting.
        catalog: The catalog entries.

    Returns:
        The catalog id and the form of the name, or two Nones.
    """
    if not isinstance(name, str) or name == "":
        return None, None
    ids = {m["id"] for m in catalog}
    if name in ids:
        return name, "canonical"
    for model in catalog:
        if name in model.get("aliases", []):
            return model["id"], "alias"
    for pattern, form in _NAME_PATTERNS:
        match = pattern.match(name)
        if match and match.group(1) in ids:
            return match.group(1), form
    return None, None
