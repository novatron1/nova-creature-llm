import tempfile
import unittest
from pathlib import Path

from nova_runtime.http_utils import resolve_confined_path


class HttpUtilsTests(unittest.TestCase):
    def test_resolves_file_inside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "index.html"
            target.write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_confined_path(root, "/index.html"), target)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_confined_path(root, "/../secret.txt")


if __name__ == "__main__":
    unittest.main()
