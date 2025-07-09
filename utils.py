import json
import sys
from datetime import datetime

# --- Character Sheet Loading Utility ---
def load_character_sheet(filepath):
    """
    Loads a character sheet from a JSON file.
    
    Args:
        filepath (str): The path to the character sheet file.
        
    Returns:
        dict: The character data as a dictionary, or None if an error occurs.
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Character sheet file not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON from {filepath}")
        return None

class Tee:
    """A helper class to redirect print output to both the console and a log file."""
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(str(obj)); f.flush()
    def flush(self):
        for f in self.files: f.flush()
