import logging
from pathlib import Path

class StructuredLogger:
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
            
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            fh = logging.FileHandler(log_dir / f"{name.lower()}.log")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

def get_scraper_logger(name: str) -> logging.Logger:
    return StructuredLogger.get_logger(name)
