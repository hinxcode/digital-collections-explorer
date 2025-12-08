from datetime import datetime
import json
import logging
from pathlib import Path

from ..core.config import settings

logger = logging.getLogger(__name__)


class MetadataSearchService:
    def __init__(self):
        self.embeddings_dir = Path(settings.embeddings_dir)
        self.embeddings = None
        self.item_ids = None
        self.metadata = None
        self.is_loaded = False

    def load_metadata(self) -> None:
        """Load metadata from the embeddings directory"""
        if self.is_loaded:
            logger.info("Metadata already loaded")
            return

        try:
            metadata_path = self.embeddings_dir / "metadata.json"

            logger.info(f"Looking for metadata at {metadata_path}")

            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    self.metadata = json.load(f)
                logger.info(f"Loaded metadata for {len(self.metadata)} items")
            else:
                self.metadata = {}
                logger.warning("Metadata file not found, proceeding without metadata.")

        except Exception as e:
            logger.error(f"Error loading metadata: {str(e)}")
            raise

    def date_search(self, target_date, limit=30, offset=0, search_near_date=False):
        """Search for items matching the target date"""
        if not self.is_loaded:
            self.load_metadata()

        results = []
        for item_id, data in self.metadata.items():
            item_date_str = data.get("date")
            if item_date_str:
                try:
                    item_date = datetime.strptime(
                        item_date_str, "%Y-%m-%d %H:%M:%S"
                    ).date()
                    if search_near_date:
                        delta = abs((item_date - target_date).days)
                        if delta <= 30:  # within a month
                            results.append({"id": item_id, "metadata": data})
                    elif item_date == target_date:
                        results.append({"id": item_id, "metadata": data})
                except ValueError:
                    logger.error(
                        f"Failed to parse date for item {item_id}: {item_date_str}"
                    )

        # Apply offset and limit
        results = results[offset : offset + limit]
        return results


metadata_search_service = MetadataSearchService()
