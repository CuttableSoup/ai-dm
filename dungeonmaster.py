import requests
import json
import yaml
import os
from datetime import datetime
from d6_rules import *

MODEL = "local-model/gemma-3-4b"  # Model used for deciding character actions
LLM_API_URL = "http://localhost:1234/v1/chat/completions" # Local server URL
SCENARIO_FILE = "scenario.yaml"   # The file containing the game's story and setup
INVENTORY_FILE = "inventory.yaml" # The file containing all possible items

# Global game state variables (will be populated by setup_initial_encounter)
scenario_data = {}
all_items = {}
players = []
actors = []
environment = None # Will be an instance of the Environment class

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

# --- 2. Game Entity and Environment Classes ---
class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, scenario_data, all_items):
        self.rooms = {room['room_id']: room for room in scenario_data.get('environment', {}).get('rooms', [])}
        self.doors = {door['door_id']: door for door in scenario_data.get('environment', {}).get('doors', [])}
        self.all_items = {item['name'].lower(): item for item in all_items} # Store items by lowercased name for easy lookup

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


class Actor:
    """Represents an actor in the game."""
    def __init__(self, character_sheet_data, location):
        self.source_data = character_sheet_data
        self.name = character_sheet_data.get('name', 'Unknown Actor')
        self.max_hp = character_sheet_data.get('max_hp', 10)
        self.cur_hp = character_sheet_data.get('cur_hp', self.max_hp)
        self.attributes = character_sheet_data.get('attributes', {})
        self.skills = character_sheet_data.get('skills', {})
        self.inventory = character_sheet_data.get('inventory', [])
        self.location = location # {'room_id': 'room_1', 'zone': 1}
        self.is_player = False # Default, can be overridden for players

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill."""
        trait_name = trait_name.lower()
        
        # Check if it's an attribute
        if trait_name in self.attributes:
            return self.attributes[trait_name] * 3 # Attributes are typically multiplied by 3 for pips

        # Check if it's a skill
        if trait_name in self.skills:
            skill_pips = self.skills[trait_name] * 3
            # Add attribute pips for the governing attribute of the skill
            for attr, skill_list in D6_SKILLS_BY_ATTRIBUTE.items():
                if trait_name in skill_list:
                    return skill_pips + (self.attributes.get(attr, 0) * 3)
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


# --- 3. Discrete Action Functions ---
def execute_skill_check(actor, skill=None, target=None):
    """
    Performs a general skill check against a target (object, trap, or another actor)
    or a static difficulty.
    """
    if not skill or not target:
        return f"ERROR: Skill '{skill}' or target '{target}' not specified for skill check."

    # Try to find the target as an object in the current room/zone
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    
    target_object = None
    if current_zone_data and 'objects' in current_zone_data:
        for obj in current_zone_data['objects']:
            if obj['name'].lower() == target.lower():
                target_object = obj
                break
    if not target_object and 'objects' in current_room: # Check room-level objects too
        for obj in current_room['objects']:
            if obj['name'].lower() == target.lower():
                target_object = obj
                break

    # Try to find the target as a door
    target_door = environment.get_door_by_id(target)
    if not target_door and target_object is None: # If not found by ID, try by name
        for door_id, door_data in environment.doors.items():
            if door_data['name'].lower() == target.lower():
                target_door = door_data
                break

    # Try to find the target as a trap
    target_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    if target_trap and target_trap['name'].lower() == target.lower():
        # Only proceed if the skill is related to the trap's actions
        if skill.lower() not in [action['skill'].lower() for action in target_trap.get('actions', [])]:
            return f"{actor.name} can't use {skill} on the {target}."
        
        # Override target_object with trap data for consistent processing
        target_object = target_trap
        is_trap = True
    else:
        is_trap = False


    if target_object:
        # Check if the skill can be applied to the object/trap
        action_found = False
        outcome_message = ""
        for action in target_object.get('actions', []):
            if action['skill'].lower() == skill.lower():
                action_found = True
                difficulty = action.get('difficulty', 0)
                
                actor_pips = actor.get_attribute_or_skill_pips(skill)
                success_level, roll_total = roll_d6_check(actor_pips, difficulty)

                if success_level > 0:
                    outcome = action.get('pass', 'success')
                    if outcome == 'open' and (target_door or target_object.get('name').lower() == 'chest'):
                        if target_door:
                            target_door['status'] = 'open'
                            outcome_message = f"{actor.name} successfully used {skill} on the {target}. The {target_door['name']} is now open."
                        elif target_object.get('name').lower() == 'chest':
                            target_object['status'] = 'open' # Assuming chests can have a status
                            inventory_items = []
                            if 'inventory' in target_object:
                                for item_data in target_object['inventory']:
                                    item_name = item_data['item']
                                    item_quantity = item_data.get('quantity', 1)
                                    inventory_items.append(f"{item_quantity} {item_name}")
                                    # Add to actor's inventory
                                    actor.inventory.append({'item': item_name, 'quantity': item_quantity})
                                target_object['inventory'] = [] # Empty the chest
                            outcome_message = f"{actor.name} successfully used {skill} on the {target} and opened it. Inside, you find: {', '.join(inventory_items) if inventory_items else 'nothing'}."
                    elif outcome == 'disarm' and is_trap:
                        target_trap['status'] = 'disarmed'
                        outcome_message = f"{actor.name} successfully used {skill} on the {target} and disarmed it."
                    elif outcome == 'known' and is_trap:
                        target_trap['known'] = actor.name # Mark the trap as known by the actor
                        outcome_message = f"{actor.name} successfully used {skill} on the {target} and now knows about the {target_trap['name']}."
                    else:
                        outcome_message = f"{actor.name} successfully used {skill} on the {target}. {action.get('pass', 'It worked!')}"
                else:
                    outcome = action.get('fail', 'nothing')
                    if outcome == 'jam' and (target_door or target_object.get('name').lower() == 'chest'):
                        if target_door:
                            target_door['status'] = 'jammed'
                            outcome_message = f"{actor.name} failed to use {skill} on the {target}. The {target_door['name']} is now jammed and cannot be opened."
                        elif target_object.get('name').lower() == 'chest':
                            target_object['status'] = 'jammed'
                            outcome_message = f"{actor.name} failed to use {skill} on the {target}. The {target_object['name']} is now jammed."
                    elif outcome == 'attack' and is_trap:
                        if target_trap['status'] == 'armed' and target_trap['known'] != actor.name:
                            attack_roll = roll_d6_dice(target_trap['attack'])
                            damage_roll = roll_d6_dice(target_trap['damage'])
                            
                            damage_taken = damage_roll
                            
                            outcome_message = f"{actor.name} failed to use {skill} on the {target}. The {target_trap['name']} attacked! {actor.take_damage(damage_taken)}"
                            target_trap['status'] = 'sprung' # Trap springs after attacking
                        else:
                            outcome_message = f"{actor.name} failed to use {skill} on the {target}. Nothing happens because the trap is already disarmed or known."
                    else:
                        outcome_message = f"{actor.name} failed to use {skill} on the {target}. {action.get('fail', 'Nothing happens.')}"
                return outcome_message

        if not action_found:
            return f"{actor.name} cannot use {skill} on the {target}."
    
    # Try to find the target as another actor
    target_actor = next((a for a in players + actors if a.name.lower() == target.lower()), None)
    if target_actor:
        # For now, we'll just say a skill check was attempted on an actor without specific combat logic
        # Combat would involve comparing skills and attributes directly
        actor_pips = actor.get_attribute_or_skill_pips(skill)
        target_pips = target_actor.get_attribute_or_skill_pips(skill) # Or an opposing skill
        
        # Simple opposed roll example (needs more sophisticated combat rules)
        if skill.lower() in COMBAT_SKILLS:
            # This is a very basic example and needs proper combat resolution rules
            # For now, just a generic message
            return f"{actor.name} attempts to use {skill} on {target_actor.name}. Combat resolution rules not fully implemented."
        else:
            return f"{actor.name} tries to use {skill} on {target_actor.name}, but nothing specific happens with that skill for now."

    return f"Could not find target '{target}' for skill check."


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

def get_llm_action_and_execute(input_command, actor):
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
    
    # Add trap if present and armed/known
    current_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    if current_trap and (current_trap['status'] == 'armed' or current_trap.get('known') == actor.name):
        all_potential_targets.append(current_trap['name'])

    # An explicit, rule-based prompt to guide the AI
    prompt_template = """You are an AI assistant for a text-based game. Your task is to translate an actor's command into a specific function call.
