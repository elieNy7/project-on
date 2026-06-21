import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.append("d:/Project/Project-On")
sys.path.append("f:/Project/Project-On")

from PyQt6.QtWidgets import QApplication

from app.database.connection import Database, DatabaseConfig
from app.utils.playlist_model import PlaylistRoles
from app.utils.project_on_controller import ProjectOnController

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class TestPlaylistFeatures(unittest.TestCase):
    def setUp(self):
        # Create temp directories
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test.db"
        self.presentation_dir = Path(self.test_dir) / "presentation"
        self.presentation_dir.mkdir()

        # Initialize Database
        self.db_config = DatabaseConfig(db_path=self.db_path)
        self.db = Database(self.db_config)
        self.db.initialize()

        # Initialize Controller
        self.controller = ProjectOnController(self.db, self.presentation_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_persistence(self):
        print("\n--- Testing Persistence ---")
        # Add items
        self.controller.add_to_playlist("bible", "Gen 1:1", "In the beginning...")
        self.controller.add_to_playlist("hymn", "Hymn 1", "Amazing Grace")

        # Verify in memory
        self.assertEqual(self.controller.playlist_model.flat_row_count(), 2)

        # Verify in DB
        with self.db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM playlist_item").fetchone()[0]
            self.assertEqual(count, 2)

        # Restart Controller (Simulate App Restart)
        new_controller = ProjectOnController(self.db, self.presentation_dir)
        self.assertEqual(new_controller.playlist_model.flat_row_count(), 2)
        slide1 = new_controller.playlist_model.slide_at(0)
        self.assertEqual(slide1.reference, "Gen 1:1")
        print("Persistence Check Passed")

    def test_folders(self):
        print("\n--- Testing Folders ---")
        # Create folder
        idx = self.controller.create_folder("Service AM")
        self.assertTrue(idx.isValid())

        # Add item to folder
        self.controller.add_to_playlist(
            "bible", "John 3:16", "For God so loved...", parent=idx
        )

        # Check hierarchy
        new_controller = ProjectOnController(self.db, self.presentation_dir)
        folders = new_controller.playlist_model.get_folders()
        self.assertEqual(len(folders), 1)
        self.assertEqual(folders[0][0], "Service AM")

        # Verify item is inside folder
        # We need to find the folder item in the model and check its children
        root = new_controller.playlist_model.invisibleRootItem()
        folder_item = root.child(0)
        self.assertEqual(folder_item.rowCount(), 1)
        child = folder_item.child(0)
        self.assertTrue("John 3:16" in child.text())
        print("Folder Check Passed")

    def test_reordering(self):
        print("\n--- Testing Reordering ---")
        # Add 3 items
        self.controller.add_to_playlist("custom", "1", "One")
        self.controller.add_to_playlist("custom", "2", "Two")
        self.controller.add_to_playlist("custom", "3", "Three")

        model = self.controller.playlist_model
        root = model.invisibleRootItem()

        # Initial order
        self.assertEqual(root.child(0).data(PlaylistRoles.ReferenceRole), "1")
        self.assertEqual(root.child(1).data(PlaylistRoles.ReferenceRole), "2")
        self.assertEqual(root.child(2).data(PlaylistRoles.ReferenceRole), "3")

        # Move "2" (index 1) Up to index 0
        index_to_move = model.index(1, 0)
        success = self.controller.move_index(index_to_move, up=True)
        self.assertTrue(success)

        # Check new order in model
        self.assertEqual(root.child(0).data(PlaylistRoles.ReferenceRole), "2")
        self.assertEqual(root.child(1).data(PlaylistRoles.ReferenceRole), "1")

        # Check DB Sort Order
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT reference, sort_order FROM playlist_item ORDER BY sort_order"
            ).fetchall()
            refs = [r[0] for r in rows]
            self.assertEqual(refs, ["2", "1", "3"])

        print("Reordering Check Passed")

    def test_undo(self):
        print("\n--- Testing Undo ---")
        self.controller.add_to_playlist("custom", "UndoMe", "Text")
        self.assertEqual(self.controller.playlist_model.flat_row_count(), 1)

        self.controller.undo()
        self.assertEqual(self.controller.playlist_model.flat_row_count(), 0)

        with self.db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM playlist_item").fetchone()[0]
            self.assertEqual(count, 0)
        print("Undo Check Passed")

    @unittest.skip("Export/Import deprecated in controller")
    def test_export_import(self):
        print("\n--- Testing Export/Import ---")
        self.controller.create_folder("My Folder")
        self.controller.add_to_playlist("custom", "Slide", "Text")

        export_path = Path(self.test_dir) / "playlist.json"

        # Export
        self.controller.export_playlist(export_path)
        self.assertTrue(export_path.exists())

        # Clear
        self.controller.clear_playlist()
        self.assertEqual(self.controller.playlist_model.flat_row_count(), 0)

        # Import
        self.controller.import_playlist(export_path)

        # Verify restored
        items = self.controller.playlist_model.flat_row_count()
        folders = len(self.controller.playlist_model.get_folders())
        self.assertEqual(items, 1)
        self.assertEqual(folders, 1)
        print("Export/Import Check Passed")

    def test_folder_boundary_navigation(self):
        print("\n--- Testing Folder Boundary Navigation ---")
        
        # Create folder A
        idx_a = self.controller.create_folder("Folder A")
        self.controller.add_to_playlist("custom", "A1", "Text A1", parent=idx_a)
        self.controller.add_to_playlist("custom", "A2", "Text A2", parent=idx_a)
        
        # Create folder B
        idx_b = self.controller.create_folder("Folder B")
        self.controller.add_to_playlist("custom", "B1", "Text B1", parent=idx_b)
        
        # We have 3 flat slides: A1 (row 0), A2 (row 1), B1 (row 2)
        self.assertEqual(self.controller.playlist_model.flat_row_count(), 3)
        
        # Select A1 (row 0)
        self.controller.set_current_row(0)
        self.assertEqual(self.controller.current_row(), 0)
        
        # next_slide should go to A2 (row 1) since they are in the same folder A
        self.controller.next_slide()
        self.assertEqual(self.controller.current_row(), 1)
        
        # next_slide should STOP at A2 (row 1) and NOT go to B1 (row 2) because B1 is in folder B
        self.controller.next_slide()
        self.assertEqual(self.controller.current_row(), 1)
        
        # prev_slide should go back to A1 (row 0)
        self.controller.prev_slide()
        self.assertEqual(self.controller.current_row(), 0)
        
        # prev_slide should STOP at A1 (row 0) and NOT go anywhere else
        self.controller.prev_slide()
        self.assertEqual(self.controller.current_row(), 0)
        
        print("Folder Boundary Navigation Passed")


if __name__ == "__main__":
    unittest.main()
