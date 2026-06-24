import os
import tempfile
import unittest
from pathlib import Path

from nova_runtime.http_utils import content_type, encode_json, resolve_confined_path


class HttpUtilsTests(unittest.TestCase):
    def test_resolves_file_inside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "index.html"
            target.write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_confined_path(root, "/index.html"), target)

    def test_resolves_root_to_index_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(resolve_confined_path(root, "/"), root / "index.html")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_confined_path(root, "/../secret.txt")

    def test_rejects_url_encoded_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_confined_path(root, "/%2e%2e/secret.txt")

    @unittest.skipUnless(os.name == "nt", "Windows path semantics")
    def test_rejects_encoded_backslash_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_confined_path(root, "/..%5csecret.txt")

    @unittest.skipUnless(os.name == "nt", "Windows path semantics")
    def test_rejects_windows_absolute_paths(self):
        attempts = (
            r"C:\escape.txt",
            r"\\server\share\escape.txt",
            r"\\?\C:\escape.txt",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for request_path in attempts:
                with self.subTest(request_path=request_path):
                    with self.assertRaises(ValueError):
                        resolve_confined_path(root, request_path)

    def test_content_type_uses_known_mime_and_binary_fallback(self):
        self.assertEqual(content_type(Path("index.html")), "text/html")
        self.assertEqual(
            content_type(Path("payload.unknown-extension")),
            "application/octet-stream",
        )

    def test_encode_json_emits_literal_utf8_for_non_ascii_text(self):
        encoded = encode_json({"message": "café"})
        self.assertIn("café".encode("utf-8"), encoded)
        self.assertNotIn(b"\\u", encoded)


if __name__ == "__main__":
    unittest.main()