Actor Input: '{input_command}'

**CONTEXT**
- Actor Name: {actor_name}
- Actor Skills: {actor_skills}
- Actors Present (and in the same location as {actor_name}): {actors_present}
- Objects Present (in the same location as {actor_name}): {objects_present}
- Doors Present (in the same location as {actor_name}): {doors_present}
- Traps Present (in the same location as {actor_name}): {traps_present}

**FUNCTION SELECTION RULES - Follow these steps:**
1.  **Is the command using a skill (like search, lift, investigate, lockpick, disable device) on an object, door, trap or another actor?**
    - If yes, you **MUST** call `execute_skill_check`.
    - The `skill` argument should be the skill used (e.g., 'Search', 'Lockpicking', 'Lifting', 'Disable Device'). **Ensure the skill is a valid skill from 'Actor Skills' and is relevant to the command.**
    - The `target` argument **MUST** be the name of the object, door, trap or actor from the list of 'Objects Present', 'Doors Present', 'Traps Present', or 'Actors Present'. **Ensure the target name exactly matches one of the provided names.**

Based on these strict rules, select the correct function and parameters.
If no suitable function call can be made, return an empty response.
"""
    prompt = prompt_template.format(
        input_command=input_command,
        actor_name=actor.name,
        actor_skills=list(actor.skills.keys()),
        actors_present=actors_in_room,
        objects_present=objects_in_room,
        doors_present=doors_in_room,
        traps_present=[current_trap['name']] if current_trap else [],
    )

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
        
        if function_name == "execute_skill_check":
            return execute_skill_check(actor, **arguments)
        
        return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e:
        return f"Error communicating with AI: {e}"

# --- 5. Narrative LLM ---
def get_actor_dialogue(actor, context):
    """Generates dialogue for an actor using the LLM."""
    current_room, current_zone_data = environment.get_current_room_data(actor.location)

    # Get objects in the current room/zone
    objects_in_room = []
    if current_zone_data and 'objects' in current_zone_data:
        objects_in_room.extend([obj['name'] for obj in current_zone_data['objects']])
    if current_room and 'objects' in current_room:
        objects_in_room.extend([obj['name'] for obj in current_room['objects']])
    
    # Get actors in the current room/zone (excluding the current actor)
    actors_in_room = [a.name for a in players + actors if a.location == actor.location and a.name != actor.name]

    prompt_template = """You are an AI assistant for a text-based game. Your task is to provide dialogue for a specific actor.
