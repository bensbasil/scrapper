import json
from pathlib import Path
from typing import List, Dict, Any
from scraper.base_scraper import BaseScraper
from scraper.utils.logger import get_scraper_logger
from scraper.utils.exceptions import ScraperException

logger = get_scraper_logger("DataAcquisitionPipeline")

class AcquisitionPipeline:
    """
    Orchestrates the execution of multiple scraper connectors.
    Writes normalized data to the raw/processed directories.
    """
    def __init__(self, connectors: List[BaseScraper]):
        self.connectors = connectors
        
        # Ensure directories exist
        self.raw_dir = Path("data/raw")
        self.processed_dir = Path("data/processed")
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def run_all(self, target: str, **kwargs) -> Dict[str, Any]:
        """
        Runs all configured connectors against a target (e.g., URL or search query).
        """
        logger.info(f"Starting acquisition pipeline for target: {target}")
        aggregated_data = {"target": target, "sources": {}}
        
        for connector in self.connectors:
            connector_name = connector.__class__.__name__
            try:
                logger.info(f"Running connector: {connector_name}")
                result = connector.run(target, **kwargs)
                aggregated_data["sources"][connector_name] = result
            except ScraperException as e:
                logger.warning(f"Connector {connector_name} failed gracefully: {e}")
                aggregated_data["sources"][connector_name] = {"error": str(e)}
            except Exception as e:
                logger.error(f"Connector {connector_name} crashed unexpectedly: {e}")
                aggregated_data["sources"][connector_name] = {"error": "Critical crash"}

        self._save_raw(target, aggregated_data)
        return aggregated_data

    def _save_raw(self, target: str, data: Dict[str, Any]):
        """Saves the raw JSON output to the data directory."""
        safe_name = "".join([c if c.isalnum() else "_" for c in target])
        filepath = self.raw_dir / f"{safe_name}.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Saved raw data to {filepath}")
