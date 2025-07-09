import os
import json
from game_state import game_state, scenario_data
from game_entities import Environment, GameEntity
from utils import load_character_sheet
from d6_rules import ATTITUDE_HOSTILE, roll_d6_dice

def load_scenario(filepath):
    """Loads the main scenario file that defines the adventure."""
    global scenario_data
    try:
        with open(filepath, 'r') as f:
            scenario_data.update(json.load(f))
            return True
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR loading scenario file {filepath}: {e}")
        return False

def setup_initial_encounter():
    """
    Sets up the game by loading the environment and creating characters.
    """
    characters_dir = "."
    env_data = scenario_data.get("environment")
    if not env_data:
        print("No environment data in scenario. Exiting.")
        return False
    game_state["environment"] = Environment(env_data)

    # Load player and enemy character sheets
    char_configs = scenario_data.get("characters", {})
    for player_config in char_configs.get("players", []):
        sheet = load_character_sheet(os.path.join(characters_dir, player_config["sheet"]))
        if sheet: game_state["players"].append(GameEntity(sheet, player_config["location"]))
    for enemy_config in char_configs.get("npcs", []):
        sheet = load_character_sheet(os.path.join(characters_dir, enemy_config["sheet"]))
        if sheet: game_state["npcs"].append(GameEntity(sheet, enemy_config["location"]))

    if not game_state["players"]:
        print("No players loaded. Exiting.")
        return False
        
    return True

def roll_initiative():
    """
    Rolls for initiative for all hostile characters in the same room as the player
    to determine the turn order in combat.
    """
    player_room = game_state["players"][0].current_room if game_state["players"] else None
    if not player_room: return
    
    # Find all combat participants in the current room
    participants = [e for e in game_state["players"] + game_state["npcs"] if not e.is_incapacitated() and e.attitude == ATTITUDE_HOSTILE and e.current_room == player_room]
    for entity in participants:
        entity.initiative_roll, _ = roll_d6_dice(entity.get_attribute_or_skill_pips("Perception"))

    # Sort the turn order from highest to lowest roll
    game_state["turn_order"] = sorted(participants, key=lambda e: e.initiative_roll, reverse=True)
    if game_state["turn_order"]:
        print("Combat Initiative Order: " + ", ".join([f"{e.name} ({e.initiative_roll})" for e in game_state["turn_order"]]))
