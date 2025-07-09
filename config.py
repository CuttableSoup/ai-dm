# --- Configuration ---
# These settings control the connection to the AI models and game files.
ACTION_MODEL = "local-model/gemma-3-4b"  # Model used for deciding character actions
NARRATIVE_MODEL = "local-model/gemma-3-4b" # Model used for generating descriptive text
LLM_API_URL = "http://localhost:1234/v1/chat/completions" # Local server URL
SCENARIO_FILE = "scenario.json"      # The file containing the game's story and setup
DEBUG = False                         # Set to True to print extra debugging information
