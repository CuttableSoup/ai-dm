import random
import requests
import json
import os
import sys
from datetime import datetime
from d6_rules import *

# --- Configuration ---
OPENROUTER_API_KEY = "not-required"
ACTION_MODEL = "local-model/gemma-12b-it"
NARRATIVE_MODEL = "local-model/gemma-12b-it"
OPENROUTER_API_URL = "http://localhost:1234/v1/chat/completions"
SCENARIO_FILE = "scenario.json"
DEBUG = False

# --- Global State Variables ---
scenario_data = {}
game_state = {
    "players": [], "enemies": [], "environment_description": "An uninitialized scene.",
    "turn_order": [], "current_turn_entity_index": 0, "round_number": 1
}

# --- 1. Character Sheet Loading Utility ---
def load_character_sheet(filepath):
    """Loads a character sheet from a JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Character sheet file not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON from {filepath}")
        return None

# --- 2. Game Entity Class ---
class GameEntity:
    """Represents a character (player or NPC) in the game."""
    def __init__(self, character_sheet_data):
        self.source_data = character_sheet_data
        self.id = character_sheet_data["id"]
        self.name = character_sheet_data["name"]
        self.personality = character_sheet_data.get("personality", "neutral")
        self.attitude = character_sheet_data.get("attitude", ATTITUDE_INDIFFERENT)
        self.attributes = {k.lower(): v for k, v in character_sheet_data.get("attributes", {}).items()}
        self.skills = {k.lower(): v for k, v in character_sheet_data.get("skills", {}).items()}
        self.equipment = character_sheet_data.get("equipment", [])
        self.current_wound_index = WOUND_LEVEL_HEALTHY
        self.initiative_roll = 0

    def get_attribute_descriptors_string(self):
        """Returns a string of the character's attribute descriptors if enabled."""
        descriptors = []
        for attr, pips in self.attributes.items():
            descriptor = get_attribute_descriptor(attr, pips)
            if descriptor and descriptor != "Average":
                descriptors.append(f"{attr.capitalize()}: {descriptor}")
        
        if not descriptors:
            return "Average"
        return ", ".join(descriptors)

    def get_status_summary(self):
        """Returns a full summary string for the character, including descriptors."""
        base_summary = f"{self.name} (Status: {self.get_wound_status()}, Attitude: {self.attitude}, Personality: {self.personality}"
        descriptors = self.get_attribute_descriptors_string()
        if descriptors:
            base_summary += f", Traits: {descriptors}"
        base_summary += ")"
        return base_summary

    def get_wound_status(self):
        """Returns the string representation of the character's current wound level."""
        return {
            WOUND_LEVEL_HEALTHY: "Healthy",
            WOUND_LEVEL_STUNNED: "Stunned",
            WOUND_LEVEL_WOUNDED: "Wounded (-1D)",
            WOUND_LEVEL_SEVERELY_WOUNDED: "Severely Wounded (-2D)",
            WOUND_LEVEL_INCAPACITATED: "Incapacitated",
            WOUND_LEVEL_MORTALLY_WOUNDED: "Mortally Wounded",
            WOUND_LEVEL_DEAD: "Dead"
        }.get(self.current_wound_index, "Unknown")

    def get_wound_penalty_pips(self):
        """Returns the number of pips to subtract from rolls due to wounds."""
        if self.current_wound_index == WOUND_LEVEL_WOUNDED: return 3
        if self.current_wound_index == WOUND_LEVEL_SEVERELY_WOUNDED: return 6
        return 0

    def apply_damage(self, damage_roll_total, resistance_roll_total):
        """Calculates and applies damage to the character, updating their wound level."""
        if self.is_incapacitated(): return f"{self.name} is already out of action."
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
        """Checks if the character is incapacitated, mortally wounded, or dead."""
        return self.current_wound_index <= WOUND_LEVEL_INCAPACITATED

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total pips for a given skill or attribute."""
        trait_name_lower = trait_name.lower()
        governing_attribute_name = None
        for attr_key, skill_list in D6_SKILLS_BY_ATTRIBUTE.items():
            if trait_name_lower in [s.lower() for s in skill_list]:
                governing_attribute_name = attr_key.lower()
                break
        if governing_attribute_name:
            skill_pips = self.skills.get(trait_name_lower, 0)
            attribute_pips = self.attributes.get(governing_attribute_name, 0)
            return skill_pips + attribute_pips
        if trait_name_lower in self.attributes:
            return self.attributes[trait_name_lower]
        if DEBUG: print(f"[WARN] Trait '{trait_name}' not found for {self.name}. Returning 0 pips.")
        return 0

    def get_resistance_pips(self):
        """Calculates pips for resisting damage."""
        physique_pips = self.attributes.get("physique", 0)
        return max(0, physique_pips)

    def get_weapon_details(self, weapon_name_or_type="melee"):
        """Finds a weapon in the character's equipment."""
        for item in self.equipment:
            if item.get("type", "").lower() == "weapon":
                weapon_skill = item.get("skill", "").lower()
                if weapon_name_or_type == "melee" and weapon_skill in ["melee_combat", "brawling"]:
                    return item

        str_pips = self.attributes.get("physique", 6)
        return {"name": "Unarmed", "skill": "brawling", "damage": str_pips, "range": "melee"}

