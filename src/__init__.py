"""
WMS CLI - Command-line tool for WMS queries with fuzzy search
"""

from .wms_parser import (
    parse_capabilities,
    WMSCapabilities,
    Layer,
    BoundingBox,
    Dimension,
    Style,
    WMSParser
)

from .wms_client import (
    WMSClient,
    create_client
)

from .fuzzy import (
    FuzzySearchEngine,
    SearchResult,
    LayerIndex
)

from .smart_resolver import (
    SmartQueryResolver,
    ResolvedQuery,
    AmbiguousQueryError
)

from .config import (
    load_config,
    save_config,
    init_from_file,
    init_from_server,
    WMSConfig
)

__all__ = [
    # Parser
    'parse_capabilities',
    'WMSCapabilities',
    'Layer',
    'BoundingBox',
    'Dimension',
    'Style',
    'WMSParser',
    # Client
    'WMSClient',
    'create_client',
    # Fuzzy search
    'FuzzySearchEngine',
    'SearchResult',
    'LayerIndex',
    # Resolver
    'SmartQueryResolver',
    'ResolvedQuery',
    'AmbiguousQueryError',
    # Config
    'load_config',
    'save_config',
    'init_from_file',
    'init_from_server',
    'WMSConfig',
]
