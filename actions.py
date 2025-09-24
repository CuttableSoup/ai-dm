from d6_rules import roll_d6_check, COMBAT_SKILLS, OPPOSED_SKILLS, roll_d6_dice
from classes import GameState, InventoryItem

def get_equipped_weapon(actor, skill_name, game_state: GameState):
    """Finds the equipped weapon for a given combat skill."""
    for item_in_inventory in getattr(actor, 'inventory', []):
        # FIX: Use attribute access (item.equipped) instead of dictionary access (item.get('equipped'))
        if item_in_inventory.equipped:
            # FIX: Use attribute access (item.item) instead of dictionary access (item['item'])
            item_details = game_state.environment.get_item_details(item_in_inventory.item)
            if item_details and item_details.get('skill', '').lower() == skill_name.lower():
                return item_details
    return None

def execute_skill_check(actor, skill: str, target: str, game_state: GameState):
    """
    Performs a general skill check against a target.
    This function now uses the game_state object to access the environment and actors.
    """
    if not skill or not target:
        return f"ERROR: Skill '{skill}' or target '{target}' not specified for skill check."

    skill_lower = skill.lower()
    target_lower = target.lower()

    target_object = game_state.environment.get_object_in_room(actor.location['room_id'], target_lower)
    target_door = next((d for d in game_state.environment.doors.values() if d['name'].lower() == target_lower), None)
    target_trap = game_state.environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    target_actor = game_state.find_actor_by_name(target_lower)

    match skill_lower:
        case "melee":
            target_entity = target_actor or target_object
            if not target_entity:
                return f"Cannot find '{target}' to attack."
            if target_entity == actor:
                return f"{actor.name} can't attack themself."

            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            actor_roll, _ = roll_d6_check(actor_pips, 0)

            highest_opposition_roll = 0
            if target_actor:
                opposing_skills = OPPOSED_SKILLS.get(skill_lower, ['dodge'])
                for opposing_skill in opposing_skills:
                    target_pips = target_actor.get_attribute_or_skill_pips(opposing_skill)
                    target_roll, _ = roll_d6_check(target_pips, 0)
                    if target_roll > highest_opposition_roll:
                        highest_opposition_roll = target_roll
            
            if actor_roll > highest_opposition_roll:
                equipped_weapon = get_equipped_weapon(actor, skill_lower, game_state)
                if not equipped_weapon:
                    return f"{actor.name} tries to attack but has no appropriate weapon equipped!"
                
                base_damage = equipped_weapon.get('value', 3)
                damage_dealt = base_damage + (actor_roll - highest_opposition_roll)
                target_dr = getattr(target_entity, 'dr', 0)
                final_damage = max(0, damage_dealt - target_dr)
                
                damage_message = ""
                if hasattr(target_entity, 'hp'):
                    current_hp = getattr(target_entity, 'hp')
                    new_hp = current_hp - final_damage
                    setattr(target_entity, 'hp', new_hp) 
                    
                    if new_hp <= 0:
                        damage_message = f"{target_entity.name} is destroyed!"
                    else:
                        damage_message = f"{target_entity.name} now has {new_hp} HP."
                else:
                    damage_message = f"{target_entity.name} seems unaffected."

                dr_message = f" (reduced by {target_dr} from armor)" if target_dr > 0 else ""
                return (f"{actor.name}'s {skill} attack with {equipped_weapon['name']} hits {target_entity.name}! "
                        f"It deals {final_damage} damage{dr_message}. {damage_message}")
            else:
                return f"{actor.name}'s {skill} attack misses {target_entity.name}."
        
        case "observation":
            if target_object:
                dc = getattr(target_object, 'observation_dc', 10)
                actor_pips = actor.get_attribute_or_skill_pips('observation')
                _, success = roll_d6_check(actor_pips, dc)
                if success:
                    return f"{actor.name} observes {target_object.name} closely: {target_object.description}"
                else:
                    return f"{actor.name} doesn't notice anything unusual about {target_object.name}."
            elif target_actor:
                return f"{actor.name} is observing {target_actor.name}."
            else:
                return f"{actor.name} observes the area, but doesn't focus on anything in particular."
        
        case "charisma":
            if not target_actor:
                return f"Cannot find '{target}' to use {skill} on."
            
            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            target_pips = target_actor.get_attribute_or_skill_pips('willpower')
            actor_roll, _ = roll_d6_check(actor_pips, 0)
            target_roll, _ = roll_d6_check(target_pips, 0)

            if actor_roll > target_roll:
                return f"{actor.name} successfully uses {skill} on {target_actor.name}."
            else:
                return f"{target_actor.name} resists {actor.name}'s attempt at {skill}."

        case "athletics":
            return
        case "throwing":
            return
        case "fortitude":
            return
        case "strength":
            return
        case "acrobatics":
            return
        case "fly":
            return
        case "trickery":
            return
        case "stealth":
            return
        case "dodge":
            return
        case "missiles":
            return
        case "appraise":
            return
        case "linguistics":
            return
        case "spellcraft":
            return
        case "navigation":
            return
        case "technology":
            return
        case "law":
            return
        case "business":
            return
        case "cultures":
            return
        case "medicine":
            return
        case "survival":
            return
        case "willpower":
            return
        case "miracles":
            return
        case "artistry":
            return
        case "forgery":
            return
        case "gambling":
            return
        case "streetwise":
            return
        case "deception":
            return
        case "disguise":
            return
        case "husbandry":
            return
        case "intimidation":
            return
        case "psionics":
            return

        case _:
            return f"The skill '{skill}' cannot be used in this way or is not yet implemented."
            
    return f"Could not find target '{target}' for skill check."

