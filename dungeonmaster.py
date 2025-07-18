import requests
import json
import yaml
import os
from datetime import datetime
from d6_rules import *

MODEL = "local-model/gemma-3-4b"  # Model used for deciding character actions
LLM_API_URL = "http://localhost:1234/v1/chat/completions" # Local server URL
SCENARIO_FILE = "scenario.yaml"   # The file containing the game's story and setup

# --- 1. Character Sheet Loading Utility ---
def load_character_sheet(filepath):
    yaml_filepath = os.path.splitext(filepath)[0] + '.yaml'
    try:
        with open(yaml_filepath, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: Character sheet file not found at {yaml_filepath}")
        return None
    except yaml.YAMLError as e:
        print(f"ERROR: Could not parse YAML from {yaml_filepath}: {e}")
        return None

# --- 2. Game Entity and Environment Classes ---
class Environment:
    """Manages the game world's rooms, objects, and exits."""
class Actor:
    """Represents an actor in the game."""
    def __init__(self, character_sheet_data):
        # Basic information
        self.source_data = character_sheet_data

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill and ."""
        return

# --- 3. Discrete Action Functions ---
def execute_skill_check(actor, skill=None, target=None):
    """Performs a general skill check against a target, an object, or a static difficulty."""
    return

# --- 4. AI Tool Definitions & Execution ---
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_skill_check", "description": "Use a skill on an object or another character.",
            "parameters": {"type": "object", "properties": {
                "skill": {"type": "string", "description": "The name of the skill being used, e.g., 'Search'."},
                "target": {"type": "string", "description": "The target of the skill."}
                },
                "required": ["skill", "target"]
            }
        }
    },
]

def get_llm_action_and_execute(input, actor):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """

    # An explicit, rule-based prompt to guide the AI
    prompt_template = """You are an AI assistant for a text-based game. Your task is to translate an actor's command into a specific function call.
Actor Input: '{input}'

**CONTEXT**
- Actors Present: {actors}
- Objects Present: {objects}

**FUNCTION SELECTION RULES - Follow these steps:**
1.  **Is the command using a skill (like search, lift, investigate) on another object or actor?**
    - If yes, you **MUST** call `execute_skill_check`.
    - The `skill_name` should be the skill used (e.g., 'Search').
    - The `target_name` **MUST** be the name of the object/actor from the list of 'Actors Present' or 'Objects Present'.

Based on these strict rules, select the correct function and parameters.
"""
    prompt = prompt_template.format()

    # Prepare and send the request to the AI model
    headers = {"Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()

        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return f"{actor.name} is unable to decide on an action and passes the turn."
            
        # Extract the function name and arguments from the AI's response
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        if function_name == "execute_skill_check": return execute_skill_check(actor, **arguments)
        
        return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e:
        return f"Error communicating with AI: {e}"

# --- 5. Narrative LLM ---
def get_actor_dialogue(actor, context):
    """Generates dialogue for an actor using the LLM."""
    prompt_template = """You are an AI assistant for a text-based game. Your task is to provide dialogue for a specific actor.
You are: '{actor}'

**CONTEXT**
- Actors Present: {actors}
- Objects Present: {objects}
"""
    prompt = prompt_template.format()
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        dialogue = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return f'{actor.name}: "{dialogue}"' if dialogue else f"{actor.name} remains silent."
    except Exception as e:
        return f"LLM Error (Narration): Could not get dialogue. {e}"

def get_llm_story_response(mechanical_summary, actor):
    """
    Generates a narrative summary of the events that just occurred.
    """
    prompt_template = """'You are a Game Master narrating a story.
**CONTEXT**
- Actors Present: {actors}
- Objects Present: {objects}
- Mechanical Outcome: {mechanical_summary}

    Your Task: Write a 2-3 sentence narrative description of what just happened in the third person with a focus on {actor}.'
"""

    # Format the prompt with all the necessary context
    prompt = prompt_template.format()
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or f"LLM (empty response): {mechanical_summary}"
    except Exception as e:
        return f"LLM Error: Could not get narration. {e}"

# --- 6. Initial Game Setup ---
def load_scenario(filepath):
    """Loads the main scenario file that defines the adventure."""
    global scenario_data
    try:
        with open(filepath, 'r') as f:
            scenario_data = yaml.safe_load(f)
            return True
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"ERROR loading scenario file {filepath}: {e}")
        return False

def setup_initial_encounter():
    """
    Sets up the game by loading the environment and creating characters.
    """
    return

def roll_initiative():
    """
    Rolls for initiative for all characters in the room.  Returns a list of characters in initiative order.
    """

# --- 7. Main Game Loop ---
class Tee:
    """A helper class to redirect print output to both the console and a log file."""
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(str(obj)); f.flush()
    def flush(self):
        for f in self.files: f.flush()

def main_game_loop():
    """The main loop that runs the game."""

if __name__ == "__main__":
    main_game_loop()