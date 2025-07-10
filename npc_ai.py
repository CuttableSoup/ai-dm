import random
from game_state import game_state, prompts
from d6_rules import ATTITUDE_HOSTILE
from game_entities import get_zone_distance
from actions import execute_attack, execute_move_zone, pass_turn
from config import NARRATIVE_MODEL, LLM_API_URL
import requests

def get_enemy_action(enemy_actor, is_combat_mode, last_summary):
    """
    Determines an NPC's action based on its personality and the current situation.
    """
    # --- Special logic for mindless traps ---
    if "trap" in enemy_actor.statuses:
        # Mindless traps only act if a player enters their specific zone
        if enemy_actor.is_incapacitated():
            return "" # Suppress output for sprung traps
            
        players_in_zone = [p for p in game_state["players"] if p.current_room == enemy_actor.current_room and p.current_zone == enemy_actor.current_zone and not p.is_incapacitated()]
        
        # Check if any players in the zone are NOT allies of the trap (e.g., they haven't found it yet)
        valid_targets = [p for p in players_in_zone if p.name not in enemy_actor.allies]

        if valid_targets:
            # The trap makes an attack against a random valid target in its zone
            player_to_ambush = random.choice(valid_targets)
            # NOTE: Pass the 'enemy_actor' object directly.
            attack_summary = execute_attack(enemy_actor, target_name=player_to_ambush.name)
            # Fragile traps are destroyed after one attack
            if "fragile" in enemy_actor.statuses:
                enemy_actor.current_hitpoints = 0 
                attack_summary += f"\n  -> The {enemy_actor.name} has been sprung!"
            return attack_summary
        # Return an empty string to suppress "sits silently" message
        return ""

    # --- Standard combat logic for hostile npcs ---
    if is_combat_mode and enemy_actor.attitude == ATTITUDE_HOSTILE:
        # Enemy AI is now zone-aware
        players_in_room = [p for p in game_state["players"] if p.current_room == enemy_actor.current_room and not p.is_incapacitated()]
        if not players_in_room:
             return pass_turn(enemy_actor, reason="All targets have fled or are defeated.")
        
        weapon = enemy_actor.get_weapon_details()
        weapon_range_value = weapon.get("range", 0)

        # Convert descriptive range to a numerical value for comparison
        weapon_range = 0
        if isinstance(weapon_range_value, str):
            if weapon_range_value.lower() == "melee":
                weapon_range = 0
            else:
                try:
                    weapon_range = int(weapon_range_value)
                except (ValueError, TypeError):
                    weapon_range = 0
        elif isinstance(weapon_range_value, int):
            weapon_range = weapon_range_value
        
        # Find all players that are within the weapon's range
        targets_in_range = []
        for p in players_in_room:
            dist = get_zone_distance(enemy_actor.current_zone, p.current_zone, enemy_actor.current_room)
            if dist != -1 and dist <= weapon_range:
                targets_in_range.append(p)
        
        # If there's a target in range, attack it.
        if targets_in_range:
            # NOTE: Pass the 'enemy_actor' object directly.
            return execute_attack(enemy_actor, target_name=random.choice(targets_in_range).name)
        else:
            # If no target is in range, try to move closer to the nearest player.
            nearest_player = min(players_in_room, key=lambda p: get_zone_distance(enemy_actor.current_zone, p.current_zone, enemy_actor.current_room))
            current_dist = get_zone_distance(enemy_actor.current_zone, nearest_player.current_zone, enemy_actor.current_room)
            adj_zones = game_state["environment"].get_room(enemy_actor.current_room).get("zones", {}).get(str(enemy_actor.current_zone), {}).get("adjacent_zones", [])
            
            # Simple AI: move to the first adjacent zone that gets it closer.
            for zone in adj_zones:
                if get_zone_distance(zone, nearest_player.current_zone, enemy_actor.current_room) < current_dist:
                    # NOTE: Pass the 'enemy_actor' object directly.
                    return execute_move_zone(enemy_actor, target_zone=zone)
            # If no move gets it closer, wait.
            return pass_turn(enemy_actor, reason="is unable to get closer.")

    # --- Non-combat or non-hostile dialogue ---
    return get_npc_dialogue(enemy_actor, last_summary)

def get_npc_dialogue(actor, context):
    """
    Generates dialogue for an NPC using the narrative AI model.
    """
    actor_description = actor.get_full_description()
    prompt_template = prompts["npc_dialogue"]
    prompt = prompt_template.format(actor_description=actor_description, context=context)
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        dialogue = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return f'{actor.name}: "{dialogue}"' if dialogue else f"{actor.name} remains silent."
    except Exception as e:
        return f"LLM Error (Narration): Could not get dialogue. {e}"
