#!/usr/bin/env python3
"""
Configuration management for WMS CLI.
Handles init, loading/saving config, and capabilities caching.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, List
from datetime import datetime
from shutil import copy2
import logging

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path.home() / ".wms"
CONFIG_FILE = CONFIG_DIR / "config.json"
CAPS_CACHE_FILE = CONFIG_DIR / "capabilities_cache.xml"
SERVERS_DIR = CONFIG_DIR / "servers"


@dataclass
class ServerConfig:
    """Configuration for a named WMS server"""
    name: str                              # User-friendly name (e.g., "prod", "test")
    url: str                               # WMS server URL (may be internal/tunneled)
    capabilities_path: Optional[str] = None  # Path to cached capabilities XML
    last_fetched: Optional[str] = None     # ISO timestamp of last fetch
    
    # Special access options
    requires_manual_fetch: bool = False    # True if caps must be provided manually (CAC, etc.)
    ssh_tunnel: Optional[str] = None       # SSH tunnel config
    notes: Optional[str] = None            # User notes (e.g., "Requires VPN connection")
    
    # Source tracking
    caps_source: str = "fetched"           # "fetched", "manual", "file"
    original_caps_file: Optional[str] = None  # If caps came from user-provided file
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ServerConfig':
        """Create from dictionary."""
        return cls(**data)
    
    def has_capabilities(self) -> bool:
        """Check if this server has cached capabilities."""
        if not self.capabilities_path:
            return False
        return Path(self.capabilities_path).exists()


@dataclass
class WMSConfig:
    """WMS CLI configuration"""
    source_type: str = ""  # "file" or "server"
    source_path: str = ""  # Local file path or server URL
    server_url: str = ""   # Server URL for actual requests
    output_dir: str = "."  # Default output directory
    default_format: str = "image/png"
    cache_ttl: int = 600   # Cache TTL in seconds (10 min)
    servers: Dict[str, dict] = field(default_factory=dict)  # name → ServerConfig as dict

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
        
        # Handle old configs without servers field
        if 'servers' not in data:
            data['servers'] = {}
        
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


# ============================================================================
# Multi-Server Management Functions
# ============================================================================

def _sanitize_name(name: str) -> str:
    """Sanitize server name for use in filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


def _ensure_servers_dir():
    """Create servers directory if it doesn't exist."""
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)