# --- 3. Discrete Action Functions (For AI Function Calling) ---
def execute_melee_attack(actor_name, target_name):
    """Executes a close-quarters physical attack with a melee weapon or unarmed strike."""
    all_entities = game_state["players"] + game_state["enemies"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."
    if not target_entity: return f"Action failed: Could not find target '{target_name}'."

    weapon = actor.get_weapon_details("melee")
    outcome_summary = f"{actor.name} attacks {target_entity.name} with {weapon['name']}!"

    if actor.attitude != ATTITUDE_HOSTILE:
        actor.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {actor.name} becomes Hostile by initiating an attack!"

    if target_entity.attitude != ATTITUDE_HOSTILE:
        target_entity.attitude = ATTITUDE_HOSTILE
        outcome_summary += f"\n  -> {target_entity.name} becomes Hostile due to the attack!"

    attack_skill_pips = actor.get_attribute_or_skill_pips(weapon.get("skill", "brawling"))
    success_level, _, attack_roll_str = roll_d6_check(actor, attack_skill_pips, 10) # Simplified DN
    outcome_summary += f"\n  Attack: {attack_roll_str}"
    if success_level > 0:
        outcome_summary += " Hit!"
        damage_pips = weapon.get("damage", 0) + ((success_level - 1) * 3)
        damage_roll, _ = roll_d6_dice(damage_pips)
        res_pips = target_entity.get_resistance_pips()
        res_roll, _ = roll_d6_dice(res_pips)
        damage_effect_str = target_entity.apply_damage(damage_roll, res_roll)
        outcome_summary += f"\n  {damage_effect_str}"
    else:
        outcome_summary += " Miss!"
    return outcome_summary

def execute_skill_check(actor_name, skill_name, target_name=None, difficulty_number=10):
    """Performs a general skill check. Can be opposed by a target or against a static difficulty."""
    all_entities = game_state["players"] + game_state["enemies"]
    actor = next((e for e in all_entities if e.name.lower() == actor_name.lower()), None)
    if not actor: return f"Action failed: Could not find actor '{actor_name}'."
    target_entity = None
    if target_name:
        target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
        if not target_entity: return f"Action failed: Could not find target '{target_name}'."

    outcome_summary = f"{actor.name} attempts to use '{skill_name}'."
    final_difficulty = difficulty_number
    if target_entity:
        resisting_skill = "Willpower"
        normalized_skill_name = next((k for k in OPPOSED_SKILLS if k.lower() == skill_name.lower()), None)
        if normalized_skill_name and OPPOSED_SKILLS[normalized_skill_name]:
            resisting_skill = OPPOSED_SKILLS[normalized_skill_name][0]
        outcome_summary += f"\n  Opposed by {target_entity.name}'s '{resisting_skill}'."
        resistance_pips = target_entity.get_attribute_or_skill_pips(resisting_skill)
        resistance_roll, _ = roll_d6_dice(resistance_pips)
        final_difficulty = resistance_roll
        outcome_summary += f"\n  Resistance roll sets Difficulty to {final_difficulty}."
    else:
        outcome_summary += f" against a static difficulty of {final_difficulty}."

    skill_pips = actor.get_attribute_or_skill_pips(skill_name)
    success_level, _, details_str = roll_d6_check(actor, skill_pips, final_difficulty)
    outcome_summary += f"\n  {actor.name}'s roll: {details_str}"
    return outcome_summary

def pass_turn(actor_name, reason="", **kwargs):
    """Returns a string indicating the character is waiting or speaking."""
    cleaned_reason = reason.strip().strip('"')
    if cleaned_reason:
        return f'{actor_name}: "{cleaned_reason}"'
    else:
        return f"{actor_name} waits."

# --- 4. AI Tool Definitions & Execution ---
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_melee_attack",
            "description": "Performs a close-quarters physical attack with a sword, axe, fists, etc., against a single target. This is a hostile action.",
            "parameters": {"type": "object", "properties": { "target_name": {"type": "string", "description": "The full name of the character being attacked, e.g., 'Orc Berserker'."}}, "required": ["target_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_skill_check",
            "description": "Use for any non-combat action that requires a skill. Examples: persuading someone, sneaking past a guard, searching a room, climbing a wall.",
            "parameters": {"type": "object", "properties": {
                "skill_name": {"type": "string", "description": "The name of the skill being used, e.g., 'Persuasion', 'Stealth', 'Search'."},
                "target_name": {"type": "string", "description": "Optional: The full name of the character being targeted or opposed by the skill."},
                "difficulty_number": {"type": "integer", "description": "Optional: A static difficulty number for unopposed checks. Defaults to 10."}}, "required": ["skill_name"]}}},
    {   "type": "function", "function": {
            "name": "pass_turn",
            "description": "Use this if the character wants to wait, do nothing, defend, observe, or say something that doesn't require a skill check.",
            "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Optional: a brief reason for passing, such as a line of dialogue."}},"required": []}}}
]

