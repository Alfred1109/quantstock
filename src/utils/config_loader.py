import yaml
import logging
from typing import Dict, Optional, Any

# It's good practice for utility modules to have their own logger
# or use a common logger if one is established for utilities.
# For now, let's use a simple named logger.
logger = logging.getLogger(__name__)

def load_yaml_config(file_path: str) -> Optional[Dict[str, Any]]:
    """Helper to load a YAML config file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            if not isinstance(config_data, dict):
                # Use the logger defined in this module
                logger.error(f"Configuration file {file_path} did not return a dictionary.")
                return None
            return config_data
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {file_path}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {file_path}: {e}")
        return None
    except Exception as e: # Catch any other potential errors during file reading/parsing
        logger.error(f"An unexpected error occurred while loading YAML file {file_path}: {e}", exc_info=True)
        return None 