def manage_item(actor, action: str, item_name: str, game_state: GameState, quantity: int = 1, target_name: str = None):
    """Manages item interactions like using, moving, creating, destroying, equipping, and unequipping."""
    action_lower = action.lower()
    item_name_lower = item_name.lower()
    target = None
    if target_name:
        target = game_state.find_actor_by_name(target_name)

    match action_lower:
        case 'equip':
            item_to_equip = None
            for item in getattr(actor, 'inventory', []):
                # FIX: Use attribute access
                if item.item.lower() == item_name_lower:
                    item_to_equip = item
                    break
            if not item_to_equip:
                return f"{actor.name} does not have a {item_name} to equip."
            item_details = game_state.environment.get_item_details(item_name)
            if not item_details or 'type' not in item_details:
                return f"Cannot determine the type of {item_name} to equip it correctly."
            item_type = item_details['type']
            # Unequip any other item of the same type
            for item in getattr(actor, 'inventory', []):
                # FIX: Use attribute access
                if item.equipped:
                    other_item_details = game_state.environment.get_item_details(item.item)
                    if other_item_details and other_item_details.get('type') == item_type:
                        item.equipped = False
            # Equip the new item
            item_to_equip.equipped = True
            return f"{actor.name} equips the {item_name}."

        case 'unequip':
            for item in getattr(actor, 'inventory', []):
                # FIX: Use attribute access
                if item.item.lower() == item_name_lower and item.equipped:
                    item.equipped = False
                    return f"{actor.name} unequips the {item_name}."
            return f"{actor.name} does not have a {item_name} equipped."

        case 'use':
            return f"{actor.name} uses the {item_name}. (Functionality to be expanded)."

        case 'move':
            if not target_name:
                return f"A target is required to move an item to."
            if not target:
                return f"Cannot find target '{target_name}' to move the item to."
            if target == actor:
                return f"{actor.name} can't move an item to themself."
            item_to_move = None
            inventory = getattr(actor, 'inventory', [])
            for i, item in enumerate(inventory):
                 # FIX: Use attribute access
                if item.item.lower() == item_name_lower:
                    item_to_move = inventory.pop(i)
                    break
            if not item_to_move:
                return f"{actor.name} does not have a {item_name} to move."
            if not hasattr(target, 'inventory'):
                target.inventory = []
            target.inventory.append(item_to_move)
            return f"{actor.name} gives a {item_name} to {target.name}."

        case 'create':
            item_details = game_state.environment.get_item_details(item_name)
            if not item_details:
                return f"Cannot create '{item_name}' as it is not a known item."
            if not hasattr(actor, 'inventory'):
                actor.inventory = []
            for _ in range(quantity):
                # FIX: Append an actual InventoryItem object, not a dictionary
                new_item = InventoryItem(item=item_details['name'], equipped=False, quantity=1)
                actor.inventory.append(new_item)
            return f"Created {quantity} {item_name} and added it to {actor.name}'s inventory."

        case 'destroy':
            inventory = getattr(actor, 'inventory', [])
            items_removed = 0
            # Iterate backwards when removing items from a list
            for i in range(len(inventory) - 1, -1, -1):
                if items_removed >= quantity:
                    break
                # FIX: Use attribute access
                if inventory[i].item.lower() == item_name_lower:
                    inventory.pop(i)
                    items_removed += 1
            if items_removed > 0:
                return f"Destroyed {items_removed} {item_name} from {actor.name}'s inventory."
            else:
                return f"{actor.name} does not have any {item_name} to destroy."
        case _:
            return f"Unknown item action: '{action}'."

def manage_party_member(actor, action: str, member_name: str, game_state: GameState):
    """Adds or removes a member from the party using the GameState."""
    action_lower = action.lower()
    member_to_manage = game_state.find_actor_by_name(member_name)
    if not member_to_manage:
        return f"Cannot find a character named '{member_name}'."
    
    party = game_state.party

    match action_lower:
        case 'add':
            if member_to_manage in party.members:
                return f"{member_name} is already in the party."
            party.add_member(member_to_manage)
            return
        case 'remove':
            if member_to_manage not in party.members:
                return f"{member_name} is not in the party."
            party.remove_member(member_to_manage)
            return f"{member_name} has left the party."
        case _:
            return f"Unknown party action: '{action}'."

def move_party(actor, destination_zone: str, game_state: GameState):
    """Moves the entire party to a new zone using the GameState."""
    environment = game_state.environment
    party = game_state.party
    
    current_room, current_zone = environment.get_current_room_data(actor.location)
    if not current_zone:
        return f"Cannot determine the current location of the party."

    valid_exit = None
    for exit_data in current_zone.get('exits', []):
        if exit_data.get('zone_ref', '').lower() == destination_zone.lower():
            valid_exit = exit_data
            break
    if not valid_exit:
        return f"Cannot move to '{destination_zone}'. It is not a valid exit from the current location."

    door_ref = valid_exit.get('door_ref')
    if door_ref:
        door = environment.get_door_by_id(door_ref)
        if door and door.get('locked', False):
            return f"The way is blocked by the {door.get('name', 'door')}, which is locked."

    new_location = {'room_id': actor.location['room_id'], 'zone': destination_zone}
    for member in party.members:
        member.location = new_location

    new_room, new_zone = environment.get_current_room_data(new_location)
    description = new_zone.get('description', 'You arrive in the new area.')
    return f"The party moves to the {destination_zone}. {description}"