def get_llm_action_and_execute(command, actor, is_combat):
    """Sends command to LLM to get a function call, then executes it."""
    other_chars = [e.name for e in game_state['players'] + game_state['enemies'] if e.id != actor.id]
    actor_description = actor.get_status_summary()
    
    prompt_template_key = "combat" if is_combat else "non_combat"
    prompt_template = scenario_data["prompts"]["action_selection"][prompt_template_key]
    prompt = prompt_template.format(
        actor_description=actor_description,
        other_chars=', '.join(other_chars),
        command=command
    )

    if DEBUG:
        print(f"\n[DEBUG] PROMPT FOR LLM ACTION:\n---\n{prompt}\n---\n")

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": ACTION_MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
        if DEBUG:
            print(f"[DEBUG] LLM Action Response: {json.dumps(response, indent=2)}")

        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"): return f"{actor.name} is unable to decide on an action and passes the turn."
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        arguments['actor_name'] = actor.name

        if function_name == "execute_melee_attack": return execute_melee_attack(**arguments)
        elif function_name == "execute_skill_check": return execute_skill_check(**arguments)
        elif function_name == "pass_turn": return pass_turn(**arguments)
        else: return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e: return f"Error communicating with AI: {e}"

# --- 5. Enemy AI & Narrative LLM ---
def get_npc_dialogue(actor, context):
    """Generates a line of dialogue for an NPC using the NARRATIVE_MODEL."""
    actor_description = actor.get_status_summary()
    prompt_template = scenario_data["prompts"]["npc_dialogue"]
    prompt = prompt_template.format(
        actor_description=actor_description,
        context=context
    )

    if DEBUG:
        print(f"\n[DEBUG] PROMPT FOR NPC DIALOGUE:\n---\n{prompt}\n---\n")

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
        if DEBUG:
            print(f"[DEBUG] NPC Dialogue Response: {json.dumps(response, indent=2)}")

        dialogue = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return f'{actor.name}: "{dialogue}"' if dialogue else f"{actor.name} remains silent."
    except Exception as e:
        return f"LLM Error (Narration): Could not get dialogue. {e}"


