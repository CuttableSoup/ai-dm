# dungeonmaster.py
import requests
import json
import yaml
import re
import os
from datetime import datetime
from d6_rules import *
from llm_calls import player_action, npc_action, narration
from classes import Environment, Actor, GameHistory
import sys 
import random 
import config

# --- Model Configuration ---
USE_OPENROUTER_MODEL = False 

if USE_OPENROUTER_MODEL:
    MODEL = "google/gemma-3-12b-it:free"
    LLM_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_API_KEY = config.OPENROUTER_API_KEY
    HEADERS = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000"
    }
else:
    MODEL = "local-model/gemma-3-12b"
    LLM_API_URL = "http://localhost:1234/v1/chat/completions"
    HEADERS = {"Content-Type": "application/json"}

SCENARIO_FILE = "scenario.yaml"
INVENTORY_FILE = "inventory.yaml"
SPELLS_FILE = "spells.yaml"
DEBUG = True

# Global game state variables
scenario_data = {}
all_items = {}
all_spells = {}
players = []
actors = []
mechanical_summary = None
environment = None
game_history = None

# --- Utility Functions ---
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

# --- AI Tool Definitions ---
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
    }
]

# --- Game Setup ---
def load_scenario(filepath):
    global scenario_data
    try:
        with open(filepath, 'r') as f:
            scenario_data = yaml.safe_load(f)
            return True
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"ERROR loading scenario file {filepath}: {e}")
        return False

def setup_initial_encounter():
    global players, actors, environment, all_items, all_spells, game_history

    if not load_scenario(SCENARIO_FILE):
        print("Failed to load scenario. Exiting.")
        return False

    all_items = load_items(INVENTORY_FILE)
    all_spells = load_spells(SPELLS_FILE)
    if not all_items:
        print("Failed to load inventory items. Exiting.")
        return False

    game_history = GameHistory()

    # The Environment class now handles the creation of actors and objects
    environment = Environment(
        scenario_data, 
        all_items, 
        all_spells,
        scenario_data.get('players', []),
        scenario_data.get('actors', []),
        load_character_sheet # Pass the function itself
    )

    # Populate global lists from the environment instance
    players = environment.players
    actors = environment.actors

    if not players and not actors:
        print("No players or actors loaded. Game cannot start.")
        return False
    
    return True

def roll_initiative():
    all_combatants = players + actors
    initiative_rolls = []
    for combatant in all_combatants:
        dexterity_pips = combatant.get_attribute_or_skill_pips('dexterity')
        wisdom_pips = combatant.get_attribute_or_skill_pips('wisdom')
        initiative_score = roll_d6_dice(dexterity_pips) + roll_d6_dice(wisdom_pips)
        initiative_rolls.append((initiative_score, combatant))
    
    initiative_rolls.sort(key=lambda x: x[0], reverse=True)
    return [combatant for score, combatant in initiative_rolls]

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(str(obj)); f.flush()
    def flush(self, *files):
        for f in self.files: f.flush()

# --- Main Game Loop ---
def main_game_loop():
    log_file_name = datetime.now().strftime("game_log_%Y%m%d_%H%M%S.txt")
    
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_filepath = os.path.join(log_dir, log_file_name)

    llm_config = {
        "url": LLM_API_URL, "headers": HEADERS, "model": MODEL, "tools": available_tools
    }

    with open(log_filepath, 'w') as log_f:
        original_stdout = sys.stdout
        sys.stdout = Tee(original_stdout, log_f)

        if not setup_initial_encounter():
            print("Game setup failed. Exiting.")
            sys.stdout = original_stdout
            return

        if DEBUG:
            print("\n--- Initial Encounter Details ---")
            for player in players:
                current_room, current_zone = environment.get_current_room_data(player.location)
                objects_in_zone = environment.get_objects_in_zone(player.location['room_id'], player.location['zone'])
                print(f"Player: {player.name} is in {current_room['name']} (Zone {player.location['zone']}). HP: {player.cur_hp}/{player.max_hp}")
                if current_zone:
                    print(f"   Zone Description: {current_zone['description']}")
                    if objects_in_zone:
                        print(f"   Objects in Zone: {[obj.name for obj in objects_in_zone]}")
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
        turn_order = roll_initiative()
        
        if DEBUG:
            print("\n--- Initiative Order ---")
            for i, combatant in enumerate(turn_order):
                print(f"{i+1}. {combatant.name} (HP: {combatant.cur_hp}/{combatant.max_hp})")

        while game_active:
            turn_count += 1
            if DEBUG: print(f"\n--- Turn {turn_count} ---")

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
                
                objects_in_current_zone = environment.get_objects_in_zone(current_character.location['room_id'], current_character.location['zone'])
                if DEBUG and objects_in_current_zone:
                    print(f"Objects nearby: {[obj.name for obj in objects_in_current_zone]}")
                
                current_trap = environment.get_trap_in_room(current_character.location['room_id'], current_character.location['zone'])
                if DEBUG:
                    if current_trap and current_trap['status'] == 'armed' and current_trap.get('known') != current_character.name:
                        print(f"WARNING: An unknown trap is armed in this zone! ({current_trap['name']})")
                    elif current_trap and current_trap['status'] == 'armed' and current_trap.get('known') == current_character.name:
                        print(f"You know there is an armed {current_trap['name']} here.")

                if current_character.is_player:
                    character_action = input(f"{current_character.name}, your action > ").strip()
                    print(character_action)
                    
                    dialogue_pattern = r'"(.*?)"|\'(.*?)\''
                    matches = re.findall(dialogue_pattern, character_action)
                    dialogue_parts = [item for t in matches for item in t if item]

                    if dialogue_parts:
                        for dialogue in dialogue_parts:
                            game_history.add_dialogue(current_character.name, dialogue)
                    
                    narration_for_llm = re.sub(dialogue_pattern, '', character_action)
                    narration_for_llm = re.sub(r'\s+', ' ', narration_for_llm).strip() 

                    if narration_for_llm:
                        mechanical_result = player_action(
                            narration_for_llm, current_character, game_history, 
                            environment, players, actors, llm_config, DEBUG
                        )
                    else:
                        mechanical_result = None

                    if DEBUG: print(f"Player {current_character.name}'s Mechanical Outcome: {mechanical_result}")

                else: # NPC Turn
                    mechanical_result = npc_action(
                        current_character, game_history, environment, 
                        players, actors, llm_config, DEBUG
                    )
                    if DEBUG: print(f"{current_character.name}'s Mechanical Outcome: {mechanical_result}")
                    
                if False: #mechanical_result is not None:
                    if DEBUG: print(f"Mechanical Outcome: {mechanical_result}")

                    narrative_text = narration(
                        current_character, environment, players, actors,
                        mechanical_result, game_history, llm_config, DEBUG
                    )
                    print(narrative_text)

        print("\n--- Game End ---")
        sys.stdout = original_stdout

if __name__ == "__main__":
    main_game_loop()