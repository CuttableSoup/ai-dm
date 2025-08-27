import requests
import json
import yaml
import re
import os
from datetime import datetime
from collections import deque # For the GameHistory class
from d6_rules import *
from actions import execute_skill_check, cast_spell # <-- IMPORT the new cast_spell function
import sys # Needed for stdout redirection in main_game_loop
import random # Needed for roll_initiative
import config

# --- Model Configuration ---
# Set this to True to use the OpenRouter model, False to use the local model
USE_OPENROUTER_MODEL = False 

if USE_OPENROUTER_MODEL:
    MODEL = "google/gemma-3-12b-it:free"
    LLM_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_API_KEY = config.OPENROUTER_API_KEY # Get the API key from config.py
    # OpenRouter requires a Referer or X-Title header. For local development, a placeholder is fine.
    OPENROUTER_HEADERS = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000" # You can replace this with your actual app URL if deployed
    }
else:
    MODEL = "local-model/gemma-3-12b"
    LLM_API_URL = "http://localhost:1234/v1/chat/completions"
    LOCAL_HEADERS = {"Content-Type": "application/json"} # Headers for local model

SCENARIO_FILE = "scenario.yaml"   # The file containing the game's story and setup
INVENTORY_FILE = "inventory.yaml" # The file containing all possible items
SPELLS_FILE = "spells.yaml"       # The file containing all possible spells
DEBUG = True

# Global game state variables (will be populated by setup_initial_encounter)
scenario_data = {}
all_items = {}
all_spells = {}
players = []
actors = []
mechanical_summary = None
environment = None # Will be an instance of the Environment class
game_history = None # Will be an instance of the GameHistory class

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

def load_items(filepath):
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f).get('items', [])
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"ERROR loading inventory file {filepath}: {e}")
        return []

def load_spells(filepath):
    """Loads and processes the spells from the given YAML file."""
    try:
        with open(filepath, 'r') as f:
            spells_list = yaml.safe_load(f)
            processed_spells = {}
            for spell_entry in spells_list:
                for spell_name, spell_data in spell_entry.items():
                    processed_spells[spell_name.lower()] = spell_data
            return processed_spells
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"ERROR loading spells file {filepath}: {e}")
        return {}

# --- 2. Game Entity and Environment Classes ---
class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, scenario_data, all_items, all_spells):
        self.rooms = {room['room_id']: room for room in scenario_data.get('environment', {}).get('rooms', [])}
        self.doors = {door['door_id']: door for door in scenario_data.get('environment', {}).get('doors', [])}
        self.all_items = {item['name'].lower(): item for item in all_items} # Store items by lowercased name for easy lookup
        self.all_spells = all_spells

    def get_room_by_id(self, room_id):
        return self.rooms.get(room_id)

    def get_door_by_id(self, door_id):
        return self.doors.get(door_id)

    def get_current_room_data(self, actor_location):
        room = self.get_room_by_id(actor_location['room_id'])
        if not room:
            return None, None
        
        # Get zone data
        current_zone_data = None
        for zone_data in room.get('zones', []):
            if zone_data.get('zone') == actor_location['zone']:
                current_zone_data = zone_data
                break
        
        return room, current_zone_data

    def get_object_in_room(self, room_id, object_name):
        room = self.get_room_by_id(room_id)
        if room:
            for zone_data in room.get('zones', []):
                for obj in zone_data.get('objects', []):
                    if obj['name'].lower() == object_name.lower():
                        return obj
            # Check objects directly in the room if not in a specific zone's objects
            for obj in room.get('objects', []):
                if obj['name'].lower() == object_name.lower():
                    return obj
        return None

    def get_trap_in_room(self, room_id, zone_id):
        room = self.get_room_by_id(room_id)
        if room:
            for zone_data in room.get('zones', []):
                if zone_data.get('zone') == zone_id:
                    return zone_data.get('trap')
        return None

    def get_item_details(self, item_name):
        return self.all_items.get(item_name.lower())

    def get_spell_details(self, spell_name):
        return self.all_spells.get(spell_name.lower())


