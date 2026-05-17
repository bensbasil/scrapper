from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseScraper(ABC):
    """
    Abstract Base Class for all scraper connectors.
    Enforces a standard interface for the data pipeline.
    """
    
    @abstractmethod
    def fetch_raw(self, target: str, **kwargs) -> Any:
        """
        Fetches the raw data (HTML, JSON, etc.) from the target.
        Should handle retries and basic rate limiting.
        """
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any, **kwargs) -> Any:
        """
        Parses the raw data into a semi-structured format.
        """
        pass

    @abstractmethod
    def normalize(self, parsed_data: Any) -> Dict[str, Any]:
        """
        Normalizes the parsed data into the standard dictionary schema
        expected by the pipeline and database.
        """
        pass

    def run(self, target: str, **kwargs) -> Dict[str, Any]:
        """
        Standard execution flow: fetch -> parse -> normalize.
        """
        raw_data = self.fetch_raw(target, **kwargs)
        if not raw_data:
            return {}
            
        parsed_data = self.parse_data(raw_data, **kwargs)
        if not parsed_data:
            return {}
            
        return self.normalize(parsed_data)
