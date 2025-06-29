import random
import requests
import json
import os
import sys
import collections
from datetime import datetime
from d6_rules import *

# --- Configuration ---
# These settings control the connection to the AI models and game files.
ACTION_MODEL = "local-model/gemma-3-1b"  # Model used for deciding character actions
NARRATIVE_MODEL = "local-model/gemma-3-1b" # Model used for generating descriptive text
LLM_API_URL = "http://localhost:1234/v1/chat/completions" # Local server URL
SCENARIO_FILE = "scenario.json"      # The file containing the game's story and setup
DEBUG = False                         # Set to True to print extra debugging information

# --- Global State Variables ---
# These variables store the game's data and are accessed throughout the program.
scenario_data = {}  # Holds all the data from the scenario.json file
game_state = {
    "players": [], "npcs": [], "environment": None,
    "turn_order": [], "current_turn_entity_index": 0, "round_number": 1
}

# --- 1. Character Sheet Loading Utility ---
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

# --- 2. Game Entity and Environment Classes ---
class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, environment_data):
        self.rooms = environment_data.get("rooms", {})
        self.location = environment_data.get("location", "")

    def get_room(self, room_key):
        """Returns the data for a specific room."""
        return self.rooms.get(room_key)

class GameEntity:
    """Represents a character (player, NPC, object, etc) in the game."""
    def __init__(self, character_sheet_data, location):
        # Basic information
        self.source_data = character_sheet_data
        self.id = character_sheet_data.get("id")
        self.name = character_sheet_data.get("name")
        
        # Descriptive information
        self.qualities = character_sheet_data.get("qualities", {})
        self.languages = character_sheet_data.get("languages", [])
        self.memories = character_sheet_data.get("memories", [])
        self.statuses = character_sheet_data.get("statuses", [])

        # Personality and attitude
        personality_data = character_sheet_data.get("personality", "neutral")
        if isinstance(personality_data, list) and personality_data:
            self.personality = personality_data[0]
        else:
            self.personality = personality_data

        attitude_data = character_sheet_data.get("attitudes", [])
        default_attitude = ATTITUDE_INDIFFERENT
        if isinstance(attitude_data, list) and attitude_data:
            default_attitude_entry = next((att for att in attitude_data if "default" in att), None)
            if default_attitude_entry:
                default_attitude = default_attitude_entry.get("default", ATTITUDE_INDIFFERENT)
        self.attitude = default_attitude
        
        # Game mechanics data
        self.experience = character_sheet_data.get("experience", 0)
        self.allies = character_sheet_data.get("allies", "none")
        
        # Attributes, skills, and equipment
        self.attributes = {k.lower(): v for k, v in character_sheet_data.get("attributes", {}).items()}
        self.skills = {k.lower(): v for k, v in character_sheet_data.get("skills", {}).items()}
        self.equipment = character_sheet_data.get("equipment", [])
        self.inventory = character_sheet_data.get("inventory", [])

        # Spells
        self.spells = character_sheet_data.get("spells", [])
        
        # Combat-related stats
        self.max_wounds = character_sheet_data.get("wounds", 7)
        self.current_wound_index = WOUND_LEVEL_HEALTHY
        self.initiative_roll = 0
        
        # --- MODIFIED: Location is now a dictionary including room and zone ---
        self.current_room = location.get("room")
        self.current_zone = location.get("zone")

    def get_attribute_descriptors_string(self):
        """Creates a human-readable string of the character's attributes."""
        descriptors = []
        for attr, pips in self.attributes.items():
            descriptor = get_attribute_descriptor(attr, pips)
            if descriptor and descriptor != "Average":
                descriptors.append(f"{attr.capitalize()}: {descriptor}")
        return ", ".join(descriptors) if descriptors else "Average"

    def get_status_summary(self):
        """Provides a quick summary of the character's current state, including location."""
        # --- MODIFIED: Status summary now includes zone ---
        base_summary = f"{self.name} (Status: {self.get_wound_status()}, Room: {self.current_room}, Zone: {self.current_zone})"
        return base_summary

    def get_wound_status(self):
        """Returns the character's current health status as a string."""
        return {
            WOUND_LEVEL_HEALTHY: "Healthy", WOUND_LEVEL_STUNNED: "Stunned",
            WOUND_LEVEL_WOUNDED: "Wounded (-1D)", WOUND_LEVEL_SEVERELY_WOUNDED: "Severely Wounded (-2D)",
            WOUND_LEVEL_INCAPACITATED: "Incapacitated", WOUND_LEVEL_MORTALLY_WOUNDED: "Mortally Wounded",
            WOUND_LEVEL_DEAD: "Dead"
        }.get(self.current_wound_index, "Unknown")

    def get_wound_penalty_pips(self):
        """Returns the penalty (in pips) based on how wounded the character is."""
        if self.current_wound_index == WOUND_LEVEL_WOUNDED: return 3
        if self.current_wound_index == WOUND_LEVEL_SEVERELY_WOUNDED: return 6
        return 0

    def apply_damage(self, damage_roll_total, resistance_roll_total):
        """Calculates and applies damage to the character."""
        if self.is_incapacitated():
            return f"{self.name} is already out of action."
            
        outcome = f"Damage roll: {damage_roll_total} vs Resistance roll: {resistance_roll_total}. "
        if damage_roll_total <= resistance_roll_total:
            outcome += f"{self.name} resists the damage."
            return outcome

        damage_difference = damage_roll_total - resistance_roll_total
        
        target_level_from_damage = self.current_wound_index
        if damage_difference <= 3: target_level_from_damage = WOUND_LEVEL_STUNNED
        elif damage_difference <= 6: target_level_from_damage = WOUND_LEVEL_WOUNDED
        elif damage_difference <= 9: target_level_from_damage = WOUND_LEVEL_SEVERELY_WOUNDED
        elif damage_difference <= 12: target_level_from_damage = WOUND_LEVEL_INCAPACITATED
        else: target_level_from_damage = WOUND_LEVEL_MORTALLY_WOUNDED
        
        self.current_wound_index = min(self.current_wound_index, target_level_from_damage)
        outcome += f"{self.name} is now {self.get_wound_status()}!"
        return outcome

    def is_incapacitated(self):
        """Checks if the character is unable to take actions."""
        return self.current_wound_index <= WOUND_LEVEL_INCAPACITATED

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill."""
        trait_name_lower = trait_name.lower()
        governing_attribute_name = next((k.lower() for k, v in D6_SKILLS_BY_ATTRIBUTE.items() if trait_name_lower in [s.lower() for s in v]), None)
        
        if governing_attribute_name:
            return self.skills.get(trait_name_lower, 0) + self.attributes.get(governing_attribute_name, 0)
        
        if trait_name_lower in self.attributes:
            return self.attributes[trait_name_lower]
            
        if DEBUG: print(f"[WARN] Trait '{trait_name}' not found for {self.name}. Returning 0 pips.")
        return 0

    def get_resistance_pips(self):
        """Gets the pips used for resisting damage, usually based on Physique."""
        return self.attributes.get("physique", 0)

    def get_weapon_details(self, weapon_name_or_type="melee"):
        """Finds a weapon in the character's equipment."""
        for item in self.equipment:
            if item.get("type", "").lower() == "weapon":
                return item # Return the first equipped weapon
        
        # --- MODIFIED: Default unarmed strike now includes range ---
        return {"name": "Unarmed", "skill": "brawling", "damage": self.attributes.get("physique", 6), "range": 0}

