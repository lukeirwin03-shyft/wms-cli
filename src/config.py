#!/usr/bin/env python3
"""
Configuration management for WMS CLI.
Handles init, loading/saving config, and capabilities caching.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path.home() / ".wms"
CONFIG_FILE = CONFIG_DIR / "config.json"
CAPS_CACHE_FILE = CONFIG_DIR / "capabilities_cache.xml"


@dataclass
class WMSConfig:
    """WMS CLI configuration"""
    source_type: str = ""  # "file" or "server"
    source_path: str = ""  # Local file path or server URL
    server_url: str = ""   # Server URL for actual requests
    output_dir: str = "."  # Default output directory
    default_format: str = "image/png"
    cache_ttl: int = 600   # Cache TTL in seconds (10 min)

    def is_initialized(self) -> bool:
        """Check if config has been initialized"""
        return bool(self.source_path)


def ensure_config_dir():
    """Create config directory if it doesn't exist"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> WMSConfig:
    """
    Load configuration from disk.

    Returns:
        WMSConfig object (empty if not initialized)
    """
    if not CONFIG_FILE.exists():
        return WMSConfig()

    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        return WMSConfig(**data)
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
        return WMSConfig()


def save_config(config: WMSConfig):
    """
    Save configuration to disk.

    Args:
        config: WMSConfig object to save
    """
    ensure_config_dir()

    with open(CONFIG_FILE, 'w') as f:
        json.dump(asdict(config), f, indent=2)

    logger.info(f"Config saved to {CONFIG_FILE}")


def get_capabilities_xml(config: WMSConfig) -> str:
    """
    Get capabilities XML content based on config.

    For local files, reads directly.
    For servers, uses cached version or fetches fresh.

    Args:
        config: WMSConfig with source information

    Returns:
        XML content as string

    Raises:
        FileNotFoundError: If local file doesn't exist
        ValueError: If config not initialized
    """
    if not config.is_initialized():
        raise ValueError("WMS not initialized. Run 'wms init <source>' first.")

    if config.source_type == "file":
        # Read from local file
        path = Path(config.source_path)
        if not path.exists():
            raise FileNotFoundError(f"Capabilities file not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    elif config.source_type == "server":
        # Check cache first
        if CAPS_CACHE_FILE.exists():
            # TODO: Check cache TTL
            with open(CAPS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return f.read()

        # Fetch from server
        from .wms_client import WMSClient

        client = WMSClient(config.source_path)
        caps = client.get_capabilities()

        # We need the raw XML, so fetch again
        import requests
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetCapabilities'
        }
        response = requests.get(config.source_path, params=params)
        response.raise_for_status()

        # Cache it
        ensure_config_dir()
        with open(CAPS_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(response.text)

        return response.text

    else:
        raise ValueError(f"Unknown source type: {config.source_type}")


def init_from_file(file_path: str, server_url: Optional[str] = None) -> WMSConfig:
    """
    Initialize config from a local capabilities file.

    Args:
        file_path: Path to capabilities XML file
        server_url: Optional server URL for requests

    Returns:
        Initialized WMSConfig
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Parse to validate and extract service URL
    from .wms_parser import parse_capabilities

    with open(path, 'r', encoding='utf-8') as f:
        xml_content = f.read()

    caps = parse_capabilities(xml_content)

    # Use provided server URL, or extract from capabilities
    if not server_url:
        server_url = caps.service_url or ""

    config = WMSConfig(
        source_type="file",
        source_path=str(path),
        server_url=server_url
    )

    save_config(config)

    return config


def init_from_server(server_url: str) -> WMSConfig:
    """
    Initialize config from a remote WMS server.

    Args:
        server_url: WMS server URL

    Returns:
        Initialized WMSConfig
    """
    from .wms_client import WMSClient

    # Fetch capabilities to validate
    client = WMSClient(server_url)
    caps = client.get_capabilities()

    # Fetch raw XML and cache it
    import requests
    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.3.0',
        'REQUEST': 'GetCapabilities'
    }
    response = requests.get(server_url, params=params)
    response.raise_for_status()

    ensure_config_dir()
    with open(CAPS_CACHE_FILE, 'w', encoding='utf-8') as f:
        f.write(response.text)

    config = WMSConfig(
        source_type="server",
        source_path=server_url,
        server_url=server_url
    )

    save_config(config)

    return config
