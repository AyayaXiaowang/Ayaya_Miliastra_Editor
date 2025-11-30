from __future__ import annotations

from pathlib import Path
from engine.nodes import get_node_registry


def main() -> None:
    reg = get_node_registry(Path('.').resolve())
    lib = reg.get_library()
    print(f"NODE_COUNT: {len(lib)}")
    cats = sorted({k.split('/')[0] for k in lib.keys()})
    print("CATEGORIES:", ", ".join(cats))


if __name__ == '__main__':
    main()


