import random
from game_state import game_state
from d6_rules import *
from game_entities import get_zone_distance

def execute_look(actor, **kwargs):
    """Provides a detailed description of the character's current surroundings, including zones."""
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
        
        # Only show characters who are not mindless (like traps) unless they've been discovered
        chars_in_zone = [e.name for e in all_chars if e.current_room == actor.current_room and e.current_zone == int(zone_num) and ("discovered" in e.statuses or "mindless" not in e.statuses)]
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

def execute_check_self(actor, **kwargs):
    """Provides a summary of the character's own status, equipment, and inventory."""
    if not actor: return f"Could not find player to check."
    
    response = f"--- Status for {actor.name} ---"
    response += f"Condition: {actor.get_hitpoint_status()} ({actor.current_hitpoints}/{actor.max_hitpoints} HP)"
    response += f"Location: Room '{actor.current_room}', Zone {actor.current_zone}\n"
    response += f"Attributes: {actor.get_attribute_descriptors_string()}\n"
    
    # List equipped items, now showing range
    equipped_items = [f"{item['name']} (Range: {item.get('range', 'N/A')})" for item in actor.equipment]
    response += "Equipped: " + (", ".join(equipped_items) if equipped_items else "Nothing") + "\n"
    # List inventory items
    inventory_items = [f"{item['name']}" for item in actor.inventory]
    response += "Inventory: " + (", ".join(inventory_items) if inventory_items else "Empty") + "\n"
    return response

def execute_move(actor, exit_name):
    """Moves the character through a specified exit to another room."""
    if not actor: return f"Action failed: Could not find actor to move."

    room = game_state["environment"].get_room(actor.current_room)
    if not room: return f"{actor.name} is in an unknown location and cannot move."

    target_exit = next((ext for ext in room.get("exits", []) if ext["name"].lower() == exit_name.lower()), None)
    if not target_exit: return f"{actor.name} cannot find an exit named '{exit_name}'."
    
    # Check if character is in the correct zone to use the exit
    if actor.current_zone != target_exit.get("zone"):
        return f"You must be in Zone {target_exit.get('zone')} to use the {exit_name}."

    if "action" in target_exit:
        return f"{actor.name} must perform an action to use the {exit_exit['action']['skill']}."

    destination_key = target_exit.get("to_room")
    destination_room = game_state["environment"].get_room(destination_key)
    if not destination_room: return f"The exit '{exit_name}' leads nowhere."
    
    # Update actor's location to the new room, defaulting to Zone 1
    actor.current_room = destination_key
    actor.current_zone = 1
    return f"{actor.name} moves through the {exit_name} into the {destination_room.get('name', 'next room')}."

def execute_move_zone(actor, target_zone):
    """Moves the character to an ADJACENT zone and performs a passive search for traps."""
    if not actor: return f"Action failed: Could not find actor to move."

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
    move_summary = f"{actor.name} moves to Zone {target_zone}."

    # --- NEW: Passive search check for traps upon entering the new zone. ---
    all_entities = game_state["players"] + game_state["npcs"]
    hidden_entities = [e for e in all_entities if e.id != actor.id and e.current_room == actor.current_room and e.current_zone == actor.current_zone and "discovered" not in e.statuses]

    for entity in hidden_entities:
        # Check if the hidden entity is a trap
        if "trap" in entity.statuses:
            search_pips = actor.get_attribute_or_skill_pips("search")
            hide_pips = entity.get_attribute_or_skill_pips("hide")
            hide_roll_total, _ = roll_d6_dice(hide_pips)
            success_level, _, search_roll_str = roll_d6_check(actor, search_pips, hide_roll_total)

            if success_level > 0:
                # Player spots the trap! Append to the summary.
                move_summary += f"\n  -> As {actor.name} enters, they spot {entity.name}! ({search_roll_str} vs Hide DN {hide_roll_total})"
                # Add actor to allies so the trap won't spring on them.
                if entity.allies == "none":
                    entity.allies = actor.name
                else:
                    entity.allies += f", {actor.name}"
                entity.statuses.append("discovered")

    return move_summary