You are: '{actor_name}'

**CONTEXT**
- Your Current Location: {room_name} - {zone_description}
- Other Actors Present in this location: {actors_present}
- Objects Present in this location: {objects_present}
- Current HP: {current_hp}/{max_hp}
- Current Statuses: {statuses}
- Current Memories: {memories}
- Current Mood/Personality: {personality}

Generate a short, in-character piece of dialogue (1-2 sentences) based on the current context and your personality.
"""
    prompt = prompt_template.format(
        actor_name=actor.name,
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(objects_in_room) if objects_in_room else "none",
        current_hp=actor.cur_hp,
        max_hp=actor.max_hp,
        statuses=", ".join(actor.source_data.get('statuses', [])) if actor.source_data.get('statuses') else "none",
        memories=", ".join(actor.source_data.get('memories', [])) if actor.source_data.get('memories') else "none",
        personality=", ".join(actor.source_data.get('personality', [])) if actor.source_data.get('personality') else "none"
    )
    
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
    current_room, current_zone_data = environment.get_current_room_data(actor.location)

    # Get objects in the current room/zone
    objects_in_room = []
    if current_zone_data and 'objects' in current_zone_data:
        objects_in_room.extend([obj['name'] for obj in current_zone_data['objects']])
    if current_room and 'objects' in current_room:
        objects_in_room.extend([obj['name'] for obj in current_room['objects']])
    
    # Get actors in the current room/zone
    actors_in_room = [a.name for a in players + actors if a.location == actor.location]

    prompt_template = """You are a Game Master narrating a story.
