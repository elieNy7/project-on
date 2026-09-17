"""Preuves minimales d'isolation des chemins et des alias importés."""

from app.utils import app_paths
from app.utils.app_paths import data_dir as imported_data_dir
from app.utils.app_paths import user_data_dir as imported_user_dir


def test_01_writes_only_in_current_tmp_path(tmp_path):
    for directory in (app_paths.user_data_dir(), app_paths.data_dir()):
        assert directory.is_relative_to(tmp_path)
        (directory / "isolation-marker.txt").write_text("first test", encoding="utf-8")
    assert imported_data_dir() == app_paths.data_dir()
    assert imported_user_dir() == app_paths.user_data_dir()


def test_02_previous_test_files_are_absent(tmp_path):
    for directory in (app_paths.user_data_dir(), app_paths.data_dir()):
        assert directory.is_relative_to(tmp_path)
        assert not (directory / "isolation-marker.txt").exists()
    assert imported_data_dir() == app_paths.data_dir()
    assert imported_user_dir() == app_paths.user_data_dir()