# --- 3. Discrete Action Functions ---
# These functions define the specific actions characters can take in the game.

# --- NEW: Helper function to calculate distance between zones ---
def get_zone_distance(start_zone, end_zone, room_key):
    """
    Calculates the shortest distance in zones between a start and end zone using BFS.
    This is the core of the range system.
    """
    if start_zone == end_zone:
        return 0

    room_data = game_state["environment"].get_room(room_key)
    if not room_data or not isinstance(room_data.get("zones"), dict):
        return -1 # Invalid room data, cannot calculate distance

    layout = room_data["zones"]
    
    # A queue for our search, storing (zone_id, distance_from_start)
    queue = collections.deque([(start_zone, 0)])
    # A set to keep track of zones we've already visited to avoid loops
    visited = {start_zone}

    while queue:
        current_zone, distance = queue.popleft()

        # Get adjacent zones from the layout. Keys are strings in JSON.
        adjacent_zones = layout.get(str(current_zone), {}).get("adjacent_zones", [])

        for neighbor in adjacent_zones:
            # If we found the target, return the distance traveled.
            if neighbor == end_zone:
                return distance + 1
            
            # If we haven't visited this neighbor yet, add it to the queue.
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    
    return -1 # Target was not found/unreachable

# --- MODIFIED: `look` now describes zones and locations within them ---
def execute_look(actor_name, **kwargs):
    """Provides a detailed description of the character's current surroundings, including zones."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return "Could not find actor to 'look' for."

    room = game_state["environment"].get_room(actor.current_room)
    if not room: return f"{actor.name} is in an unknown location."

    # Build the description string
    response = f"--- {room.get('name', 'Unnamed Room')} ---\n"
    response += room.get('description', 'No description available.') + "\n"

    all_chars = game_state["players"] + game_state["npcs"]
    all_zones_data = room.get("zones", {})
    
    # Describe each zone, and the characters/objects within it
    for zone_num, zone_data in all_zones_data.items():
        zone_name = zone_data.get('name', '')
        response += f"\n  [Zone {zone_num} - {zone_name}]"
        
        chars_in_zone = [e.name for e in all_chars if e.current_room == actor.current_room and e.current_zone == int(zone_num)]
        if chars_in_zone:
            response += f" Characters: {', '.join(chars_in_zone)}."

        objects_in_zone = [obj['name'] for obj in room.get("objects", []) if obj.get("zone") == int(zone_num)]
        if objects_in_zone:
            response += f" Objects: {', '.join(objects_in_zone)}."

    # State the player's own position and valid moves from there
    actor_zone_data = all_zones_data.get(str(actor.current_zone))
    if actor_zone_data:
        adjacent_zones = actor_zone_data.get("adjacent_zones", [])
        response += f"\n\nYou are in Zone {actor.current_zone} ({actor_zone_data.get('name', '')})."
        response += f"\nFrom here, you can move to Zone(s): {', '.join(map(str, adjacent_zones))}."

    # List the exits from the entire room
    exits = [f"{exit['name']} (from Zone {exit['zone']}): {exit['description']}" for exit in room.get("exits", [])]
    if exits: response += "\n\nExits from Room: \n- " + "\n- ".join(exits) + "\n"
    
    return response

def execute_check_self(actor_name, **kwargs):
    """Provides a summary of the character's own status, equipment, and inventory."""
    actor = next((e for e in game_state["players"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Could not find player '{actor_name}'."
    
    response = f"--- Status for {actor.name} ---\n"
    response += f"Condition: {actor.get_wound_status()}\n"
    response += f"Location: Room '{actor.current_room}', Zone {actor.current_zone}\n"
    response += f"Attributes: {actor.get_attribute_descriptors_string()}\n"
    
    # List equipped items, now showing range
    equipped_items = [f"{item['name']} (Range: {item.get('range', 'N/A')})" for item in actor.equipment]
    response += "Equipped: " + (", ".join(equipped_items) if equipped_items else "Nothing") + "\n"
    # List inventory items
    inventory_items = [f"{item['name']}" for item in actor.inventory]
    response += "Inventory: " + (", ".join(inventory_items) if inventory_items else "Empty") + "\n"
    return response

# --- MODIFIED: `move` between rooms now checks if the player is in the correct zone to use an exit ---
def execute_move(actor_name, exit_name):
    """Moves the character through a specified exit to another room."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    room = game_state["environment"].get_room(actor.current_room)
    if not room: return f"{actor.name} is in an unknown location and cannot move."

    target_exit = next((ext for ext in room.get("exits", []) if ext["name"].lower() == exit_name.lower()), None)
    if not target_exit: return f"{actor.name} cannot find an exit named '{exit_name}'."
    
    # Check if character is in the correct zone to use the exit
    if actor.current_zone != target_exit.get("zone"):
        return f"You must be in Zone {target_exit.get('zone')} to use the {exit_name}."

    if "action" in target_exit:
        return f"{actor.name} must perform an action to use the {exit_name}. Try using the '{target_exit['action']['skill']}' skill."

    destination_key = target_exit.get("to_room")
    destination_room = game_state["environment"].get_room(destination_key)
    if not destination_room: return f"The exit '{exit_name}' leads nowhere."
    
    # Update actor's location to the new room, defaulting to Zone 1
    actor.current_room = destination_key
    actor.current_zone = 1
    return f"{actor.name} moves through the {exit_name} into the {destination_room.get('name', 'next room')}."

# --- NEW: Function to move between zones in the same room ---
def execute_move_zone(actor_name, target_zone):
    """Moves the character to an ADJACENT zone within the current room."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    room_data = game_state["environment"].get_room(actor.current_room)
    if not room_data: return f"{actor.name} is in an unknown location."

    all_zones = room_data.get("zones", {})
    if not all_zones or not isinstance(all_zones, dict):
        return f"The {room_data.get('name')} does not have a valid zone layout."

    current_zone_data = all_zones.get(str(actor.current_zone))
    if not current_zone_data: return f"{actor.name} is in an invalid zone '{actor.current_zone}'."

    # Check if the target zone is in the list of adjacent zones for the current zone
    if target_zone not in current_zone_data.get("adjacent_zones", []):
        return f"Cannot move to Zone {target_zone}. From here, you can only move to: {', '.join(map(str, current_zone_data.get('adjacent_zones', ['Nowhere'])))}."

    actor.current_zone = target_zone
    return f"{actor.name} moves to Zone {target_zone}."

# --- REPLACED: `execute_melee_attack` is now a more general `execute_attack` that checks range ---
def execute_attack(actor_name, target_name):
    """Executes an attack, checking the weapon's range against the target's distance."""
    all_entities = game_state["players"] + game_state["npcs"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    # This function only finds characters, so passing an object name will fail.
    target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
    
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."
    if not target_entity: return f"Action failed: Could not find target '{target_name}'."
    if actor.current_room != target_entity.current_room: return f"Action failed: {target_name} is not in the same room."

    # Get the actor's equipped weapon (or unarmed) and its range
    weapon = actor.get_weapon_details()
    weapon_range = weapon.get("range", 0)
    
    # Calculate distance in zones and check if target is in range
    distance = get_zone_distance(actor.current_zone, target_entity.current_zone, actor.current_room)
    if distance == -1 or distance > weapon_range:
        return f"Action failed: {target_name} is out of range for the {weapon['name']}. (Target is {distance} zones away, range is {weapon_range})."
    
    # If range check passes, proceed with the attack
    outcome_summary = f"{actor.name} attacks {target_entity.name} with {weapon['name']}! (Distance: {distance} zones)"
    if actor.attitude != ATTITUDE_HOSTILE:
        actor.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {actor.name} becomes Hostile!"
    if target_entity.attitude != ATTITUDE_HOSTILE:
        target_entity.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {target_entity.name} becomes Hostile!"

    # Perform the attack roll
    attack_skill_pips = actor.get_attribute_or_skill_pips(weapon.get("skill", "brawling"))
    success_level, _, attack_roll_str = roll_d6_check(actor, attack_skill_pips, 10) # Simplified Difficulty
    outcome_summary += f"\n  Attack: {attack_roll_str}"
    
    if success_level > 0:
        outcome_summary += " Hit!"
        # Calculate and apply damage
        damage_pips = weapon.get("damage", 0) + ((success_level - 1) * 3)
        damage_roll, _ = roll_d6_dice(damage_pips)
        res_pips = target_entity.get_resistance_pips()
        res_roll, _ = roll_d6_dice(res_pips)
        damage_effect_str = target_entity.apply_damage(damage_roll, res_roll)
        outcome_summary += f"\n  {damage_effect_str}"
    else:
        outcome_summary += " Miss!"
        
    return outcome_summary

def execute_skill_check(actor_name, skill_name=None, target_name=None, object_name=None):
    """Performs a general skill check against a target, an object, or a static difficulty."""
    all_entities = game_state["players"] + game_state["npcs"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."
    
    actor_room_data = game_state["environment"].get_room(actor.current_room)
    
    # --- Logic for interacting with an object or exit ---
    if object_name:
        target_object = next((obj for obj in actor_room_data.get("objects", []) if obj["name"].lower() == object_name.lower()), None)
        target_exit = next((ext for ext in actor_room_data.get("exits", []) if ext["name"].lower() == object_name.lower()), None)
        target_interactive = target_object or target_exit
        
        if not target_interactive:
            return f"{actor.name} can't find an object or exit named '{object_name}' to interact with."
        
        # --- MODIFIED: Check if actor is in the right zone to interact with the object/exit ---
        if 'zone' in target_interactive and actor.current_zone != target_interactive['zone']:
             return f"You must move to Zone {target_interactive['zone']} to interact with the {object_name}."

        action_data = target_interactive.get("action")
        if not action_data: return f"'{object_name}' is not interactive in that way."
        if not skill_name: skill_name = action_data.get("skill")
        if action_data.get("skill", "").lower() != skill_name.lower():
            return f"You can't use '{skill_name}' on '{object_name}'."
            
        difficulty_number = action_data.get("difficulty", 10)
        skill_pips = actor.get_attribute_or_skill_pips(skill_name)
        success_level, _, details_str = roll_d6_check(actor, skill_pips, difficulty_number)
        
        outcome_summary = f"{actor.name} uses {skill_name} on {object_name}: {details_str}"
        if success_level > 0:
            outcome_summary += f"\n  -> SUCCESS! {action_data.get('success_text', 'It works!')}"
            if target_exit: target_exit.pop("action", None)
            if "inventory" in action_data:
                target_interactive.setdefault('items', []).extend(action_data["inventory"])
                target_interactive.pop("action", None)
        else:
            outcome_summary += "\n  -> " + action_data.get("failure_text", "Nothing happens.")
        return outcome_summary

    # --- Logic for an opposed skill check against another character ---
    if target_name:
        target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
        # This is the source of the "Could not find target" error if the AI misuses this parameter.
        if not target_entity: return f"Action failed: Could not find target '{target_name}'."
        # --- MODIFIED: Opposed skill checks now require being in the same zone ---
        if actor.current_room != target_entity.current_room or actor.current_zone != target_entity.current_zone:
             return f"Action failed: {target_name} is not in the same zone."
        if not skill_name: return f"Action failed: must specify a skill to use on {target_name}."
        
        resisting_skill = "Willpower"
        normalized_skill_name = next((k for k in OPPOSED_SKILLS if k.lower() == skill_name.lower()), None)
        if normalized_skill_name and OPPOSED_SKILLS[normalized_skill_name]:
            resisting_skill = OPPOSED_SKILLS[normalized_skill_name][0]
            
        outcome_summary = f"{actor.name} uses {skill_name} against {target_entity.name} (resisted by {resisting_skill})."
        
        resistance_pips = target_entity.get_attribute_or_skill_pips(resisting_skill)
        resistance_roll, _ = roll_d6_dice(resistance_pips)
        final_difficulty = resistance_roll
        skill_pips = actor.get_attribute_or_skill_pips(skill_name)
        success_level, _, details_str = roll_d6_check(actor, skill_pips, final_difficulty)
        
        outcome_summary += f"\n  {actor.name}'s roll: {details_str} vs Resistance DN {final_difficulty}."
        return outcome_summary

    # --- Logic for a general skill check against a static difficulty ---
    if not skill_name:
        return "Action failed: You must specify a skill to use."
    outcome_summary = f"{actor.name} attempts to use their {skill_name} skill."
    final_difficulty = 10 # Default difficulty
    outcome_summary += f" against a static difficulty of {final_difficulty}."
    skill_pips = actor.get_attribute_or_skill_pips(skill_name)
    success_level, _, details_str = roll_d6_check(actor, skill_pips, final_difficulty)
    outcome_summary += f"\n  {actor.name}'s roll: {details_str}"
    return outcome_summary

def execute_take_item(actor_name, source_name, item_name):
    """Takes an item from an object or an incapacitated character."""
    all_entities = game_state["players"] + game_state["npcs"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    actor_room_data = game_state["environment"].get_room(actor.current_room)
    
    # --- Case 1: Taking from an object in the room ---
    source_object = next((obj for obj in actor_room_data.get("objects", []) if obj["name"].lower() == source_name.lower()), None)
    if source_object:
        # --- MODIFIED: Check if actor is in the same zone as the object ---
        if actor.current_zone != source_object.get("zone"):
            return f"You must be in Zone {source_object.get('zone')} to take items from the {source_name}."

        available_items = source_object.get("items", [])
        possible_matches = [item for item in available_items if item_name.lower() in item['name'].lower()]
        if len(possible_matches) == 0:
            return f"There is no item named '{item_name}' on the {source_name}."
        elif len(possible_matches) > 1:
            item_names = ", ".join([item['name'] for item in possible_matches])
            return f"Did you mean one of these: {item_names}?"
        else:
            item_to_take = possible_matches[0]
            actor.inventory.append(item_to_take)
            available_items.remove(item_to_take)
            return f"{actor.name} takes the {item_to_take['name']} from the {source_name}."

    # --- Case 2: Taking from a character ---
    source_char = next((e for e in all_entities if e.name.lower() == source_name.lower()), None)
    if source_char:
        # Taking from a character requires being in the same zone
        if source_char.current_room != actor.current_room or source_char.current_zone != actor.current_zone:
            return f"Cannot take from {source_name}; they are not in the same zone."
        if not source_char.is_incapacitated():
            return f"Cannot take from {source_name}; they are not incapacitated."

        source_inventory = source_char.inventory + source_char.equipment
        item_to_take = next((item for item in source_inventory if item['name'].lower() == item_name.lower()), None)
        if not item_to_take: return f"{source_name} does not have an item named '{item_name}'."

        actor.inventory.append(item_to_take)
        try:
            if item_to_take in source_char.inventory: source_char.inventory.remove(item_to_take)
            if item_to_take in source_char.equipment: source_char.equipment.remove(item_to_take)
        except ValueError: pass
        return f"{actor.name} takes the {item_name} from the incapacitated {source_name}."

    return f"Cannot find a source named '{source_name}' to take from."

def execute_drop_item(actor_name, item_name):
    """Removes an item from a character's inventory and places it in a pile on the floor in their current zone."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    item_to_drop = next((item for item in actor.inventory if item['name'].lower() == item_name.lower()), None)
    if item_to_drop:
        actor.inventory.remove(item_to_drop)
    else:
        item_to_drop = next((item for item in actor.equipment if item['name'].lower() == item_name.lower()), None)
        if item_to_drop:
            actor.equipment.remove(item_to_drop)
        else:
            return f"{actor.name} does not have a '{item_name}' to drop."

    room_data = game_state["environment"].get_room(actor.current_room)
    if not room_data: return "ERROR: Actor is in an invalid room."

    pile_name = "a pile of items"
    pile_object = None
    room_objects = room_data.setdefault("objects", [])

    for obj in room_objects:
        if obj.get("name") == pile_name and obj.get("zone") == actor.current_zone:
            pile_object = obj
            break
    
    if not pile_object:
        pile_object = {"name": pile_name, "zone": actor.current_zone, "items": []}
        room_objects.append(pile_object)

    pile_object.setdefault("items", []).append(item_to_drop)
    return f"{actor.name} drops the {item_to_drop['name']} on the ground."

def execute_equip_item(actor_name, item_name):
    """Moves an item from inventory to equipment, checking for occupied location slots."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    item_to_equip = next((item for item in actor.inventory if item['name'].lower() == item_name.lower()), None)
    if not item_to_equip:
        return f"{actor.name} does not have a '{item_name}' in their inventory."

    item_location = item_to_equip.get("location")
    if not item_location or item_location == "none":
        return f"The '{item_name}' is not something that can be equipped."

    equipped_items_in_location = [item for item in actor.equipment if item.get("location") == item_location]
    
    location_limits = {"head": 1, "chest": 1, "hand": 2} 
    limit = location_limits.get(item_location, 1)

    if len(equipped_items_in_location) >= limit:
        occupied_by_names = ", ".join([item['name'] for item in equipped_items_in_location])
        return f"Cannot equip '{item_name}'. The '{item_location}' location is already occupied by: {occupied_by_names}. You must unequip an item first."

    actor.inventory.remove(item_to_equip)
    actor.equipment.append(item_to_equip)
    return f"{actor.name} equips the {item_to_equip['name']}."

def execute_unequip_item(actor_name, item_name):
    """Moves an item from equipment back to inventory."""
    actor = next((e for e in game_state["players"] + game_state["npcs"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    item_to_unequip = next((item for item in actor.equipment if item['name'].lower() == item_name.lower()), None)
    if not item_to_unequip:
        return f"{actor.name} does not have a '{item_name}' equipped."

    actor.equipment.remove(item_to_unequip)
    actor.inventory.append(item_to_unequip)
    return f"{actor.name} unequips the {item_to_unequip['name']}."

def pass_turn(actor_name, reason="", **kwargs):
    """Allows a character to wait, speak, or do nothing for their turn."""
    cleaned_reason = reason.strip().strip('"')
    return f'{actor_name}: "{cleaned_reason}"' if cleaned_reason else f"{actor_name} waits."

# --- 4. AI Tool Definitions & Execution ---
# --- MODIFIED: The toolset is updated for zones, range, and new actions ---
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_look", "description": "Get a detailed description of the current room, including zones, objects, exits, and other characters.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
    {   "type": "function", "function": {
            "name": "execute_check_self", "description": "Check your own character's status, including health, condition, equipment, inventory, and location.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
    {   "type": "function", "function": {
            "name": "execute_move", "description": "Move your character through a named exit into an adjacent room.",
            "parameters": {"type": "object", "properties": { "exit_name": {"type": "string", "description": "The name of the exit to move through."}}, "required": ["exit_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_move_zone", "description": "Move to an adjacent numbered zone within the current room to change position.",
            "parameters": {"type": "object", "properties": { "target_zone": {"type": "integer", "description": "The number of the adjacent zone to move to."}}, "required": ["target_zone"]}}},
    {   "type": "function", "function": {
            "name": "execute_attack", "description": "Performs an attack against a single target in the same room. The success depends on weapon range and zone distance.",
            "parameters": {"type": "object", "properties": { "target_name": {"type": "string", "description": "The name of the character being attacked."}}, "required": ["target_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_skill_check", "description": "Use a skill on an object, an exit, or another character in the same zone.",
            "parameters": {"type": "object", "properties": {
                "skill_name": {"type": "string", "description": "The name of the skill being used, e.g., 'Search'."},
                "target_name": {"type": "string", "description": "Optional: The character being targeted by the skill (must be in the same zone)."},
                "object_name": {"type": "string", "description": "Optional: The object or exit being targeted by the skill (must be in the right zone)."}}, "required": ["skill_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_take_item", "description": "Take an item from a container, an object, or an incapacitated character in your current zone.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item to take."},
                "source_name": {"type": "string", "description": "The name of the object or character to take from."}}, "required": ["item_name", "source_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_drop_item", "description": "Drop an item from your inventory or equipment onto the floor of your current zone.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item you want to drop."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_equip_item", "description": "Equip an item from your inventory. You cannot equip an item if the location (e.g. head, chest, hands) is already full.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item from your inventory to equip."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_unequip_item", "description": "Unequip an item, moving it from your equipment to your inventory.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item you are currently wearing/wielding."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "pass_turn", "description": "Use this if the character wants to wait, do nothing, defend, or say something that doesn't require a skill check.",
            "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Optional: a brief reason for passing, such as dialogue."}},"required": []}}}
]

def get_llm_action_and_execute(command, actor, is_combat):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """
    actor_room = game_state["environment"].get_room(actor.current_room)
    other_chars_in_room = [e for e in game_state['players'] + game_state['npcs'] if e.id != actor.id and e.current_room == actor.current_room]
    
    current_zone_data = actor_room.get("zones", {}).get(str(actor.current_zone), {})
    adjacent_zones = current_zone_data.get("adjacent_zones", [])
    character_locations = ", ".join([f"{c.name} in Zone {c.current_zone}" for c in other_chars_in_room]) or 'None'
    objects_in_room = [o for o in actor_room.get("objects", [])]
    object_locations = ", ".join([f"{o['name']} in Zone {o.get('zone', 'N/A')}" for o in objects_in_room]) or 'None'

    # --- FIXED: Replaced vague prompts with a more explicit, rule-based prompt to guide the AI ---
    prompt_template = """You are an AI assistant for a text-based game. Your task is to translate a player's command into a specific function call.
Player Command: '{command}'

**CONTEXT**
- Your Status: {actor_description}
- Your Location: Zone {actor_zone}
- Adjacent Zones: {adjacent_zones}
- Characters Present: {character_locations}
- Interactable Objects & Exits Present: {object_locations}

**FUNCTION SELECTION RULES - Follow these steps:**
1.  **Is the command an attack on a CHARACTER?**
    - If yes, call `execute_attack`.
    - The `target_name` parameter MUST be a character from the 'Characters Present' list.

2.  **Is the command using a skill (like search, lift, investigate, track) on an OBJECT or EXIT?**
    - If yes, you **MUST** call `execute_skill_check`.
    - The `skill_name` should be the skill used (e.g., 'Search').
    - The `object_name` **MUST** be the name of the object/exit from the 'Interactable Objects & Exits Present' list (e.g., 'Crumbling Stones').
    - Do **NOT** use the `target_name` parameter for objects/exits.

3.  **Is the command using a skill on another CHARACTER?**
    - If yes, call `execute_skill_check`.
    - The `target_name` **MUST** be a character from the 'Characters Present' list.
    - Do **NOT** use the `object_name` parameter for characters.

4.  **Is the command to move between ZONES?**
    - If yes, call `execute_move_zone`.

5.  **If none of the above rules match**, choose another appropriate function like `execute_look`, `execute_move` (for room exits), `execute_take_item`, or `pass_turn`.

Based on these strict rules, select the correct function and parameters.
"""

    prompt = prompt_template.format(
        actor_description=actor.get_status_summary(),
        actor_zone=actor.current_zone,
        adjacent_zones=", ".join(map(str, adjacent_zones)) or "None",
        character_locations=character_locations,
        object_locations=object_locations,
        command=command
    )
    if DEBUG: print(f"\n[DEBUG] PROMPT FOR LLM ACTION:\n---\n{prompt}\n---\n")

    # Prepare and send the request to the AI model
    headers = {"Content-Type": "application/json"}
    payload = {"model": ACTION_MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        if DEBUG: print(f"[DEBUG] LLM Action Response: {json.dumps(response, indent=2)}")

        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return f"{actor.name} is unable to decide on an action and passes the turn."
            
        # Extract the function name and arguments from the AI's response
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        arguments['actor_name'] = actor.name

        # Call the chosen function
        if function_name == "execute_attack": return execute_attack(**arguments)
        if function_name == "execute_skill_check": return execute_skill_check(**arguments)
        if function_name == "execute_take_item": return execute_take_item(**arguments)
        if function_name == "execute_drop_item": return execute_drop_item(**arguments)
        if function_name == "execute_equip_item": return execute_equip_item(**arguments)
        if function_name == "execute_unequip_item": return execute_unequip_item(**arguments)
        if function_name == "pass_turn": return pass_turn(**arguments)
        if function_name == "execute_move": return execute_move(**arguments)
        if function_name == "execute_move_zone": return execute_move_zone(**arguments)
        if function_name == "execute_look": return execute_look(**arguments)
        if function_name == "execute_check_self": return execute_check_self(**arguments)
        
        return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e:
        return f"Error communicating with AI: {e}"

# --- 5. Enemy AI & Narrative LLM ---
def get_enemy_action(enemy_actor, is_combat_mode, last_summary):
    """
    Determines an NPC's action based on its personality and the current situation.
    """
    # --- Special logic for mindless traps ---
    if "mindless" in enemy_actor.statuses and "mechanical" in enemy_actor.statuses:
        # Mindless traps only act if a player enters their specific zone
        if enemy_actor.is_incapacitated():
            return f"The {enemy_actor.name} lies dormant on the floor, already sprung."
            
        players_in_zone = [p for p in game_state["players"] if p.current_room == enemy_actor.current_room and p.current_zone == enemy_actor.current_zone and not p.is_incapacitated()]
        if players_in_zone:
            # The trap makes an attack against a random player in its zone
            player_to_ambush = random.choice(players_in_zone)
            attack_summary = execute_attack(actor_name=enemy_actor.name, target_name=player_to_ambush.name)
            enemy_actor.current_wound_index = WOUND_LEVEL_DEAD # Mark the trap as sprung
            attack_summary += f"\n  -> The {enemy_actor.name} has been sprung!"
            return attack_summary
        return f"The {enemy_actor.name} sits silently."

    # --- Standard combat logic for hostile npcs ---
    if is_combat_mode and enemy_actor.attitude == ATTITUDE_HOSTILE:
        # --- MODIFIED: Enemy AI is now zone-aware ---
        players_in_room = [p for p in game_state["players"] if p.current_room == enemy_actor.current_room and not p.is_incapacitated()]
        if not players_in_room:
             return pass_turn(actor_name=enemy_actor.name, reason="All targets have fled or are defeated.")
        
        weapon = enemy_actor.get_weapon_details()
        weapon_range = weapon.get("range", 0)
        
        # Find all players that are within the weapon's range
        targets_in_range = []
        for p in players_in_room:
            dist = get_zone_distance(enemy_actor.current_zone, p.current_zone, enemy_actor.current_room)
            if dist != -1 and dist <= weapon_range:
                targets_in_range.append(p)
        
        # If there's a target in range, attack it.
        if targets_in_range:
            return execute_attack(actor_name=enemy_actor.name, target_name=random.choice(targets_in_range).name)
        else:
            # If no target is in range, try to move closer to the nearest player.
            nearest_player = min(players_in_room, key=lambda p: get_zone_distance(enemy_actor.current_zone, p.current_zone, enemy_actor.current_room))
            current_dist = get_zone_distance(enemy_actor.current_zone, nearest_player.current_zone, enemy_actor.current_room)
            adj_zones = game_state["environment"].get_room(enemy_actor.current_room).get("zones", {}).get(str(enemy_actor.current_zone), {}).get("adjacent_zones", [])
            
            # Simple AI: move to the first adjacent zone that gets it closer.
            for zone in adj_zones:
                if get_zone_distance(zone, nearest_player.current_zone, enemy_actor.current_room) < current_dist:
                    return execute_move_zone(actor_name=enemy_actor.name, target_zone=zone)
            # If no move gets it closer, wait.
            return pass_turn(actor_name=enemy_actor.name, reason="is unable to get closer.")

    # --- Non-combat or non-hostile dialogue ---
    return get_npc_dialogue(enemy_actor, last_summary)

def get_npc_dialogue(actor, context):
    """Generates dialogue for an NPC using the narrative AI model."""
    actor_description = actor.get_status_summary()
    prompt_template = scenario_data["prompts"]["npc_dialogue"]
    prompt = prompt_template.format(actor_description=actor_description, context=context)
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
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
    actor_room_key = actor.current_room
    entities_in_room = [e for e in game_state['players'] + game_state['npcs'] if e.current_room == actor_room_key]
    statuses = "\n".join([p.get_status_summary() for p in entities_in_room]) if entities_in_room else "None"
    
    actor_room = game_state["environment"].get_room(actor.current_room)
    prompt_template = scenario_data["prompts"]["narrative_summary"]

    # Format the prompt with all the necessary context
    prompt = prompt_template.format(
        actor_name=actor.name,
        room_name=actor_room.get("name"),
        room_description=actor_room.get("description"),
        statuses=statuses,
        mechanical_summary=mechanical_summary
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}]}
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
            scenario_data = json.load(f)
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
    log_filename = f"game_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    original_stdout = sys.stdout
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        # Redirect all print statements to both the console and the log file
        sys.stdout = Tee(original_stdout, log_file)

        if not load_scenario(SCENARIO_FILE) or not setup_initial_encounter():
            sys.stdout = original_stdout
            return

        # Keywords to help determine the type of input
        action_keywords = ["attack", "climb", "lift", "run", "swim", "dodge", "fly", "ride", "pilot", "operate", "pick", "repair", "craft", "track", "move", "go", "enter", "use", "look", "search", "take", "get", "grab", "check", "status", "inventory", "shoot", "drop", "equip", "unequip", "wear", "remove"]
        mechanical_summary_keywords = ["attack:", "hit!", "miss!", "roll:", "success", "failure", "vs dn"]
        
        player = game_state["players"][0]
        initial_look = execute_look(player.name)
        print(f"\nSCENE START: {scenario_data.get('scenario_name', 'Unnamed Scenario')}\n{initial_look}")

        is_combat_mode = False
        turn_summaries = []
        # Initial turn order is just players then npcs
        game_state["turn_order"] = game_state["players"] + game_state["npcs"]
        last_active_actor = player

        # --- The Game Loop ---
        while True:
            # Check if combat should start or end
            player_room = game_state["players"][0].current_room
            hostiles_in_room = any(e.attitude == ATTITUDE_HOSTILE and e.current_room == player_room and not e.is_incapacitated() for e in game_state["npcs"])
            
            # Start combat if it's not already active and there are hostiles
            if not is_combat_mode and hostiles_in_room and any(p.attitude == ATTITUDE_HOSTILE for p in game_state["players"]):
                print("\n" + "="*20); print("HOSTILITIES DETECTED! Entering Combat Mode!"); print("="*20)
                is_combat_mode = True; game_state["round_number"] = 1
                roll_initiative()
                if not game_state["turn_order"]:
                    print("No one is left to fight.")
                    is_combat_mode = False
                else:
                    print(f"\n--- Beginning Combat Round {game_state['round_number']} ---")
                game_state["current_turn_entity_index"] = 0
            
            # End combat if it's active but there are no more hostiles
            elif is_combat_mode and not hostiles_in_room:
                print("\n" + "="*20); print("COMBAT ENDS. No active hostiles present."); print("="*20)
                is_combat_mode = False
                game_state["turn_order"] = game_state["players"] + game_state["npcs"]
                game_state["current_turn_entity_index"] = 0

            # --- End of Round Summary ---
            if game_state["current_turn_entity_index"] >= len(game_state["turn_order"]):
                last_turn_actor = last_active_actor
                # Find the last significant action to summarize for the narrator
                action_summary_for_narrator = next((s for s in reversed(turn_summaries) if any(k in s.lower() for k in mechanical_summary_keywords)), "The characters paused and took in their surroundings.")
                print(f"\nNARRATIVE SUMMARY:\n{get_llm_story_response(action_summary_for_narrator, last_turn_actor)}\n")
                
                turn_summaries = []
                game_state["current_turn_entity_index"] = 0
                if is_combat_mode:
                    game_state["round_number"] += 1
                    print(f"--- End of Combat Round {game_state['round_number'] - 1} ---")
                    roll_initiative() # Re-roll initiative for the new round
                    if not game_state["turn_order"]:
                        is_combat_mode = False
                    else:
                        print(f"\n--- Beginning Combat Round {game_state['round_number']} ---")
            
            if not game_state["turn_order"]:
                print("No one available. Game over?")
                break

            current_entity = game_state["turn_order"][game_state["current_turn_entity_index"]]

            # Skip turns for characters not in the player's room during non-combat
            if not is_combat_mode and current_entity.current_room != player.current_room:
                game_state["current_turn_entity_index"] += 1
                continue

            summary = ""
            if current_entity.is_incapacitated():
                summary = f"{current_entity.name} is incapacitated and cannot act."
            else:
                # --- Player's Turn ---
                if current_entity in game_state["players"]:
                    command = input(f"Your action, {current_entity.name} (in {current_entity.current_room}, Zone {current_entity.current_zone}): ")
                    if command.lower() in ["quit", "exit"]:
                        print("Exiting game.")
                        break
                    
                    # If the command looks like an action, send it to the AI for interpretation
                    if any(keyword in command.lower() for keyword in action_keywords):
                        summary = get_llm_action_and_execute(command, current_entity, is_combat_mode)
                    else: # Otherwise, treat it as simple dialogue
                        summary = pass_turn(actor_name=current_entity.name, reason=command)
                
                # --- NPC's Turn ---
                else:
                    last_summary = turn_summaries[-1] if turn_summaries else "The scene begins."
                    summary = get_enemy_action(current_entity, is_combat_mode, last_summary)

            # Print the outcome of the turn
            if summary:
                # Check if the summary is just dialogue.
                is_dialogue = summary.strip().startswith(f'{current_entity.name}: "') and summary.strip().endswith('"')

                if is_dialogue:
                    print(f"\n{summary}\n") # Print only the dialogue
                else:
                    # For all other actions, use the detailed outcome format
                    print(f"\n-- Outcome for {current_entity.name}'s turn --\n{summary}\n----------------------------------")
                
                turn_summaries.append(summary)
                last_active_actor = current_entity

            # Move to the next character in the turn order
            game_state["current_turn_entity_index"] += 1

    # Restore standard output and inform the user where the log file is saved
    sys.stdout = original_stdout
    print(f"Game log saved to: {log_filename}")

if __name__ == "__main__":
    main_game_loop()