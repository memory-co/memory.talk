"""Example sync source - demonstrates how to create a sync source."""
import time
from connectors.base import Source, SourceConfig


class ExampleSource(Source):
    """Example sync source that generates dummy data."""

    def __init__(self, config: SourceConfig):
        """Initialize the example source."""
        super().__init__(config)
        self._running = False

    @property
    def name(self) -> str:
        """Return the source name."""
        return "example"

    def start(self):
        """Start the source sync."""
        self._running = True
        self._update_status("running")

    def stop(self):
        """Stop the source sync."""
        self._running = False
        self._update_status("stopped")

    def sync(self) -> int:
        """Perform a sync and return the number of messages synced.

        Returns:
            Number of messages synced
        """
        if not self._running:
            return 0

        try:
            # Simulate syncing some data
            messages_synced = 0
            # In a real implementation, this would fetch data from an external source

            self._update_status("running", messages_synced)
            return messages_synced
        except Exception as e:
            self._update_status("error", error_message=str(e))
            return 0