def execute_attack(actor, target_name):
    """Executes an attack, checking the weapon's range against the target's distance."""
    all_entities = game_state["players"] + game_state["npcs"]
    target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
    
    if not actor: return f"Action failed: Could not find attacker."
    if not target_entity: return f"Action failed: Could not find target '{target_name}'."
    if actor.current_room != target_entity.current_room: return f"Action failed: {target_name} is not in the same room."

    # Prevent attacking allies
    if actor.name in target_entity.allies or target_entity.name in actor.allies:
        return f"Action failed: {actor.name} cannot attack an ally, {target_name}."

    # Get the actor's equipped weapon (or unarmed) and its range
    weapon = actor.get_weapon_details()
    weapon_range_value = weapon.get("range", 0)

    # Convert descriptive range to a numerical value for comparison
    weapon_range = 0
    if isinstance(weapon_range_value, str):
        if weapon_range_value.lower() == "melee":
            weapon_range = 0
        else:
            try:
                # Try to convert other string values to a number
                weapon_range = int(weapon_range_value)
            except (ValueError, TypeError):
                weapon_range = 0 # Default to melee if conversion fails
    elif isinstance(weapon_range_value, int):
        weapon_range = weapon_range_value

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

def execute_skill_check(actor, skill_name=None, target_name=None, object_name=None):
    """Performs a general skill check against a target, an object, or a static difficulty."""
    all_entities = game_state["players"] + game_state["npcs"]
    if not actor: return f"Action failed: Could not find actor for skill check."
    
    actor_room_data = game_state["environment"].get_room(actor.current_room)

    # Logic for a general search of the current zone to find hidden entities
    if skill_name and skill_name.lower() == 'search' and not target_name and not object_name:
        outcome_summary = ""
        found_something = False
        # Find entities in the same zone that haven't been discovered yet
        hidden_entities = [e for e in all_entities if e.id != actor.id and e.current_room == actor.current_room and e.current_zone == actor.current_zone and "discovered" not in e.statuses]

        for entity in hidden_entities:
            hide_pips = entity.get_attribute_or_skill_pips("hide")
            # If the entity has a hide skill, it's potentially hidden
            if hide_pips > 0:
                search_pips = actor.get_attribute_or_skill_pips("search")
                # Opposed Roll: Search vs. Hide
                hide_roll_total, _ = roll_d6_dice(hide_pips)
                success_level, _, search_roll_str = roll_d6_check(actor, search_pips, hide_roll_total)

                if success_level > 0:
                    found_something = True
                    outcome_summary += f"{actor.name} discovers {entity.name}! ({search_roll_str} vs Hide DN {hide_roll_total})\n"
                    # Add the actor to the entity's allies so it won't attack them
                    if entity.allies == "none":
                        entity.allies = actor.name
                    else:
                        entity.allies += f", {actor.name}"
                    # Mark as discovered to prevent it from being found again
                    entity.statuses.append("discovered")

        if not found_something:
            return f"{actor.name} searches the area but finds nothing unusual."
        else:
            return outcome_summary.strip()
            
    # Logic for interacting with an object or exit
    if object_name:
        target_object = next((obj for obj in actor_room_data.get("objects", []) if obj["name"].lower() == object_name.lower()), None)
        target_exit = next((ext for ext in actor_room_data.get("exits", []) if ext["name"].lower() == object_name.lower()), None)
        target_interactive = target_object or target_exit
        
        if not target_interactive:
            return f"{actor.name} can't find an object or exit named '{object_name}' to interact with."
        
        # Check if actor is in the right zone to interact
        if 'zone' in target_interactive and actor.current_zone != target_interactive['zone']:
             return f"You must move to Zone {target_interactive['zone']} to interact with the {object_name}."

        action_data = target_interactive.get("action")
        # Handle searching non-interactive objects gracefully
        if not action_data:
            if skill_name and skill_name.lower() == 'search':
                return f"{actor.name} searches the {object_name}, but finds nothing of interest."
            return f"'{object_name}' is not interactive in that way."

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

    # Logic for an opposed skill check against another character
    if target_name:
        target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
        if not target_entity: return f"Action failed: Could not find target '{target_name}'."
        # Opposed checks require being in the same zone
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

    # Logic for a general skill check against a static difficulty
    if not skill_name:
        return "Action failed: You must specify a skill to use."
    outcome_summary = f"{actor.name} attempts to use their {skill_name} skill."
    final_difficulty = 10 # Default difficulty
    outcome_summary += f" against a static difficulty of {final_difficulty}."
    skill_pips = actor.get_attribute_or_skill_pips(skill_name)
    success_level, _, details_str = roll_d6_check(actor, skill_pips, final_difficulty)
    outcome_summary += f"\n  {actor.name}'s roll: {details_str}"
    return outcome_summary

