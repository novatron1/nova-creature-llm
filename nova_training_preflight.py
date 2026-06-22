from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_main():
    root = Path(__file__).resolve().parent
    src = root / "src"
    sys.path.insert(0, str(src))
    spec = importlib.util.spec_from_file_location(
        "_nova_training_preflight_impl",
        src / "nova_training_preflight.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load src/nova_training_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


if __name__ == "__main__":
    raise SystemExit(_load_main()())
