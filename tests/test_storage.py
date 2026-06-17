import tempfile
import unittest
from pathlib import Path

from backend.storage import JsonStore, safe_id
import backend.context as context_module


class JsonStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tempdir.name))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_workspace_is_initialized(self):
        self.assertEqual(self.store.active_workspace(), "writing")
        self.assertTrue((self.store.workspace_path("writing") / "brain" / "style_profile.json").exists())
        self.assertTrue((self.store.workspace_path("writing") / "brain" / "conversation_memory.json").exists())
        self.assertTrue((self.store.workspace_path("writing") / "brain" / "learning_proposals.json").exists())

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

    def test_permanent_delete_keeps_internal_backup(self):
        chat = {"id": "chat_123", "title": "Test", "messages": [], "archived": True}
        self.store.save_entity("writing", "chats", chat)
        self.store.permanently_delete_entity("writing", "chats", "chat_123")
        self.assertFalse((self.store.workspace_path("writing") / "chats" / "chat_123.json").exists())
        backups = list((self.store.root / "archive" / "deleted" / "chats" / "writing").glob("chat_123_*.json"))
        self.assertEqual(len(backups), 1)

    def test_cross_workspace_requires_explicit_name_and_action(self):
        original = context_module.store
        context_module.store = self.store
        try:
            second = self.store.create_workspace("Marketing")
            self.assertEqual(context_module.requested_workspaces("writing", "Marketing bagus"), [])
            self.assertEqual(
                context_module.requested_workspaces("writing", "Baca workspace Marketing"),
                [second["id"]],
            )
        finally:
            context_module.store = original

    def test_context_includes_inventory_and_relevant_draft(self):
        original = context_module.store
        context_module.store = self.store
        try:
            self.store.save_entity(
                "writing",
                "drafts",
                {"id": "draft_affiliate", "title": "Affiliate", "content": "Strategi soft selling produk."},
            )
            context, extras = context_module.build_chat_context("writing", "Apa isi draft affiliate?")
            self.assertIn("1 draft", context)
            self.assertIn("Strategi soft selling", context)
            self.assertEqual(extras, [])
        finally:
            context_module.store = original


if __name__ == "__main__":
    unittest.main()