def execute_take_item(actor, source_name, item_name):
    """Takes an item from an object or an incapacitated character."""
    all_entities = game_state["players"] + game_state["npcs"]
    if not actor: return f"Action failed: Could not find actor to take item."

    actor_room_data = game_state["environment"].get_room(actor.current_room)
    
    # --- Case 1: Taking from an object in the room ---
    source_object = next((obj for obj in actor_room_data.get("objects", []) if obj["name"].lower() == source_name.lower()), None)
    if source_object:
        # Check if actor is in the same zone as the object
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

def execute_drop_item(actor, item_name):
    """Removes an item from a character's inventory and places it in a pile on the floor in their current zone."""
    if not actor: return f"Action failed: Could not find actor to drop item."

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

def execute_equip_item(actor, item_name):
    """Moves an item from inventory to equipment, checking for occupied location slots."""
    if not actor: return f"Action failed: Could not find actor to equip item."

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

def execute_unequip_item(actor, item_name):
    """Moves an item from equipment back to inventory."""
    if not actor: return f"Action failed: Could not find actor to unequip item."

    item_to_unequip = next((item for item in actor.equipment if item['name'].lower() == item_name.lower()), None)
    if not item_to_unequip:
        return f"{actor.name} does not have a '{item_name}' equipped."

    actor.equipment.remove(item_to_unequip)
    actor.inventory.append(item_to_unequip)
    return f"{actor.name} unequips the {item_to_unequip['name']}."

def pass_turn(actor, reason="", **kwargs):
    """Allows a character to wait, speak, or do nothing for their turn."""
    if not actor: return "A nameless entity passes its turn."
    cleaned_reason = reason.strip().strip('"')
    return f'{actor.name}: "{cleaned_reason}"' if cleaned_reason else f"{actor.name} waits."

def execute_cast_spell(actor, spell_name, target_name=None):
    """Casts a spell, checking for spell availability and target validity."""
    if not actor: return f"Action failed: Could not find actor to cast spell."

    # Check if the actor knows the spell
    spell_to_cast = next((spell for spell in actor.spells if spell.get('name', '').lower() == spell_name.lower()), None)
    if not spell_to_cast:
        return f"{actor.name} does not know the spell '{spell_name}'."

    # Basic spell information
    spell_type = spell_to_cast.get("type", "generic")
    spell_range = spell_to_cast.get("range", 0)
    spell_effect = spell_to_cast.get("effect", "No effect described.")

    outcome_summary = f"{actor.name} begins to cast '{spell_name}'..."

    # Target validation
    target_entity = None
    if target_name:
        all_entities = game_state["players"] + game_state["npcs"]
        target_entity = next((e for e in all_entities if e.name.lower() == target_name.lower()), None)
        if not target_entity:
            return f"Action failed: Could not find target '{target_name}'."
        
        # Range check
        distance = get_zone_distance(actor.current_zone, target_entity.current_zone, actor.current_room)
        if distance > spell_range:
            return f"Action failed: {target_name} is out of range for the spell '{spell_name}'."

    # Placeholder for spell logic
    outcome_summary += f"\n  -> The spell fizzles with no effect. (Spellcasting not yet implemented)."

    return outcome_summary