def get_enemy_action(enemy_actor, is_combat_mode, last_summary):
    """Determines an NPC's action: attacks if in combat and hostile, otherwise speaks."""
    if is_combat_mode and enemy_actor.attitude == ATTITUDE_HOSTILE:
        active_players = [p for p in game_state["players"] if not p.is_incapacitated()]
        if active_players:
            return execute_melee_attack(actor_name=enemy_actor.name, target_name=random.choice(active_players).name)
        else:
            return pass_turn(actor_name=enemy_actor.name, reason="All targets are defeated.")

    return get_npc_dialogue(enemy_actor, last_summary)

def get_llm_story_response(mechanical_summary):
    """Gets a narrative response from an LLM."""
    statuses = "\n".join([p.get_status_summary() for p in game_state['players'] + game_state['enemies']])
    prompt_template = scenario_data["prompts"]["narrative_summary"]
    prompt = prompt_template.format(
        environment_description=game_state['environment_description'],
        statuses=statuses,
        mechanical_summary=mechanical_summary
    )

    if DEBUG:
        print(f"\n[DEBUG] PROMPT FOR NARRATIVE LLM:\n---\n{prompt}\n---\n")

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}]}
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30).json()
        if DEBUG:
            print(f"[DEBUG] Narrative LLM Response: {json.dumps(response, indent=2)}")
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or f"LLM (empty response): {mechanical_summary}"
    except Exception as e: return f"LLM Error: Could not get narration. {e}"

# --- 6. Initial Game Setup ---
def load_scenario(filepath):
    """Loads the scenario file."""
    global scenario_data
    try:
        with open(filepath, 'r') as f:
            scenario_data = json.load(f)
            return True
    except FileNotFoundError:
        print(f"ERROR: Scenario file not found at {filepath}")
        return False
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON from {filepath}")
        return False

def setup_initial_encounter():
    """Loads the encounter from the scenario data."""
    characters_dir = "."

    for player_file in scenario_data.get("characters", {}).get("players", []):
        player_sheet = load_character_sheet(os.path.join(characters_dir, player_file))
        if player_sheet:
            game_state["players"].append(GameEntity(player_sheet))
        else:
            print(f"Could not load player character: {player_file}. Exiting.")
            return False

    for enemy_file in scenario_data.get("characters", {}).get("enemies", []):
        enemy_sheet = load_character_sheet(os.path.join(characters_dir, enemy_file))
        if enemy_sheet:
            game_state["enemies"].append(GameEntity(enemy_sheet))
        else:
            print(f"Could not load enemy character: {enemy_file}. Exiting.")
            return False
            
    if not game_state["players"]:
        print("No players loaded. Exiting.")
        return False

    game_state["environment_description"] = scenario_data.get("environment", {}).get("description", "A featureless void.")
    return True

def roll_initiative():
    """Rolls initiative for all active combatants."""
    participants = [p for p in game_state["players"] + game_state["enemies"] if not p.is_incapacitated() and p.attitude == ATTITUDE_HOSTILE]
    for entity in participants:
        entity.initiative_roll, _ = roll_d6_dice(entity.get_attribute_or_skill_pips("Perception"))

    game_state["turn_order"] = sorted(participants, key=lambda e: e.initiative_roll, reverse=True)
    if game_state["turn_order"]:
        print("Combat Initiative Order: " + ", ".join([f"{e.name} ({e.initiative_roll})" for e in game_state["turn_order"]]))

# --- 7. Main Game Loop ---
class Tee:
    """Helper class to redirect stdout to both console and a file."""
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(str(obj))
            f.flush()
    def flush(self):
        for f in self.files: f.flush()