class Actor:
    """Represents an actor in the game."""
    def __init__(self, character_sheet_data, location):
        self.source_data = character_sheet_data
        for key, value in character_sheet_data.items():
            setattr(self, key, value)
        self.location = location # {'room_id': 'room_1', 'zone': 1}
        self.is_player = False # Default, can be overridden for players

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill."""
        trait_name = trait_name.lower()
        
        # Check if it's an attribute
        if trait_name in self.attributes:
            return self.attributes[trait_name]

        # Check if it's a skill
        if trait_name in self.skills:
            skill_pips = self.skills[trait_name]
            # Add attribute pips for the governing attribute of the skill
            for attr, skill_list in D6_SKILLS_BY_ATTRIBUTE.items():
                if trait_name in skill_list:
                    return skill_pips + (self.attributes.get(attr, 0))
            return skill_pips # If skill found but no governing attribute specified/found

        return 0 # Trait not found

    def take_damage(self, damage):
        self.cur_hp -= damage
        if self.cur_hp < 0:
            self.cur_hp = 0
        return f"{self.name} took {damage} damage and now has {self.cur_hp} HP."

    def heal_damage(self, healing):
        self.cur_hp += healing
        if self.cur_hp > self.max_hp:
            self.cur_hp = self.max_hp
        return f"{self.name} healed {healing} HP and now has {self.cur_hp} HP."

class GameHistory:
    """Records the past few actions and dialogues in the game."""
    def __init__(self, max_entries=5):
        self.history = deque(maxlen=max_entries)

    def add_action(self, actor_name, action_description):
        """Adds an action to the history."""
        self.history.append(f"ACTION: {actor_name} - {action_description}")

    def add_dialogue(self, actor_name, dialogue_text):
        """Adds dialogue to the history."""
        self.history.append(f"DIALOGUE: {actor_name}: \"{dialogue_text}\"")

    def get_history_string(self):
        """Returns the history as a formatted string."""
        if not self.history:
            return "No recent history."
        return "\n".join(list(self.history))


# --- 3. Discrete Action Functions ---
# execute_skill_check and cast_spell are in actions.py

# --- 4. AI Tool Definitions & Execution ---
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_skill_check", "description": "Use a non-magical skill on an object or another character.",
            "parameters": {"type": "object", "properties": {
                "skill": {"type": "string", "description": "The name of the skill being used."},
                "target": {"type": "string", "description": "The target of the skill."}
                },
                "required": ["skill", "target"]
            }
        }
    },
    {   "type": "function", "function": {
            "name": "cast_spell", "description": "Cast a known spell on a target.",
            "parameters": {"type": "object", "properties": {
                "spell": {"type": "string", "description": "The name of the spell being cast from the character's spell list."},
                "target": {"type": "string", "description": "The target of the spell."}
                },
                "required": ["spell", "target"]
            }
        }
    }
]

def execute_function_call(actor, function_name, arguments):
    """A helper to execute the function call from the LLM's response."""
    if function_name == "execute_skill_check":
        mechanical_result = execute_skill_check(actor, environment=environment, players=players, actors=actors, **arguments)
        game_history.add_action(actor.name, f"attempted to use {arguments.get('skill', 'a skill')} on {arguments.get('target', 'a target')}.")
        return mechanical_result
    elif function_name == "cast_spell":
        mechanical_result = cast_spell(actor, environment=environment, players=players, actors=actors, **arguments)
        game_history.add_action(actor.name, f"attempted to cast {arguments.get('spell', 'a spell')} on {arguments.get('target', 'a target')}.")
        return mechanical_result
    
    mechanical_result = f"Error: The AI tried to call an unknown function '{function_name}'."
    game_history.add_action(actor.name, mechanical_result)
    return mechanical_result

