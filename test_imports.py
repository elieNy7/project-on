import sys
sys.path.insert(0, '.')

try:
    from app.ui import theme
    print('theme OK')
    from app.ui.sidebar import Sidebar
    print('sidebar OK')
    from app.ui.library_panel import LibraryPanel
    print('library_panel OK')
    from app.ui.bible_tab import BibleTab
    print('bible_tab OK')
    from app.ui.hymns_tab import HymnsTab
    print('hymns_tab OK')
    from app.ui.sermons_tab import SermonsTab
    print('sermons_tab OK')
    from app.ui.expose_tab import ExposeTab
    print('expose_tab OK')
    from app.ui.settings_tab import SettingsTab
    print('settings_tab OK')
    from app.ui.preview_panel import PreviewPanel
    print('preview_panel OK')
    from app.ui.status_bar import StatusBar
    print('status_bar OK')
    from app.ui.main_window import MainWindow
    print('main_window OK')
    print('ALL IMPORTS SUCCESSFUL')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