def add_server(
    name: str,
    url: str,
    fetch_caps: bool = True,
    caps_file: Optional[str] = None,
    ssh_tunnel: Optional[str] = None,
    notes: Optional[str] = None
) -> ServerConfig:
    """
    Register a named WMS server.
    
    Args:
        name: Unique name for this server (e.g., "prod", "test")
        url: WMS server URL (the URL to use for actual requests)
        fetch_caps: If True, fetch and cache capabilities immediately
        caps_file: Path to local capabilities XML file (for auth-protected servers)
        ssh_tunnel: SSH tunnel specification
        notes: User notes about this server
    
    Returns:
        ServerConfig for the added server
    
    Raises:
        ValueError: If name already exists
        FileNotFoundError: If caps_file provided but doesn't exist
    """
    config = load_config()
    
    if name in config.servers:
        raise ValueError(f"Server '{name}' already exists. Use 'wms server remove {name}' first.")
    
    _ensure_servers_dir()
    
    server_config = ServerConfig(
        name=name,
        url=url,
        ssh_tunnel=ssh_tunnel,
        notes=notes
    )
    
    # Handle capabilities
    if caps_file:
        # User provided a capabilities file
        caps_path = Path(caps_file).expanduser().resolve()
        if not caps_path.exists():
            raise FileNotFoundError(f"Capabilities file not found: {caps_path}")
        
        # Validate XML
        from .wms_parser import parse_capabilities
        with open(caps_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        parse_capabilities(xml_content)  # Will raise if invalid
        
        # Copy to cache
        cache_file = SERVERS_DIR / f"{_sanitize_name(name)}_capabilities.xml"
        copy2(caps_path, cache_file)
        
        server_config.capabilities_path = str(cache_file)
        server_config.last_fetched = datetime.now().isoformat()
        server_config.caps_source = "manual"
        server_config.original_caps_file = str(caps_path)
        server_config.requires_manual_fetch = True
        
    elif fetch_caps:
        # Fetch from server
        try:
            import requests
            params = {
                'SERVICE': 'WMS',
                'VERSION': '1.3.0',
                'REQUEST': 'GetCapabilities'
            }
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Validate XML
            from .wms_parser import parse_capabilities
            parse_capabilities(response.text)
            
            # Cache it
            cache_file = SERVERS_DIR / f"{_sanitize_name(name)}_capabilities.xml"
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            server_config.capabilities_path = str(cache_file)
            server_config.last_fetched = datetime.now().isoformat()
            server_config.caps_source = "fetched"
            
        except Exception as e:
            raise ValueError(f"Failed to fetch capabilities from {url}: {e}")
    else:
        # No fetch - register URL only
        server_config.requires_manual_fetch = True
    
    # Save to config
    config.servers[name] = server_config.to_dict()
    save_config(config)
    
    return server_config


def remove_server(name: str) -> bool:
    """
    Remove a registered server.
    
    Args:
        name: Server name to remove
    
    Returns:
        True if removed, False if not found
    """
    config = load_config()
    
    if name not in config.servers:
        return False
    
    # Get server config to find cached file
    server_data = config.servers[name]
    if server_data.get('capabilities_path'):
        caps_path = Path(server_data['capabilities_path'])
        if caps_path.exists():
            caps_path.unlink()
    
    # Remove from config
    del config.servers[name]
    save_config(config)
    
    return True


def list_servers() -> List[ServerConfig]:
    """
    List all registered servers.
    
    Returns:
        List of ServerConfig objects
    """
    config = load_config()
    return [ServerConfig.from_dict(data) for data in config.servers.values()]


def get_server(name: str) -> Optional[ServerConfig]:
    """
    Get a server by name.
    
    Args:
        name: Server name
    
    Returns:
        ServerConfig or None if not found
    """
    config = load_config()
    
    if name not in config.servers:
        return None
    
    return ServerConfig.from_dict(config.servers[name])


def get_server_capabilities(name: str, refresh: bool = False) -> Optional['WMSCapabilities']:
    """
    Get parsed capabilities for a named server.
    
    Args:
        name: Server name
        refresh: If True, fetch fresh capabilities from server
    
    Returns:
        Parsed WMSCapabilities object or None if no capabilities
    
    Raises:
        ValueError: If server not found
    """
    from .wms_parser import parse_capabilities
    
    server = get_server(name)
    if not server:
        raise ValueError(f"Server not found: {name}")
    
    if refresh and not server.requires_manual_fetch:
        # Refresh from server
        fetch_server_capabilities(name)
        server = get_server(name)
    
    if not server.has_capabilities():
        return None
    
    with open(server.capabilities_path, 'r', encoding='utf-8') as f:
        xml_content = f.read()
    
    return parse_capabilities(xml_content)


def fetch_server_capabilities(name: str, caps_file: Optional[str] = None) -> ServerConfig:
    """
    Fetch/refresh capabilities for a server.
    
    Args:
        name: Server name
        caps_file: Optional path to local capabilities file
    
    Returns:
        Updated ServerConfig
    
    Raises:
        ValueError: If server not found or fetch fails
    """
    config = load_config()
    
    if name not in config.servers:
        raise ValueError(f"Server not found: {name}")
    
    server = ServerConfig.from_dict(config.servers[name])
    _ensure_servers_dir()
    
    if caps_file:
        # Update from local file
        caps_path = Path(caps_file).expanduser().resolve()
        if not caps_path.exists():
            raise FileNotFoundError(f"File not found: {caps_path}")
        
        # Validate XML
        from .wms_parser import parse_capabilities
        with open(caps_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        parse_capabilities(xml_content)
        
        # Copy to cache
        cache_file = SERVERS_DIR / f"{_sanitize_name(name)}_capabilities.xml"
        copy2(caps_path, cache_file)
        
        server.capabilities_path = str(cache_file)
        server.last_fetched = datetime.now().isoformat()
        server.caps_source = "manual"
        server.original_caps_file = str(caps_path)
        
    else:
        # Fetch from server URL
        if server.requires_manual_fetch:
            raise ValueError(
                f"Server '{name}' requires manual fetch. "
                f"Use --caps-file to provide a capabilities file, "
                f"or use 'wms server fetch-interactive {name}'."
            )
        
        import requests
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetCapabilities'
        }
        response = requests.get(server.url, params=params, timeout=30)
        response.raise_for_status()
        
        # Validate XML
        from .wms_parser import parse_capabilities
        parse_capabilities(response.text)
        
        # Cache it
        cache_file = SERVERS_DIR / f"{_sanitize_name(name)}_capabilities.xml"
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        server.capabilities_path = str(cache_file)
        server.last_fetched = datetime.now().isoformat()
        server.caps_source = "fetched"
    
    # Save updated config
    config.servers[name] = server.to_dict()
    save_config(config)
    
    return server


def update_server_caps_from_file(name: str, caps_file: str) -> ServerConfig:
    """
    Update capabilities for a server from a local file.
    
    Convenience wrapper around fetch_server_capabilities.
    
    Args:
        name: Server name
        caps_file: Path to capabilities XML file
    
    Returns:
        Updated ServerConfig
    """
    return fetch_server_capabilities(name, caps_file=caps_file)