def get_llm_action_and_execute(input_command, actor, game_history_instance):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    
    # Get objects in the current room/zone
    objects_in_room = []
    if current_zone_data and 'objects' in current_zone_data:
        objects_in_room.extend([obj['name'] for obj in current_zone_data['objects']])
    if current_room and 'objects' in current_room:
        objects_in_room.extend([obj['name'] for obj in current_room['objects']])
    
    # Get actors in the current room/zone (excluding the current actor)
    actors_in_room = [a.name for a in players + actors if a.location == actor.location and a.name != actor.name]

    # Get doors in the current room's exits
    doors_in_room = []
    if current_zone_data and 'exits' in current_zone_data:
        for exit_data in current_zone_data['exits']:
            door_ref = exit_data.get('door_ref')
            if door_ref:
                door = environment.get_door_by_id(door_ref)
                if door:
                    doors_in_room.append(door['name'])
    
    # Combine all potential targets
    all_potential_targets = list(set(objects_in_room + actors_in_room + doors_in_room))
    
    # Get trap if present
    current_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    if current_trap:
        all_potential_targets.append(current_trap['name'])

    # An explicit, rule-based prompt to guide the AI
    prompt_template = """You are an AI assistant for a text-based game. Your task is to determine if a described action requires a mechanical function call.
    The input is either a player's direct command or a narrative description of an NPC's action.

    Input: '{input_command}'

    **CONTEXT**
    - Actor Name: {actor_name}
    - Actor Skills: {actor_skills}
    - Actor Spells: {actor_spells}
    - Actors Present: {actors_present}
    - Objects Present: {objects_present}
    - Doors Present: {doors_present}
    - Traps Present: {traps_present}
    - Recent Game History: {game_history}

    **FUNCTION SELECTION RULES - Follow these steps STRICTLY:**
    1.  **Analyze the INTENT.** Is the character trying to perform a specific, mechanical action?
    2.  **Check for SPELLCASTING.** If the input mentions casting a spell (e.g., "casts fireball," "uses charm"), and the spell is in the Actor's spell list, you **MUST** call the `cast_spell` function.
        - The `spell` argument must exactly match a spell from `{actor_spells}`.
        - The `target` argument must match an item from the lists of present Actors, Objects, etc.
    3.  **Check for SKILL USE.** If the action is not a spell but involves using a skill (e.g., "attacks with sword," "tries to pick the lock"), you **MUST** call `execute_skill_check`.
        - The `skill` argument must be a relevant skill from `{actor_skills}`.
        - The `target` argument must match an item from the lists.
    4.  **IGNORE DIALOGUE AND FLAVOR TEXT.** If the input is just dialogue, an emotional reaction, or a description of an action without a clear target (e.g., "fiddling with a lockpick," "observing the room," "muttering to himself"), it is NOT a mechanical action. In this case, you **MUST NOT** call any function. Return an empty response.
    5.  **PRIORITY:** It is better to do nothing than to call a function incorrectly. If you are not certain, do not call a function.
    """
    prompt = prompt_template.format(
        input_command=input_command,
        actor_name=actor.name,
        actor_skills=list(actor.skills.keys()),
        actor_spells=getattr(actor, 'spells', []), # Use getattr to safely get spells
        actors_present=actors_in_room,
        objects_present=objects_in_room,
        doors_present=doors_in_room,
        traps_present=[current_trap['name']] if current_trap else [],
        game_history=game_history_instance.get_history_string()
    )

    # Use appropriate headers based on the model chosen
    headers = OPENROUTER_HEADERS if USE_OPENROUTER_MODEL else LOCAL_HEADERS

    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    
    if DEBUG:
        print(f"\n--- LLM Narrative Request Payload ---\n{json.dumps(payload, indent=2)}\n-----------------------------------\n")
        
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        
        if DEBUG:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
            
        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            # This is the expected outcome for dialogue or flavor text.
            mechanical_result = None
            game_history_instance.add_dialogue(actor.name, input_command) # Log the dialogue
            return mechanical_result
            
        # Extract the function name and arguments from the AI's response
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        # Call the appropriate function based on the AI's choice
        if function_name == "execute_skill_check":
            mechanical_result = execute_skill_check(actor, environment=environment, players=players, actors=actors, **arguments)
            game_history_instance.add_action(actor.name, f"attempted to use {arguments.get('skill', 'a skill')} on {arguments.get('target', 'a target')}.")
            return mechanical_result
        elif function_name == "cast_spell":
            mechanical_result = cast_spell(actor, environment=environment, players=players, actors=actors, **arguments)
            game_history_instance.add_action(actor.name, f"attempted to cast {arguments.get('spell', 'a spell')} on {arguments.get('target', 'a target')}.")
            return mechanical_result
        
        mechanical_result = f"Error: The AI tried to call an unknown function '{function_name}'."
        game_history_instance.add_action(actor.name, mechanical_result)
        return mechanical_result
    except Exception as e:
        mechanical_result = f"Error communicating with AI: {e}"
        game_history_instance.add_action(actor.name, mechanical_result)
        return mechanical_result

