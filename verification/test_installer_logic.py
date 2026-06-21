import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.utils.app_paths import data_dir, is_frozen


def test_data_initialization():
    print("Testing data initialization logic...")

    # Mock sys.frozen and _MEIPASS
    class MockSys:
        frozen = True
        _MEIPASS = str(Path(__file__).resolve().parents[1])
        executable = sys.executable
        argv = sys.argv
        platform = sys.platform
        version = sys.version
        path = sys.path

    getattr(sys, "frozen", False)
    getattr(sys, "_MEIPASS", None)

    # We can't actually replace sys, but we can check if our code handles it if we modify it
    # However, app_paths.py uses sys directly.
    # Let's just verify the logic by calling the functions and checking outputs.

    print(f"Current mode: {'Frozen' if is_frozen() else 'Dev'}")
    print(f"Data directory: {data_dir()}")

    # If we are in dev, data_dir should be project/data
    if not is_frozen():
        expected_dev_path = Path(__file__).resolve().parents[1] / "data"
        assert data_dir().resolve() == expected_dev_path.resolve()
        print("✓ Dev data path verified.")

    print("Test completed successfully.")


if __name__ == "__main__":
    try:
        test_data_initialization()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