**CONTEXT**
- Current Room: {room_name} - {zone_description}
- Actors Present in this location: {actors_present}
- Objects Present in this location: {objects_present}
- Mechanical Outcome: {mechanical_summary}

Your Task: Write a 2-3 sentence narrative description of what just happened in the third person with a focus on {actor_name}.
Describe the environment and the actor's action and its immediate outcome.
"""

    # Format the prompt with all the necessary context
    prompt = prompt_template.format(
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(objects_in_room) if objects_in_room else "none",
        mechanical_summary=mechanical_summary,
        actor_name=actor.name
    )
    
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
    Populates global players, actors, and environment variables.
    """
    global players, actors, environment, all_items

    if not load_scenario(SCENARIO_FILE):
        print("Failed to load scenario. Exiting.")
        return False

    all_items = load_items(INVENTORY_FILE)
    if not all_items:
        print("Failed to load inventory items. Exiting.")
        return False

    environment = Environment(scenario_data, all_items)

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
    for actor_data in scenario_data.get('actors', []):
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
    For simplicity, a basic roll (e.g., d6 + Perception attribute pips) for now.
    """
    all_combatants = players + actors
    initiative_rolls = []
    for combatant in all_combatants:
        # A simple initiative: roll 1d6 + Perception pips (Perception * 3)
        perception_pips = combatant.get_attribute_or_skill_pips('perception')
        initiative_score = roll_d6_dice(perception_pips) + random.randint(1, 6)
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
    log_file_name = datetime.now().strftime("game_log_%Y%m%d_%H%M%S.txt")
    
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

        print("\n--- Initial Encounter Details ---")
        for player in players:
            current_room, current_zone = environment.get_current_room_data(player.location)
            print(f"Player: {player.name} is in {current_room['name']} (Zone {player.location['zone']}). HP: {player.cur_hp}/{player.max_hp}")
            if current_zone:
                print(f"  Zone Description: {current_zone['description']}")
                if 'objects' in current_zone and current_zone['objects']:
                    print(f"  Objects in Zone: {[obj['name'] for obj in current_zone['objects']]}")
                if 'trap' in current_zone:
                    print(f"  There's a {current_zone['trap']['name']} here.")
            print(f"  Inventory: {[{item['item']: item['quantity']} for item in player.inventory]}")
        
        for actor_npc in actors:
            current_room, current_zone = environment.get_current_room_data(actor_npc.location)
            print(f"NPC: {actor_npc.name} is in {current_room['name']} (Zone {actor_npc.location['zone']}). HP: {actor_npc.cur_hp}/{actor_npc.max_hp}")
            if current_zone:
                print(f"  Zone Description: {current_zone['description']}")

        game_active = True
        turn_count = 0

        # Roll initiative to determine turn order
        turn_order = roll_initiative()
        print("\n--- Initiative Order ---")
        for i, combatant in enumerate(turn_order):
            print(f"{i+1}. {combatant.name} (HP: {combatant.cur_hp}/{combatant.max_hp})")

        while game_active:
            turn_count += 1
            print(f"\n--- Turn {turn_count} ---")

            for current_character in turn_order:
                if current_character.cur_hp <= 0:
                    print(f"{current_character.name} is unconscious and cannot act.")
                    continue

                print(f"\n{current_character.name}'s turn.")
                current_room, current_zone_data = environment.get_current_room_data(current_character.location)
                
                if not current_room:
                    print(f"{current_character.name} is in an unknown location. Skipping turn.")
                    continue

                print(f"Location: {current_room['name']} (Zone {current_character.location['zone']}) - {current_zone_data['description']}")
                
                # List objects in the current zone
                objects_in_current_zone = current_zone_data.get('objects', [])
                if objects_in_current_zone:
                    print(f"Objects nearby: {[obj['name'] for obj in objects_in_current_zone]}")
                
                # Check for armed traps in the current zone
                current_trap = environment.get_trap_in_room(current_character.location['room_id'], current_character.location['zone'])
                if current_trap and current_trap['status'] == 'armed' and current_trap.get('known') != current_character.name:
                    print(f"WARNING: An unknown trap is armed in this zone! ({current_trap['name']})")
                elif current_trap and current_trap['status'] == 'armed' and current_trap.get('known') == current_character.name:
                    print(f"You know there is an armed {current_trap['name']} here.")


                # Player turn
                if current_character.is_player:
                    player_input = input(f"What will {current_character.name} do? (e.g., 'search dusty floor', 'lift wooden door', 'quit'): ").strip().lower()
                    if player_input == 'quit':
                        game_active = False
                        print("Exiting game.")
                        break

                    mechanical_result = get_llm_action_and_execute(player_input, current_character)
                    print(f"Mechanical Outcome: {mechanical_result}")
                    print(get_llm_story_response(mechanical_result, current_character))
                # NPC/Actor turn
                else:
                    print(get_actor_dialogue(current_character, {})) # Placeholder for more complex context
                    # For now, NPCs will try to interact with known objects or just wait
                    # A more complex AI would use get_llm_action_and_execute
                    if current_trap and current_trap['status'] == 'armed' and current_trap.get('known') != current_character.name:
                        mechanical_result = execute_skill_check(current_character, skill='search', target=current_trap['name'])
                        print(f"Mechanical Outcome: {mechanical_result}")
                        print(get_llm_story_response(mechanical_result, current_character))
                    elif objects_in_current_zone:
                        # Simple NPC action: try to interact with the first object they see
                        first_object_name = objects_in_current_zone[0]['name']
                        mechanical_result = f"{current_character.name} considers interacting with the {first_object_name} but does nothing for now."
                        print(f"Mechanical Outcome: {mechanical_result}")
                        print(get_llm_story_response(mechanical_result, current_character))
                    else:
                        mechanical_result = f"{current_character.name} surveys the area."
                        print(f"Mechanical Outcome: {mechanical_result}")
                        print(get_llm_story_response(mechanical_result, current_character))

                # Check if all players are incapacitated or a game-ending condition is met
                if all(p.cur_hp <= 0 for p in players):
                    print("\nAll players are incapacitated. Game Over!")
                    game_active = False
                    break
                
                # Simple win condition: if chest is open and empty
                inner_sanctum_chest = environment.get_object_in_room('room_2', 'chest')
                if inner_sanctum_chest and inner_sanctum_chest.get('status') == 'open' and not inner_sanctum_chest.get('inventory'):
                    print("\nCongratulations! The chest in the Inner Sanctum has been looted. You have completed the scenario!")
                    game_active = False
                    break

        print("\n--- Game End ---")
        sys.stdout = original_stdout # Restore stdout

if __name__ == "__main__":
    import sys
    main_game_loop()