# --- 5. Narrative LLM ---
def get_llm_response(actor):
    """
    Generates a narrative summary of the events that just occurred.
    """
    current_room, current_zone_data = environment.get_current_room_data(actor.location) # Use actor.location

    # Get objects in the current room/zone
    objects_in_room = []
    if current_zone_data and 'objects' in current_zone_data:
        objects_in_room.extend([obj['name'] for obj in current_zone_data['objects']])
    if current_room and 'objects' in current_room:
        objects_in_room.extend([obj['name'] for obj in current_room['objects']])

    # Get actors in the current room/zone
    actors_in_room = [a.name for a in players + actors if a.location == actor.location]

    # Extract character qualities for the prompt
    character_qualities = actor.source_data.get('qualities', {})
    gender = character_qualities.get('gender', 'unknown')
    race = character_qualities.get('race', 'unknown')
    occupation = character_qualities.get('occupation', 'unknown')
    eyes = character_qualities.get('eyes', 'unknown')
    hair = character_qualities.get('hair', 'unknown')
    skin = character_qualities.get('skin', 'unknown')

    prompt_template = """You are a Game Master narrating a story.
    **CONTEXT**
    - Current Room: {room_name} - {zone_description}
    - Actors Present in this location: {actors_present}
    - Objects Present in this location: {objects_present}
    - Mechanical Outcome: {mechanical_summary}
    - Recent Game History: {game_history}
    - Current Statuses: {statuses}
    - Current Memories: {memories}
    - Current Attitudes: {attitudes}
    - Current Mood/Personality: {personality}
    - Character quotes: {character_quotes}
    - Character Qualities (for narrative description of {player_name}):
    - Gender: {player_gender}
    - Race: {player_race}
    - Eyes: {player_eyes}
    - Hair: {player_hair}
    - Skin: {player_skin}
    """

    if actor.is_player == True:
        prompt_template += """
        You are the narrator of a grounded, text-based RPG. Your job is to describe the outcome of the player's action in a vivid and engaging way, like a good Dungeon Master.

        **Factual Outcome:**
        - **Mechanical Summary:** {mechanical_summary} <-- This is what actually happened. Your narration MUST align perfectly with this result.

        **Your Task:**
        1.  Write a short (2-3 sentences) narrative description from a third-person perspective focused on {player_name}.
        2.  Start by briefly describing the character's *attempted action*.
        3.  Seamlessly weave in the **Mechanical Summary** to describe the final result.
        4.  Use sensory details (the sound of a lock, the smell of dust, the glint of steel) to immerse the player.
        5.  Keep the tone grounded and cinematic. Avoid overly dramatic or poetic language.
        """
    else: # NPC Turn
        prompt_template += """
        Your task is to determine the next action for the NPC, {player_name}, and express it as simple dialogue OR a clear, direct command.

        **Instructions - Follow these steps:**
        1.  **First, review the 'Recent Game History'.** If the last entry was dialogue directed at you, your primary goal is to respond directly to that dialogue.
        2.  **Use your 'Personality' and 'Attitudes' to decide *how* to respond.** (e.g., if you are 'irritable', respond irritably).
        3.  **Decide on an action.** This can be just talking, or a physical action.
        4.  **State your turn clearly.** Write a line of dialogue from your perspective, followed by a command if you are taking an action.
        
        **Example:** If the history says 'Valerius: "Have you seen my sword?"' and your personality is 'helpful', you might say: "I think I saw it over by the table. I'll go check." followed by the action, listed under Skills.

        **CONTEXT FOR YOUR DECISION**
        - Your Personality: {personality}
        - Your Current Attitudes: {attitudes}
        - Recent Game History: {game_history}
        - Actors Present: {actors_present}
        - Objects Present: {objects_present}
        - Your Spells: {actor_spells}
        - Your Skills: {actor_skills}
        """

    # Format attitudes
    attitudes_list = actor.source_data.get('attitudes', [])
    attitudes_str = "none"
    if attitudes_list:
        # Format list of dictionaries into a readable string
        formatted_attitudes = []
        for attitude_dict in attitudes_list:
            for key, value in attitude_dict.items():
                formatted_attitudes.append(f"{key}: {value}")
        attitudes_str = ", ".join(formatted_attitudes)


    # Format the prompt with all the necessary context
    prompt = prompt_template.format(
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(objects_in_room) if objects_in_room else "none",
        mechanical_summary=mechanical_summary,
        actor_skills=list(actor.skills.keys()),
        actor_spells=getattr(actor, 'spells', []), # Safely get spells
        player_name=actor.name, # Use actor.name here
        game_history=game_history.get_history_string(),
        statuses=", ".join(actor.source_data.get('statuses', [])) if actor.source_data.get('statuses') else "none",
        memories=", ".join(actor.source_data.get('memories', [])) if actor.source_data.get('memories') else "none",
        attitudes=attitudes_str,
        personality=", ".join(actor.source_data.get('personality', [])) if actor.source_data.get('personality') else "none",
        character_quotes=", ".join(actor.source_data.get('quotes', [])) if actor.source_data.get('quotes') else "none",
        player_gender=gender,
        player_race=race,
        player_occupation=occupation,
        player_eyes=eyes,
        player_hair=hair,
        player_skin=skin
    )

    # Corrected code
    headers = OPENROUTER_HEADERS if USE_OPENROUTER_MODEL else LOCAL_HEADERS
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
    
    if DEBUG:
        print(f"\n--- LLM Response Request Payload ---\n{json.dumps(payload, indent=2)}\n-----------------------------------\n")

    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        
        if DEBUG:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
        
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"LLM Error: Could not get narration. {e}"


