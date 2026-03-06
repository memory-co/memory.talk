"""Source manager - manages all registered sync sources."""
import importlib
import pkgutil
from pathlib import Path
from typing import Optional

from sources.base import Source, SourceConfig


class SourceManager:
    """Manages all registered sync sources."""

    def __init__(self):
        """Initialize the source manager."""
        self._sources: dict[str, Source] = {}
        self._discover_sources()

    def _discover_sources(self):
        """Discover and load sources from the sources directory."""
        sources_path = Path(__file__).parent / "sources"

        if not sources_path.exists():
            return

        # Import the sources package
        try:
            import sys
            sources_package = str(Path(__file__).parent.name)

            # Add parent to path to enable imports
            parent = str(Path(__file__).parent.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)

            # Discover modules in sources/sources/
            for _, module_name, _ in pkgutil.iter_modules([str(sources_path)]):
                if module_name.startswith("_"):
                    continue

                try:
                    module = importlib.import_module(f"sources.sources.{module_name}")

                    # Find Source subclasses in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Source)
                            and attr is not Source
                        ):
                            # Instantiate with default config
                            config = SourceConfig(name=attr_name.lower())
                            source = attr(config)
                            self.register(source)
                except Exception as e:
                    print(f"Failed to load source {module_name}: {e}")

        except Exception as e:
            print(f"Failed to discover sources: {e}")

    def register(self, source: Source):
        """Register a source.

        Args:
            source: Source to register
        """
        self._sources[source.name] = source

    def unregister(self, name: str):
        """Unregister a source.

        Args:
            name: Source name
        """
        if name in self._sources:
            del self._sources[name]

    def get(self, name: str) -> Optional[Source]:
        """Get a source by name.

        Args:
            name: Source name

        Returns:
            Source or None if not found
        """
        return self._sources.get(name)

    def list_sources(self) -> list[Source]:
        """List all registered sources.

        Returns:
            List of sources
        """
        return list(self._sources.values())

    def start_all(self):
        """Start all enabled sources."""
        for source in self._sources.values():
            if source.config.enabled:
                source.start()

    def stop_all(self):
        """Stop all sources."""
        for source in self._sources.values():
            source.stop()


# Global source manager instance
_manager: Optional[SourceManager] = None


def get_source_manager() -> SourceManager:
    """Get the global source manager instance.

    Returns:
        Source manager
    """
    global _manager
    if _manager is None:
        _manager = SourceManager()
    return _manager
