# actions.py
from d6_rules import roll_d6_check, COMBAT_SKILLS, OPPOSED_SKILLS, roll_d6_dice

def get_equipped_weapon(actor, skill_name, environment):
    """Finds the equipped weapon for a given combat skill."""
    for item_in_inventory in getattr(actor, 'inventory', []):
        if item_in_inventory.get('equipped'):
            item_details = environment.get_item_details(item_in_inventory['item'])
            if item_details and item_details.get('skill', '').lower() == skill_name.lower():
                return item_details
    return None

def cast_spell(actor, spell, target, environment, players, actors):
    """
    Casts a spell at a target, checking if the actor knows the spell and performing
    an opposed roll based on data from spells.yaml.
    """
    if not spell or not target:
        return f"ERROR: Spell '{spell}' or target '{target}' not specified for casting."

    spell_lower = spell.lower()
    target_lower = target.lower()

    # 1. Check if the actor knows the spell
    known_spells = [s.lower() for s in getattr(actor, 'spells', [])]
    if spell_lower not in known_spells:
        return f"{actor.name} does not know the spell '{spell}'."

    # 1a. Get spell details from the environment (loaded from spells.yaml)
    spell_details = environment.get_spell_details(spell_lower)
    if not spell_details:
        return f"Error: The spell '{spell}' is known by {actor.name} but has no definition in the game files."

    # 2. Find the target actor (if applicable)
    target_actor = next((a for a in players + actors if a.name.lower() == target_lower), None)
    
    # 3. Perform the spell check using 'intellect'
    actor_pips = actor.get_attribute_or_skill_pips('intellect')
    actor_roll, _ = roll_d6_check(actor_pips, 0)
    
    # 4. Handle different spells based on their effect from yaml
    effect = spell_details.get('effect')
    
    match effect:
        case "fire":  # For Fireball
            if not target_actor: return f"Cannot find target '{target}' for the spell."
            target_pips = target_actor.get_attribute_or_skill_pips('dodge')
            target_roll, _ = roll_d6_check(target_pips, 0)
            if actor_roll > target_roll:
                base_damage = spell_details.get('value', 0)
                damage = base_damage + (actor_roll - target_roll)
                damage_message = target_actor.take_damage(damage)
                return f"{actor.name} hurls a fireball at {target_actor.name}! It hits! {damage_message}"
            else:
                return f"{actor.name}'s fireball misses {target_actor.name}."

        case "charm" | "stun":  # For Charm and Hold Person
            if not target_actor: return f"Cannot find target '{target}' for the spell."
            target_pips = target_actor.get_attribute_or_skill_pips('willpower')
            target_roll, _ = roll_d6_check(target_pips, 0)
            if actor_roll > target_roll:
                if effect == "charm":
                    return f"{actor.name} successfully charms {target_actor.name}."
                else:  # stun (Hold Person)
                    return f"{target_actor.name} is held in place by {actor.name}'s magic!"
            else:
                if effect == "charm":
                    return f"{target_actor.name} resists {actor.name}'s charm spell."
                else:  # stun (Hold Person)
                    return f"{target_actor.name} breaks free from the magical hold."
        
        case "language":  # For Comprehend Languages
            # This spell affects the caster and doesn't require a target actor.
            return f"{actor.name} casts {spell} and can now understand all spoken and written languages for a time."

        case _:
            return f"The spell '{spell}' with effect '{effect}' is not yet implemented or cannot be targeted in this way."


def execute_skill_check(actor, skill, target, environment, players, actors):
    """
    Performs a general skill check against a target (object, trap, or another actor)
    or a static difficulty. Now uses a match/case for different skills.
    """
    if not skill or not target:
        return f"ERROR: Skill '{skill}' or target '{target}' not specified for skill check."

    skill_lower = skill.lower()
    target_lower = target.lower()

    # Find the target entity (object, door, trap, or actor)
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    target_object = environment.get_object_in_room(actor.location['room_id'], target_lower)
    target_door = next((d for d in environment.doors.values() if d['name'].lower() == target_lower), None)
    target_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    target_actor = next((a for a in players + actors if a.name.lower() == target_lower), None)

    # Use a match/case statement to handle different skills
    match skill_lower:

        case "athletics":
            return
        
        case "melee":
            if not target_actor:
                return f"Cannot find '{target}' to attack."
            if target_actor == actor:
                return f"{actor.name} can't attack themself."

            # Opposed roll logic
            opposing_skills = OPPOSED_SKILLS.get(skill_lower, ['dodge'])
            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            actor_roll, _ = roll_d6_check(actor_pips, 0)

            # Target opposes the roll
            highest_opposition_roll = 0
            for opposing_skill in opposing_skills:
                target_pips = target_actor.get_attribute_or_skill_pips(opposing_skill)
                target_roll, _ = roll_d6_check(target_pips, 0)
                if target_roll > highest_opposition_roll:
                    highest_opposition_roll = target_roll
            
            if actor_roll > highest_opposition_roll:
                # Find equipped weapon and calculate damage
                equipped_weapon = get_equipped_weapon(actor, skill_lower, environment)
                if not equipped_weapon:
                    return f"{actor.name} tries to attack but has no appropriate weapon equipped!"
                
                base_damage = equipped_weapon.get('value', 3) # Use 'value' as damage
                damage_dealt = base_damage + (actor_roll - highest_opposition_roll)
                damage_message = target_actor.take_damage(damage_dealt)
                return f"{actor.name}'s {skill} attack with {equipped_weapon['name']} hits {target_actor.name}! {damage_message}"
            else:
                return f"{actor.name}'s {skill} attack misses {target_actor.name}."
        
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
        
        case "observation":
            return
        
        case "charisma":
            if not target_actor:
                return f"Cannot find '{target}' to use {skill} on."
            
            # Opposed willpower check
            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            target_pips = target_actor.get_attribute_or_skill_pips('willpower')
            
            actor_roll, _ = roll_d6_check(actor_pips, 0)
            target_roll, _ = roll_d6_check(target_pips, 0)

            if actor_roll > target_roll:
                # This would need more complex logic to change an NPC's state (e.g., disposition)
                return f"{actor.name} successfully uses {skill} on {target_actor.name}."
            else:
                return f"{target_actor.name} resists {actor.name}'s attempt at {skill}."
        
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
            # Default case for unhandled skills
            return f"The skill '{skill}' cannot be used in this way or is not yet implemented."
            
    return f"Could not find target '{target}' for skill check."