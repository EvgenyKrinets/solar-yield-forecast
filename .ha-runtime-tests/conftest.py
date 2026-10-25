pytest_plugins = 'pytest_homeassistant_custom_component'

# Ensure this worktree wins over the plugin's older staged integration copy.
import custom_components
from pathlib import Path
custom_components.__path__=[str(Path(__file__).resolve().parents[1]/'custom_components'), *custom_components.__path__]
