#!/usr/bin/env python3
"""
Configuration management for WMS CLI.
Handles init, loading/saving config, and capabilities caching.

Cache Strategy:
- Capabilities are cached in ~/.wms/capabilities_cache.xml
- Uses sliding window TTL: cache resets on each access
- Default TTL is 10 minutes (600 seconds)
- If you're actively using the tool, cache stays fresh
- If you return after being away, cache expires and refreshes
"""

import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path.home() / ".wms"
CONFIG_FILE = CONFIG_DIR / "config.json"
CAPS_CACHE_FILE = CONFIG_DIR / "capabilities_cache.xml"
PROFILES_FILE = CONFIG_DIR / "profiles.json"

# Default cache TTL in seconds (10 minutes)
DEFAULT_CACHE_TTL = 600


@dataclass
class HammerProfile:
    """Hammer performance test profile"""
    name: str
    workers: int = 20
    timeout: int = 30
    retries: int = 0
    size: str = "medium"  # small, medium, large
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'HammerProfile':
        return cls(**data)


# Built-in profiles
BUILTIN_PROFILES = {
    "gentle": HammerProfile(
        name="gentle",
        workers=5,
        timeout=30,
        retries=1,
        size="small",
        description="Low concurrency, small images - for slow/limited servers"
    ),
    "balanced": HammerProfile(
        name="balanced",
        workers=10,
        timeout=20,
        retries=1,
        size="medium",
        description="Moderate load - good for most servers"
    ),
    "aggressive": HammerProfile(
        name="aggressive",
        workers=50,
        timeout=30,
        retries=0,
        size="large",
        description="High concurrency - for robust servers"
    ),
    "stress": HammerProfile(
        name="stress",
        workers=100,
        timeout=60,
        retries=0,
        size="large",
        description="Maximum load - stress testing only"
    ),
}


def load_profiles() -> dict:
    """Load custom profiles from disk."""
    profiles = dict(BUILTIN_PROFILES)  # Start with built-ins

    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, 'r') as f:
                custom = json.load(f)
            for name, data in custom.items():
                profiles[name] = HammerProfile.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load profiles: {e}")

    return profiles


def save_profile(profile: HammerProfile):
    """Save a custom profile to disk."""
    ensure_config_dir()

    # Load existing custom profiles
    custom = {}
    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, 'r') as f:
                custom = json.load(f)
        except Exception:
            pass

    # Add/update this profile
    custom[profile.name] = profile.to_dict()

    with open(PROFILES_FILE, 'w') as f:
        json.dump(custom, f, indent=2)

    logger.info(f"Profile '{profile.name}' saved to {PROFILES_FILE}")


def delete_profile(name: str) -> bool:
    """Delete a custom profile. Returns True if deleted."""
    if name in BUILTIN_PROFILES:
        return False  # Can't delete built-ins

    if not PROFILES_FILE.exists():
        return False

    try:
        with open(PROFILES_FILE, 'r') as f:
            custom = json.load(f)

        if name not in custom:
            return False

        del custom[name]

        with open(PROFILES_FILE, 'w') as f:
            json.dump(custom, f, indent=2)

        return True
    except Exception:
        return False


def get_profile(name: str) -> Optional[HammerProfile]:
    """Get a profile by name."""
    profiles = load_profiles()
    return profiles.get(name)


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


def is_cache_valid(cache_path: Path, ttl_seconds: int) -> bool:
    """
    Check if cache file exists and is within TTL.

    Args:
        cache_path: Path to cache file
        ttl_seconds: Maximum age in seconds

    Returns:
        True if cache exists and is not expired
    """
    if not cache_path.exists():
        return False

    try:
        mtime = cache_path.stat().st_mtime
        age = time.time() - mtime
        return age < ttl_seconds
    except OSError:
        return False


def touch_cache(cache_path: Path) -> None:
    """
    Touch cache file to reset its modification time (sliding window).

    Args:
        cache_path: Path to cache file
    """
    try:
        cache_path.touch()
        logger.debug(f"Cache touched: {cache_path}")
    except OSError as e:
        logger.warning(f"Failed to touch cache: {e}")


def clear_cache() -> bool:
    """
    Clear the capabilities cache.

    Returns:
        True if cache was cleared, False if it didn't exist
    """
    if CAPS_CACHE_FILE.exists():
        CAPS_CACHE_FILE.unlink()
        logger.info("Capabilities cache cleared")
        return True
    return False


def fetch_capabilities_xml(server_url: str, timeout: int = 30) -> str:
    """
    Fetch raw GetCapabilities XML from a WMS server.

    Args:
        server_url: WMS server base URL
        timeout: Request timeout in seconds

    Returns:
        Raw XML content as string

    Raises:
        requests.RequestException: On network error
    """
    import requests

    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.3.0',
        'REQUEST': 'GetCapabilities'
    }

    logger.info(f"Fetching capabilities from {server_url}")
    response = requests.get(server_url, params=params, timeout=timeout)
    response.raise_for_status()

    return response.text


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
    For servers, uses cached version with sliding window TTL.

    Cache behavior:
    - Cache is valid for config.cache_ttl seconds (default 10 min)
    - Each access "touches" the cache, resetting the TTL
    - If cache expires, fresh data is fetched from server

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
        ttl = config.cache_ttl if config.cache_ttl > 0 else DEFAULT_CACHE_TTL

        # Check if cache is valid (exists and not expired)
        if is_cache_valid(CAPS_CACHE_FILE, ttl):
            logger.debug(f"Using cached capabilities (TTL: {ttl}s)")
            with open(CAPS_CACHE_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            # Touch cache to reset sliding window TTL
            touch_cache(CAPS_CACHE_FILE)
            return content

        # Cache expired or doesn't exist - fetch fresh
        logger.info("Cache expired or missing, fetching fresh capabilities...")
        xml_content = fetch_capabilities_xml(config.source_path)

        # Save to cache
        ensure_config_dir()
        with open(CAPS_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        logger.debug(f"Cached capabilities to {CAPS_CACHE_FILE}")

        return xml_content

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

    Raises:
        requests.RequestException: On network error
        ValueError: If capabilities cannot be parsed
    """
    from .wms_parser import parse_capabilities

    # Fetch raw XML (single request)
    xml_content = fetch_capabilities_xml(server_url)

    # Parse to validate it's valid capabilities XML
    caps = parse_capabilities(xml_content)
    logger.info(f"Validated capabilities: {caps.service_title} ({len(caps.get_queryable_layers())} layers)")

    # Cache the XML
    ensure_config_dir()
    with open(CAPS_CACHE_FILE, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    config = WMSConfig(
        source_type="server",
        source_path=server_url,
        server_url=server_url
    )

    save_config(config)

    return config
