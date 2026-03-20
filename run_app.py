import threading
import uvicorn
import webview
import time
import sys
import os
import shutil

def get_resource_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.abspath(sys._MEIPASS)
    return os.path.dirname(os.path.abspath(__file__))


def get_runtime_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# Add backend to path so it can be imported
backend_path = os.path.join(get_resource_root(), 'webapp', 'backend')
if os.path.exists(backend_path):
    sys.path.append(backend_path)

def run_server():
    import main
    uvicorn.run(main.app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    # --- WebView2 cache management ---
    # Use a known storage path so we can manage the cache
    app_dir = get_runtime_root()
    storage_path = os.path.join(app_dir, '.webview_data')

    # Clear stale cache on startup to ensure CSS/JS updates are always picked up.
    # WebView2 aggressively caches static assets and a stale cache can cause
    # the UI to render with outdated stylesheets.
    cache_dir = os.path.join(storage_path, 'EBWebView', 'Default', 'Cache')
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
        except Exception:
            pass  # Not critical; will work next restart

    # 1. Start FastAPI server in a separate daemon thread
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

    # Give the server a moment to start up
    time.sleep(1)

    # 2. Create and start native application window pointing to the local React/HTML frontend
    window = webview.create_window(
        title='Chronos',
        url='http://127.0.0.1:8000', # FastAPI serves the frontend on root
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600),
        background_color='#0b0f19' # Matches dark theme bg
    )
    
    # Start the webview application event loop
    # gui='edgechromium' forces the modern Chromium-based renderer (not MSHTML)
    # storage_path stores WebView2 profile data (cookies, localStorage, theme prefs)
    webview.start(gui='edgechromium', private_mode=False, storage_path=storage_path)
