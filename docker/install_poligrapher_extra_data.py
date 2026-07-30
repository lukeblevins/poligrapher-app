"""Install static PoliGraph data omitted from the retrained model bundle."""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests

PHRASE_MAP_URL = (
    "https://raw.githubusercontent.com/lukeblevins/PoliGraph/"
    "8474ff65d7607af04749d9b0c6a918ee7f44c49b/"
    "poligrapher/extra-data/phrase_map.yml"
)
PHRASE_MAP_SHA256 = "cae2e134e550884583cad6b9b021f862cce9e75801b5c7f26251090b44f9c127"


def main() -> None:
    import poligrapher

    destination = Path(poligrapher.__file__).parent / "extra-data" / "phrase_map.yml"
    response = requests.get(PHRASE_MAP_URL, timeout=60)
    response.raise_for_status()
    payload = response.content
    digest = hashlib.sha256(payload).hexdigest()
    if digest != PHRASE_MAP_SHA256:
        raise RuntimeError(
            f"Unexpected PoliGraph phrase map digest: {digest}; "
            f"expected {PHRASE_MAP_SHA256}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    print(f"Installed verified PoliGraph phrase map at {destination}")


if __name__ == "__main__":
    main()
