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
    target_object = environment.get_object_in_room(actor.location['room_id'], target_lower)
    target_door = next((d for d in environment.doors.values() if d['name'].lower() == target_lower), None)
    target_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    target_actor = next((a for a in players + actors if a.name.lower() == target_lower), None)

    # Use a match/case statement to handle different skills
    match skill_lower:

        case "melee":
            if not target_actor:
                return f"Cannot find '{target}' to attack."
            if target_actor == actor:
                return f"{actor.name} can't attack themself."

            # Opposed roll logic
            opposing_skills = OPPOSED_SKILLS.get(skill_lower, ['dodge'])
            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            actor_roll, _ = roll_d6_check(actor_pips, 0) # We only need the roll total here

            # Target opposes the roll
            highest_opposition_roll = 0
            for opposing_skill in opposing_skills:
                target_pips = target_actor.get_attribute_or_skill_pips(opposing_skill)
                target_roll, _ = roll_d6_check(target_pips, 0) # And here
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
        
        case "observation":
            if target_object:
                # Perform an observation check against the object's observation_dc
                dc = getattr(target_object, 'observation_dc', 10) # Default DC is 10
                actor_pips = actor.get_attribute_or_skill_pips('observation')
                # We can now use the 'success' boolean directly from the check
                _, success = roll_d6_check(actor_pips, dc)

                if success:
                    # Access attributes directly from the Object instance
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
            
            # Opposed willpower check
            actor_pips = actor.get_attribute_or_skill_pips(skill_lower)
            target_pips = target_actor.get_attribute_or_skill_pips('willpower')
            
            actor_roll, _ = roll_d6_check(actor_pips, 0) # Only need the roll total
            target_roll, _ = roll_d6_check(target_pips, 0) # And here

            if actor_roll > target_roll:
                # This would need more complex logic to change an NPC's state (e.g., disposition)
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
            # Default case for unhandled skills
            return f"The skill '{skill}' cannot be used in this way or is not yet implemented."
            
    return f"Could not find target '{target}' for skill check."