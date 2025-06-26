import random
import requests
import json
import os
import sys
from datetime import datetime
from d6_rules import *

# --- Configuration ---
# These settings control the connection to the AI models and game files.
# You can change the API key, model names, and file paths here.
ACTION_MODEL = "local-model/gemma-3-1b"  # Model used for deciding character actions
NARRATIVE_MODEL = "local-model/gemma-3-1b" # Model used for generating descriptive text
OPENROUTER_API_URL = "http://localhost:1234/v1/chat/completions" # Local server URL
SCENARIO_FILE = "scenario.json"      # The file containing the game's story and setup
DEBUG = True                         # Set to True to print extra debugging information

# --- Global State Variables ---
# These variables store the game's data and are accessed throughout the program.
scenario_data = {}  # Holds all the data from the scenario.json file
game_state = {
    "players": [], "enemies": [], "environment": None,
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
        self.starting_room = environment_data.get("starting_room", "")

    def get_room(self, room_key):
        """Returns the data for a specific room."""
        return self.rooms.get(room_key)

class GameEntity:
    """Represents a character (player or NPC) in the game."""
    def __init__(self, character_sheet_data, starting_room):
        # Basic information
        self.source_data = character_sheet_data
        self.id = character_sheet_data["id"]
        self.name = character_sheet_data["name"]
        
        # Personality and attitude
        self.personality = character_sheet_data.get("personality", "neutral")
        self.attitude = character_sheet_data.get("attitude", ATTITUDE_INDIFFERENT)
        
        # Attributes, skills, and equipment
        self.attributes = {k.lower(): v for k, v in character_sheet_data.get("attributes", {}).items()}
        self.skills = {k.lower(): v for k, v in character_sheet_data.get("skills", {}).items()}
        self.equipment = character_sheet_data.get("equipment", [])
        
        # Combat-related stats
        self.current_wound_index = WOUND_LEVEL_HEALTHY
        self.initiative_roll = 0
        self.current_room = starting_room

    def get_attribute_descriptors_string(self):
        """
        Creates a human-readable string of the character's attributes.
        Example: "Physique: Strong, Dexterity: Agile"
        """
        descriptors = []
        for attr, pips in self.attributes.items():
            descriptor = get_attribute_descriptor(attr, pips)
            if descriptor and descriptor != "Average":
                descriptors.append(f"{attr.capitalize()}: {descriptor}")
        return ", ".join(descriptors) if descriptors else "Average"

    def get_status_summary(self):
        """Provides a quick summary of the character's current state."""
        base_summary = f"{self.name} (Status: {self.get_wound_status()}, Room: {self.current_room})"
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
        """
        Calculates and applies damage to the character.
        
        Args:
            damage_roll_total (int): The total from the damage roll.
            resistance_roll_total (int): The total from the resistance roll.
            
        Returns:
            str: A summary of the damage outcome.
        """
        if self.is_incapacitated():
            return f"{self.name} is already out of action."
            
        outcome = f"Damage roll: {damage_roll_total} vs Resistance roll: {resistance_roll_total}. "
        if damage_roll_total <= resistance_roll_total:
            outcome += f"{self.name} resists the damage."
            return outcome

        damage_difference = damage_roll_total - resistance_roll_total
        
        # Determine the new wound level based on the damage difference
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
        """
        Gets the total number of pips for a given attribute or skill.
        If it's a skill, it adds the governing attribute's pips.
        """
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
        """
        Finds a weapon in the character's equipment.
        Defaults to an unarmed attack if no weapon is found.
        """
        for item in self.equipment:
            if item.get("type", "").lower() == "weapon":
                if weapon_name_or_type == "melee" and item.get("skill", "").lower() in ["melee_combat", "brawling"]:
                    return item
        
        # Default to unarmed strike if no weapon is equipped
        return {"name": "Unarmed", "skill": "brawling", "damage": self.attributes.get("physique", 6), "range": "melee"}

# --- 3. Discrete Action Functions ---
# These functions define the specific actions characters can take in the game.
def execute_look(actor_name, **kwargs):
    """Provides a detailed description of the character's current surroundings."""
    actor = next((e for e in game_state["players"] + game_state["enemies"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return "Could not find actor to 'look' for."

    room = game_state["environment"].get_room(actor.current_room)
    if not room: return f"{actor.name} is in an unknown location."

    # Find other characters, objects, and exits in the room
    visible_chars = [e.name for e in game_state["players"] + game_state["enemies"] if e.current_room == actor.current_room and e.id != actor.id]
    objects = [f"{obj['name']}: {obj['description']}" for obj in room.get("objects", [])]
    exits = [f"{exit['name']}: {exit['description']}" for exit in room.get("exits", [])]

    # Build the description string
    response = f"--- {room.get('name', 'Unnamed Room')} ---\n"
    response += room.get('description', 'No description available.') + "\n"
    if visible_chars: response += "\nVisible Characters: " + ", ".join(visible_chars) + "\n"
    if objects: response += "\nObjects: \n- " + "\n- ".join(objects) + "\n"
    if exits: response += "\nExits: \n- " + "\n- ".join(exits) + "\n"
    
    return response

def execute_move(actor_name, exit_name):
    """Moves the character through a specified exit to another room."""
    actor = next((e for e in game_state["players"] + game_state["enemies"] if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."

    room = game_state["environment"].get_room(actor.current_room)
    if not room: return f"{actor.name} is in an unknown location and cannot move."

    target_exit = next((ext for ext in room.get("exits", []) if ext["name"].lower() == exit_name.lower()), None)
    if not target_exit: return f"{actor.name} cannot find an exit named '{exit_name}'."
    
    # Check if the exit is locked or blocked
    if "action" in target_exit:
        return f"{actor.name} must perform an action to use the {exit_name}. Try using the '{target_exit['action']['skill']}' skill."

    destination_key = target_exit.get("to_room")
    destination_room = game_state["environment"].get_room(destination_key)
    if not destination_room: return f"The exit '{exit_name}' leads nowhere."
    
    # Update the actor's location
    actor.current_room = destination_key
    return f"{actor.name} moves through the {exit_name} into the {destination_room.get('name', 'next room')}."

def execute_melee_attack(actor_name, target_name):
    """Executes a close-quarters physical attack with a melee weapon or unarmed strike."""
    all_entities = game_state["players"] + game_state["enemies"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
    
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."
    if not target_entity: return f"Action failed: Could not find target '{target_name}'."
    if actor.current_room != target_entity.current_room: return f"Action failed: {target_name} is not in the same room."

    weapon = actor.get_weapon_details("melee")
    outcome_summary = f"{actor.name} attacks {target_entity.name} with {weapon['name']}!"

    # If this is the first attack, attitudes become hostile
    if actor.attitude != ATTITUDE_HOSTILE:
        actor.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {actor.name} becomes Hostile by initiating an attack!"
    if target_entity.attitude != ATTITUDE_HOSTILE:
        target_entity.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {target_entity.name} becomes Hostile due to the attack!"

    # Perform the attack roll
    attack_skill_pips = actor.get_attribute_or_skill_pips(weapon.get("skill", "brawling"))
    success_level, _, attack_roll_str = roll_d6_check(actor, attack_skill_pips, 10) # Simplified Difficulty Number (DN)
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
    all_entities = game_state["players"] + game_state["enemies"]
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
        
        action_data = target_interactive.get("action")
        if not action_data:
            return f"'{object_name}' is not interactive."

        if not skill_name:
            skill_name = action_data.get("skill")
            if not skill_name:
                return f"It's unclear what skill to use on '{object_name}'."

        if action_data.get("skill", "").lower() != skill_name.lower():
            return f"You can't use '{skill_name}' on '{object_name}'. The required skill is '{action_data.get('skill')}'."
            
        # Perform the skill check
        difficulty_number = action_data.get("dn", 10)
        skill_pips = actor.get_attribute_or_skill_pips(skill_name)
        success_level, _, details_str = roll_d6_check(actor, skill_pips, difficulty_number)
        
        outcome_summary = f"{actor.name} uses their {skill_name} skill on {object_name}: {details_str}"
        if success_level > 0:
            outcome_summary += "\n  -> " + action_data.get("success_text", "It works!")
            if target_exit: # If an exit was successfully opened, remove the action lock
                target_exit.pop("action", None)
        else:
            outcome_summary += "\n  -> " + action_data.get("failure_text", "Nothing happens.")
        return outcome_summary

    # --- Logic for an opposed skill check against another character ---
    if target_name:
        target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
        if not target_entity: return f"Action failed: Could not find target '{target_name}'."
        if actor.current_room != target_entity.current_room: return f"Action failed: {target_name} is not in the same room."
        if not skill_name: return f"Action failed: must specify a skill to use on {target_name}."
        
        # Determine the resisting skill
        resisting_skill = "Willpower"
        normalized_skill_name = next((k for k in OPPOSED_SKILLS if k.lower() == skill_name.lower()), None)
        if normalized_skill_name and OPPOSED_SKILLS[normalized_skill_name]:
            resisting_skill = OPPOSED_SKILLS[normalized_skill_name][0]
            
        outcome_summary = f"{actor.name} uses their {skill_name} skill against {target_entity.name} (resisted by {resisting_skill})."
        
        # Perform the opposed roll
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

def pass_turn(actor_name, reason="", **kwargs):
    """Allows a character to wait, speak, or do nothing for their turn."""
    cleaned_reason = reason.strip().strip('"')
    return f'{actor_name}: "{cleaned_reason}"' if cleaned_reason else f"{actor_name} waits."

# --- 4. AI Tool Definitions & Execution ---
# This section defines the tools (functions) that the AI model can use.
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_look",
            "description": "Get a detailed description of the current room, including objects, exits, and other characters.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
    {   "type": "function", "function": {
            "name": "execute_move",
            "description": "Move your character through a named exit into an adjacent room.",
            "parameters": {"type": "object", "properties": { "exit_name": {"type": "string", "description": "The name of the exit to move through, e.g., 'Stone Archway'."}}, "required": ["exit_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_melee_attack",
            "description": "Performs a close-quarters physical attack against a single target in the same room.",
            "parameters": {"type": "object", "properties": { "target_name": {"type": "string", "description": "The name of the character being attacked."}}, "required": ["target_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_skill_check",
            "description": "Use a skill on an object, an exit, or another character.",
            "parameters": {"type": "object", "properties": {
                "skill_name": {"type": "string", "description": "The name of the skill being used, e.g., 'Search', 'Lifting'."},
                "target_name": {"type": "string", "description": "Optional: The character being targeted by the skill."},
                "object_name": {"type": "string", "description": "Optional: The object or exit being targeted by the skill."}}, "required": ["skill_name"]}}},
    {   "type": "function", "function": {
            "name": "pass_turn",
            "description": "Use this if the character wants to wait, do nothing, defend, or say something that doesn't require a skill check.",
            "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Optional: a brief reason for passing, such as a line of dialogue."}},"required": []}}}
]

def get_llm_action_and_execute(command, actor, is_combat):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """
    actor_room = game_state["environment"].get_room(actor.current_room)
    other_chars_in_room = [e.name for e in game_state['players'] + game_state['enemies'] if e.id != actor.id and e.current_room == actor.current_room]
    
    # Choose the appropriate prompt based on whether it's combat or not
    prompt_template_key = "combat" if is_combat else "non_combat"
    prompt_template = scenario_data["prompts"]["action_selection"][prompt_template_key]
    prompt = prompt_template.format(
        room_name=actor_room.get("name"),
        room_description=actor_room.get("description"),
        actor_description=actor.get_status_summary(),
        other_chars=', '.join(other_chars_in_room) or 'None',
        objects=', '.join([o['name'] for o in actor_room.get("objects", [])]) or 'None',
        exits=', '.join([e['name'] for e in actor_room.get("exits", [])]) or 'None',
        command=command
    )
    if DEBUG: print(f"\n[DEBUG] PROMPT FOR LLM ACTION:\n---\n{prompt}\n---\n")

    # Prepare and send the request to the AI model
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": ACTION_MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
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
        if function_name == "execute_melee_attack": return execute_melee_attack(**arguments)
        if function_name == "execute_skill_check": return execute_skill_check(**arguments)
        if function_name == "pass_turn": return pass_turn(**arguments)
        if function_name == "execute_move": return execute_move(**arguments)
        if function_name == "execute_look": return execute_look(**arguments)
        
        return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e:
        return f"Error communicating with AI: {e}"

# --- 5. Enemy AI & Narrative LLM ---
def get_enemy_action(enemy_actor, is_combat_mode, last_summary):
    """
    Determines an NPC's action based on its personality and the current situation.
    """
    # --- Special logic for mindless traps ---
    if enemy_actor.personality == "mindless, mechanical":
        if enemy_actor.is_incapacitated():
            return f"The {enemy_actor.name} lies dormant on the floor, already sprung."
            
        players_in_room = [p for p in game_state["players"] if p.current_room == enemy_actor.current_room and not p.is_incapacitated()]
        if players_in_room:
            # The trap makes an opposed check to see if it can ambush a player
            player_to_ambush = random.choice(players_in_room)
            trap_stealth_pips = enemy_actor.get_attribute_or_skill_pips("Stealth")
            trap_roll, _ = roll_d6_dice(trap_stealth_pips)
            player_perception_pips = player_to_ambush.get_attribute_or_skill_pips("Perception")
            player_roll, _ = roll_d6_dice(player_perception_pips)

            if trap_roll > player_roll: # Ambush successful
                attack_summary = execute_melee_attack(actor_name=enemy_actor.name, target_name=player_to_ambush.name)
                enemy_actor.current_wound_index = WOUND_LEVEL_DEAD # Mark the trap as sprung
                attack_summary += f"\n  -> The {enemy_actor.name} has been sprung and is no longer a threat."
                return attack_summary
            else: # Player spots the trap
                return f"The {enemy_actor.name} remains hidden, but {player_to_ambush.name} spots it!"
        return f"The {enemy_actor.name} sits silently."

    # --- Standard combat logic for hostile enemies ---
    if is_combat_mode and enemy_actor.attitude == ATTITUDE_HOSTILE:
        active_players_in_room = [p for p in game_state["players"] if not p.is_incapacitated() and p.current_room == enemy_actor.current_room]
        if active_players_in_room:
            # Attack a random player in the room
            return execute_melee_attack(actor_name=enemy_actor.name, target_name=random.choice(active_players_in_room).name)
        else:
            return pass_turn(actor_name=enemy_actor.name, reason="All targets have fled or are defeated.")

    # --- Non-combat or non-hostile dialogue ---
    return get_npc_dialogue(enemy_actor, last_summary)

def get_npc_dialogue(actor, context):
    """Generates dialogue for an NPC using the narrative AI model."""
    actor_description = actor.get_status_summary()
    prompt_template = scenario_data["prompts"]["npc_dialogue"]
    prompt = prompt_template.format(actor_description=actor_description, context=context)
    
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
        dialogue = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return f'{actor.name}: "{dialogue}"' if dialogue else f"{actor.name} remains silent."
    except Exception as e:
        return f"LLM Error (Narration): Could not get dialogue. {e}"

def get_llm_story_response(mechanical_summary, actor):
    """
    Generates a narrative summary of the events that just occurred.
    
    Args:
        mechanical_summary (str): The raw text describing the action's outcome.
        actor (GameEntity): The character who just took the action.
        
    Returns:
        str: A story-like description of the events.
    """
    actor_room_key = actor.current_room
    entities_in_room = [e for e in game_state['players'] + game_state['enemies'] if e.current_room == actor_room_key]
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
    
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}]}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
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
    Sets up the game by loading the environment and creating the player and enemy characters.
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
        if sheet: game_state["players"].append(GameEntity(sheet, player_config["starting_room"]))
    for enemy_config in char_configs.get("enemies", []):
        sheet = load_character_sheet(os.path.join(characters_dir, enemy_config["sheet"]))
        if sheet: game_state["enemies"].append(GameEntity(sheet, enemy_config["starting_room"]))

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
    participants = [e for e in game_state["players"] + game_state["enemies"] if not e.is_incapacitated() and e.attitude == ATTITUDE_HOSTILE and e.current_room == player_room]
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
        action_keywords = ["attack", "climb", "lift", "run", "swim", "dodge", "fly", "ride", "pilot", "operate", "pick", "repair", "craft", "track", "move", "go", "enter", "use", "look", "search"]
        mechanical_summary_keywords = ["attack:", "hit!", "miss!", "roll:", "success", "failure", "vs dn"]
        
        player = game_state["players"][0]
        initial_look = execute_look(player.name)
        print(f"\nSCENE START: {scenario_data.get('scenario_name', 'Unnamed Scenario')}\n{initial_look}")

        is_combat_mode = False
        turn_summaries = []
        # Initial turn order is just players then enemies
        game_state["turn_order"] = game_state["players"] + game_state["enemies"] 

        # --- The Game Loop ---
        while True:
            # Check if combat should start or end
            player_room = game_state["players"][0].current_room
            hostiles_in_room = any(e.attitude == ATTITUDE_HOSTILE and e.current_room == player_room and not e.is_incapacitated() for e in game_state["enemies"])
            
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
                game_state["turn_order"] = game_state["players"] + game_state["enemies"]
                game_state["current_turn_entity_index"] = 0

            # --- End of Round Summary ---
            if game_state["current_turn_entity_index"] >= len(game_state["turn_order"]):
                last_turn_actor = game_state["turn_order"][game_state["current_turn_entity_index"]-1] if game_state["turn_order"] else player
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
                if current_entity.personality == "mindless, mechanical":
                    summary = f"The {current_entity.name} lies dormant on the floor, already sprung."
                print(summary)
            else:
                # --- Player's Turn ---
                if current_entity in game_state["players"]:
                    command = input(f"Your action, {current_entity.name} (in {current_entity.current_room}): ")
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
                print(f"\n-- Outcome for {current_entity.name}'s turn --\n{summary}\n----------------------------------")
                turn_summaries.append(summary)

            # --- Check for End Game Conditions ---
            if all(e.is_incapacitated() for e in game_state["enemies"]):
                print(f"\nVICTORY! All enemies have been defeated!")
                break
            if all(p.is_incapacitated() for p in game_state["players"]):
                print(f"\nGAME OVER! All players are incapacitated!")
                break

            # Move to the next character in the turn order
            game_state["current_turn_entity_index"] += 1

    # Restore standard output and inform the user where the log file is saved
    sys.stdout = original_stdout
    print(f"Game log saved to: {log_filename}")

if __name__ == "__main__":
    main_game_loop()