def get_llm_npc_action_single_call(actor, game_history_instance):
    """(SINGLE-CALL METHOD) Generates NPC dialogue and function call in one request."""
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    
    # Get objects in the current room/zone
    objects_in_room = []
    if current_zone_data and 'objects' in current_zone_data:
        objects_in_room.extend([obj['name'] for obj in current_zone_data['objects']])
    if current_room and 'objects' in current_room:
        objects_in_room.extend([obj['name'] for obj in current_room['objects']])
    
    # Get actors in the current room/zone (excluding the current actor)
    actors_in_room = [a.name for a in players + actors if a.location == actor.location and a.name != actor.name]

    # Get doors in the current room's exits
    doors_in_room = []
    if current_zone_data and 'exits' in current_zone_data:
        for exit_data in current_zone_data['exits']:
            door_ref = exit_data.get('door_ref')
            if door_ref:
                door = environment.get_door_by_id(door_ref)
                if door:
                    doors_in_room.append(door['name'])
                    
    current_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    attitudes_list = actor.source_data.get('attitudes', [])
    attitudes_str = "none"
    if attitudes_list:
        formatted_attitudes = [f"{k}: {v}" for d in attitudes_list for k, v in d.items()]
        attitudes_str = ", ".join(formatted_attitudes)

    prompt_template = """You are an AI Game Master controlling an NPC named {actor_name}. Your task is to determine the NPC's next action, generate their dialogue or a description of the action, AND select the appropriate function to call if a mechanical action is taken.

    **Instructions:**
    1.  **Review the Context:** Use your Personality, Attitudes, and the Recent Game History to decide on a logical and in-character action.
    2.  **Generate Narrative:** Write a short line of dialogue or a 1-2 sentence description of the action from the NPC's perspective. This will be shown to the player.
    3.  **Perform a Mechanical Action (If Necessary):**
        - If the action is a spell, a skill check, or an attack, you **MUST** call the appropriate function (`cast_spell` or `execute_skill_check`).
        - The arguments for the function must be chosen from the lists of available targets.
        - If the action is just talking, observing, or simple movement without a mechanical check, **DO NOT** call any function. Just provide the narrative text.

    **CONTEXT FOR YOUR DECISION**
    - Your Name: {actor_name}
    - Your Personality: {personality}
    - Your Current Attitudes: {attitudes}
    - Recent Game History: {game_history}
    - Actors Present: {actors_present}
    - Objects Present: {objects_present}
    - Doors Present: {doors_present}
    - Traps Present: {traps_present}
    - Your Spells: {actor_spells}
    - Your Skills: {actor_skills}
    """
    prompt = prompt_template.format(
        actor_name=actor.name,
        personality=", ".join(actor.source_data.get('personality', [])) or "none",
        attitudes=attitudes_str,
        game_history=game_history_instance.get_history_string(),
        actors_present=actors_in_room,
        objects_present=objects_in_room,
        doors_present=doors_in_room,
        traps_present=[current_trap['name']] if current_trap else [],
        actor_spells=getattr(actor, 'spells', []),
        actor_skills=list(actor.skills.keys())
    )
    headers = OPENROUTER_HEADERS if USE_OPENROUTER_MODEL else LOCAL_HEADERS
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    
    if DEBUG:
        print(f"\n--- LLM Narrative Request Payload ---\n{json.dumps(payload, indent=2)}\n-----------------------------------\n")
        
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        message = response.get("choices", [{}])[0].get("message", {})
        
        if DEBUG:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
        
        # Print the narrative/dialogue part
        npc_narrative = message.get("content", "").strip()
        if npc_narrative:
            print(npc_narrative)
            game_history_instance.add_dialogue(actor.name, npc_narrative)

        # Execute the mechanical/tool part
        if not message.get("tool_calls"):
            return None # No mechanical action was taken
        
        tool_call = message['tool_calls'][0]['function']
        return execute_function_call(actor, tool_call['name'], json.loads(tool_call['arguments']))

    except Exception as e:
        return f"Error communicating with AI: {e}"

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
    Populates global players, actors, and environment variables.
    """
    global players, actors, environment, all_items, all_spells, game_history

    if not load_scenario(SCENARIO_FILE):
        print("Failed to load scenario. Exiting.")
        return False

    all_items = load_items(INVENTORY_FILE)
    all_spells = load_spells(SPELLS_FILE)
    if not all_items:
        print("Failed to load inventory items. Exiting.")
        return False

    environment = Environment(scenario_data, all_items, all_spells)
    game_history = GameHistory() # Initialize game history

    # Setup Players
    for player_data in scenario_data.get('players', []):
        sheet_path = player_data['sheet']
        char_sheet = load_character_sheet(sheet_path)
        if char_sheet:
            player_actor = Actor(char_sheet, player_data['location'])
            player_actor.is_player = True
            players.append(player_actor)
        else:
            print(f"Warning: Could not load player character sheet: {sheet_path}")

    # Setup NPCs/Actors
    for actor_data in scenario_data.get('actors') or []:
        sheet_path = actor_data['sheet']
        char_sheet = load_character_sheet(sheet_path)
        if char_sheet:
            actors.append(Actor(char_sheet, actor_data['location']))
        else:
            print(f"Warning: Could not load actor character sheet: {sheet_path}")

    if not players and not actors:
        print("No players or actors loaded. Game cannot start.")
        return False
    
    return True

def roll_initiative():
    """
    Rolls for initiative for all characters in the room. Returns a list of characters in initiative order.
    """
    all_combatants = players + actors
    initiative_rolls = []
    for combatant in all_combatants:
        dexterity_pips = combatant.get_attribute_or_skill_pips('dexterity')
        wisdom_pips = combatant.get_attribute_or_skill_pips('wisdom')
        initiative_score = roll_d6_dice(dexterity_pips) + roll_d6_dice(wisdom_pips)
        initiative_rolls.append((initiative_score, combatant))
    
    # Sort in descending order of initiative score
    initiative_rolls.sort(key=lambda x: x[0], reverse=True)
    
    return [combatant for score, combatant in initiative_rolls]

# --- 7. Main Game Loop ---
class Tee:
    """A helper class to redirect print output to both the console and a log file."""
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(str(obj)); f.flush()
    def flush(self, *files):
        for f in self.files: f.flush()

def main_game_loop():
    """The main loop that runs the game."""
    log_file_name = datetime.now().strftime("game_log_%Y%m%d_%H%M%S.rtf")
    
    # Check if the 'logs' directory exists, create if not
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_filepath = os.path.join(log_dir, log_file_name)

    with open(log_filepath, 'w') as log_f:
        # Redirect stdout to both console and log file
        original_stdout = sys.stdout
        sys.stdout = Tee(original_stdout, log_f)

        print("--- Game Start ---")

        if not setup_initial_encounter():
            print("Game setup failed. Exiting.")
            sys.stdout = original_stdout # Restore stdout before exiting
            return

        if DEBUG:
            print("\n--- Initial Encounter Details ---")
            for player in players:
                current_room, current_zone = environment.get_current_room_data(player.location)
                print(f"Player: {player.name} is in {current_room['name']} (Zone {player.location['zone']}). HP: {player.cur_hp}/{player.max_hp}")
                if current_zone:
                    print(f"   Zone Description: {current_zone['description']}")
                    if 'objects' in current_zone and current_zone['objects']:
                        print(f"   Objects in Zone: {[obj['name'] for obj in current_zone['objects']]}")
                    if 'trap' in current_zone:
                        print(f"   There's a {current_zone['trap']['name']} here.")
                print(f"   Inventory: {[{item['item']: item['quantity']} for item in player.inventory]}")
        
        for actor_npc in actors:
            current_room, current_zone = environment.get_current_room_data(actor_npc.location)
            print(f"NPC: {actor_npc.name} is in {current_room['name']} (Zone {actor_npc.location['zone']}). HP: {actor_npc.cur_hp}/{actor_npc.max_hp}")
            if current_zone:
                print(f"   Zone Description: {current_zone['description']}")

        game_active = True
        turn_count = 0

        # Roll initiative to determine turn order
        turn_order = roll_initiative()
        if DEBUG:
            print("\n--- Initiative Order ---")
            for i, combatant in enumerate(turn_order):
                print(f"{i+1}. {combatant.name} (HP: {combatant.cur_hp}/{combatant.max_hp})")

        while game_active:
            turn_count += 1
            
            if DEBUG:
                print(f"\n--- Turn {turn_count} ---")

            for current_character in turn_order:
                if current_character.cur_hp <= 0:
                    print(f"{current_character.name} is unconscious and cannot act.")
                    continue
                
                if DEBUG:
                    print(f"\n{current_character.name}'s turn.")
                current_room, current_zone_data = environment.get_current_room_data(current_character.location)
                
                if not current_room:
                    print(f"{current_character.name} is in an unknown location. Skipping turn.")
                    continue
                
                if DEBUG:
                    print(f"Location: {current_room['name']} (Zone {current_character.location['zone']}) - {current_zone_data['description']}")
                
                # List objects in the current zone
                objects_in_current_zone = current_zone_data.get('objects', [])
                if DEBUG:
                    if objects_in_current_zone:
                        print(f"Objects nearby: {[obj['name'] for obj in objects_in_current_zone]}")
                
                # Check for armed traps in the current zone
                current_trap = environment.get_trap_in_room(current_character.location['room_id'], current_character.location['zone'])
                if DEBUG:
                    if current_trap and current_trap['status'] == 'armed' and current_trap.get('known') != current_character.name:
                        print(f"WARNING: An unknown trap is armed in this zone! ({current_trap['name']})")
                    elif current_trap and current_trap['status'] == 'armed' and current_trap.get('known') == current_character.name:
                        print(f"You know there is an armed {current_trap['name']} here.")

                # Player turn
                if current_character.is_player:
                    character_action = input(f"{current_character.name}, your action > ").strip()
                    
                    # Step 1: Find all instances of dialogue using re.findall.
                    dialogue_parts = re.findall(r'["\'](.*?)["\']', character_action)
                    
                    # Step 2: If dialogue was found, log each part.
                    if dialogue_parts:
                        for dialogue in dialogue_parts:
                            game_history.add_dialogue(current_character.name, dialogue)
                    
                    # Step 3: Get the pure narration by substituting all dialogue instances with an empty string.
                    narration_for_llm = re.sub(r'["\'].*?["\']', '', character_action)
                    narration_for_llm = re.sub(r'\s+', ' ', narration_for_llm).strip() 

                    # Step 4: Only send the narration to the LLM if any exists.
                    if narration_for_llm:
                        mechanical_result = get_llm_action_and_execute(narration_for_llm, current_character, game_history)
                    else:
                        mechanical_result = None

                    if DEBUG:
                        print(f"Mechanical Outcome: {mechanical_result}")

                else:
                    # NPC logic uses the single-call method
                    mechanical_result = get_llm_npc_action_single_call(current_character, game_history)
                    if DEBUG:
                        print(f"Mechanical Outcome: {mechanical_result}")

        print("\n--- Game End ---")
        sys.stdout = original_stdout

if __name__ == "__main__":
    main_game_loop()