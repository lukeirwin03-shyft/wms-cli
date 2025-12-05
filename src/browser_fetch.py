#!/usr/bin/env python3
"""
Browser-based capabilities fetching with download watching.
For CAC/auth-protected WMS servers.
"""

import webbrowser
import time
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Try to import watchdog, provide helpful error if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileCreatedEvent = None


class CapabilitiesDownloadHandler(FileSystemEventHandler):
    """Watch for WMS capabilities XML files being downloaded."""
    
    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback
        self.found_file: Optional[str] = None
    
    def on_created(self, event):
        if not event or getattr(event, 'is_directory', False):
            return
        
        file_path = event.src_path
        
        # Check if it's an XML file
        if not file_path.lower().endswith('.xml'):
            return
        
        # Wait a moment for file to finish writing
        time.sleep(0.5)
        
        # Verify it's a WMS capabilities document
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read first 2KB to check for WMS markers
                content = f.read(2048)
                
            if 'WMS_Capabilities' in content or 'WMT_MS_Capabilities' in content:
                logger.info(f"Found capabilities file: {file_path}")
                self.found_file = file_path
                self.callback(file_path)
        except Exception as e:
            logger.debug(f"Could not read {file_path}: {e}")


def check_watchdog_available():
    """Check if watchdog is available, raise helpful error if not."""
    if not WATCHDOG_AVAILABLE:
        raise ImportError(
            "The 'watchdog' package is required for browser-based fetch.\n"
            "Install it with: pip install watchdog>=3.0.0\n"
            "Or use 'wms server update-caps <name> <file>' to manually import capabilities."
        )


def fetch_via_browser(
    url: str,
    watch_dir: str = "~/Downloads",
    timeout: int = 300,
    on_found: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    Open URL in browser and watch for downloaded capabilities file.
    
    Args:
        url: Full GetCapabilities URL to open
        watch_dir: Directory to watch for downloads (default: ~/Downloads)
        timeout: Seconds to wait before giving up (default: 300 = 5 min)
        on_found: Optional callback when file is found
    
    Returns:
        Path to downloaded file, or None if timeout
    
    Example:
        file_path = fetch_via_browser(
            "https://afweather.mil/wms?SERVICE=WMS&REQUEST=GetCapabilities",
            watch_dir="~/Downloads",
            timeout=300
        )
    """
    check_watchdog_available()
    
    watch_path = Path(watch_dir).expanduser().resolve()
    
    if not watch_path.exists():
        raise ValueError(f"Watch directory does not exist: {watch_path}")
    
    found_file = None
    
    def on_file_found(path: str):
        nonlocal found_file
        found_file = path
        if on_found:
            on_found(path)
    
    # Set up file watcher
    handler = CapabilitiesDownloadHandler(on_file_found)
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=False)
    observer.start()
    
    logger.info(f"Watching {watch_path} for capabilities XML...")
    
    # Open browser
    logger.info(f"Opening browser to: {url}")
    webbrowser.open(url)
    
    # Wait for file or timeout
    start_time = time.time()
    try:
        while found_file is None and (time.time() - start_time) < timeout:
            time.sleep(1)
            
            # Print progress every 30 seconds
            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 30 == 0:
                remaining = timeout - elapsed
                logger.info(f"Still waiting... ({remaining}s remaining)")
    finally:
        observer.stop()
        observer.join()
    
    return found_file


def build_capabilities_url(base_url: str, version: str = "1.3.0") -> str:
    """
    Build a GetCapabilities URL from a base WMS URL.
    
    Args:
        base_url: Base WMS server URL
        version: WMS version (default: 1.3.0)
    
    Returns:
        Full GetCapabilities URL
    """
    # Remove existing query string if present
    base_url = base_url.split('?')[0]
    
    return f"{base_url}?SERVICE=WMS&VERSION={version}&REQUEST=GetCapabilities"

