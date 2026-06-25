from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

_SPEC = importlib.util.spec_from_file_location("_nova_training_dataset_impl", SRC / "nova_training_dataset.py")
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Could not load src/nova_training_dataset.py")
_IMPL = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_IMPL)

clean_record = _IMPL.clean_record
grouped_split = _IMPL.grouped_split
build_dataset = _IMPL.build_dataset
main = _IMPL.main

__all__ = ["clean_record", "grouped_split", "build_dataset", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