def main_game_loop():
    log_filename = f"game_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    original_stdout = sys.stdout
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        sys.stdout = Tee(original_stdout, log_file)

        if not load_scenario(SCENARIO_FILE) or not setup_initial_encounter():
            sys.stdout = original_stdout
            return

        action_keywords = list(OPPOSED_SKILLS.keys()) + COMBAT_SKILLS + ["attack", "climb", "lift", "run", "swim", "dodge", "fly", "ride", "pilot", "operate", "pick", "repair", "craft", "track"]
        action_keywords = sorted(list(set([k.lower() for k in action_keywords])))
        mechanical_summary_keywords = ["attack:", "hit!", "miss!", "roll:", "success", "failure", "vs dn"]

        print(f"\nSCENE START: {scenario_data.get('scenario_name', 'Unnamed Scenario')}\n{game_state['environment_description']}")

        is_combat_mode = False
        turn_summaries = []
        game_state["turn_order"] = game_state["players"] + game_state["enemies"]

        while True:
            if not is_combat_mode and any(e.attitude == ATTITUDE_HOSTILE for e in game_state["players"] + game_state["enemies"]):
                print("\n" + "="*20); print("HOSTILITIES DETECTED! Entering Combat Mode!"); print("="*20)
                is_combat_mode = True; game_state["round_number"] = 1; game_state["current_turn_entity_index"] = 0
                roll_initiative()
                if not game_state["turn_order"]: print("No one is left to fight. Combat ends before it begins."); break
                print(f"\n--- Beginning Combat Round {game_state['round_number']} ---")

            if game_state["current_turn_entity_index"] >= len(game_state["turn_order"]):
                action_summary_for_narrator = next((s for s in reversed(turn_summaries) if any(k in s.lower() for k in mechanical_summary_keywords)), "The characters conversed.")
                print(f"\nNARRATIVE SUMMARY:\n{get_llm_story_response(action_summary_for_narrator)}\n")
                turn_summaries = []; game_state["current_turn_entity_index"] = 0
                if is_combat_mode:
                    game_state["round_number"] += 1; print(f"--- End of Combat Round {game_state['round_number'] - 1} ---")
                    print(f"\n--- Beginning Combat Round {game_state['round_number']} ---"); roll_initiative()
                    if not game_state["turn_order"]: print("Combat concludes as no hostiles remain active."); break

            if not game_state["turn_order"]:
                print("No one is available to take a turn. Ending game.")
                break

            current_entity = game_state["turn_order"][game_state["current_turn_entity_index"]]
            summary = ""
            if current_entity.is_incapacitated():
                summary = f"{current_entity.name} is incapacitated and cannot act."
                print(summary)
            else:
                if current_entity in game_state["players"]:
                    command = input(f"Your action, {current_entity.name}: ")
                    if command.lower() in ["quit", "exit"]: print("Exiting game."); break

                    if any(keyword in command.lower() for keyword in action_keywords):
                        summary = get_llm_action_and_execute(command, current_entity, is_combat_mode)
                    else:
                        cleaned_command = command
                        if ":" in command:
                            parts = command.split(":", 1)
                            if parts[0].strip().lower() == current_entity.name.lower():
                                cleaned_command = parts[1].strip()
                        summary = f'{current_entity.name}: "{cleaned_command.strip()}"'
                else:
                    last_summary = turn_summaries[-1] if turn_summaries else "The scene begins."
                    summary = get_enemy_action(current_entity, is_combat_mode, last_summary)

            if summary:
                if any(key in summary.lower() for key in mechanical_summary_keywords):
                    print("\n-- Mechanical Outcome --\n" + summary + "\n------------------------")
                else:
                    print(summary)
                turn_summaries.append(summary)

            if all(e.is_incapacitated() for e in game_state["enemies"]): print(f"\nVICTORY! All enemies have been defeated!"); break
            if all(p.is_incapacitated() for p in game_state["players"]): print(f"\nGAME OVER! All players are incapacitated!"); break

            game_state["current_turn_entity_index"] += 1

    sys.stdout = original_stdout
    print(f"Game log saved to: {log_filename}")

if __name__ == "__main__":
    main_game_loop()