import tempfile
import unittest
from pathlib import Path

from backend.storage import JsonStore, safe_id


class JsonStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tempdir.name))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_workspace_is_initialized(self):
        self.assertEqual(self.store.active_workspace(), "writing")
        self.assertTrue((self.store.workspace_path("writing") / "brain" / "style_profile.json").exists())

    def test_entity_round_trip_and_archive(self):
        draft = {"id": "draft_123", "title": "Test", "content": "Isi"}
        self.store.save_entity("writing", "drafts", draft)
        self.assertEqual(self.store.get_entity("writing", "drafts", "draft_123")["title"], "Test")
        self.store.delete_entity("writing", "drafts", "draft_123")
        self.assertFalse((self.store.workspace_path("writing") / "drafts" / "draft_123.json").exists())

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            safe_id("../../etc/passwd")

    def test_snapshot_contains_data(self):
        snapshot = self.store.create_snapshot()
        self.assertTrue((self.store.root / "snapshots" / snapshot["file"]).exists())


if __name__ == "__main__":
    unittest.main()
