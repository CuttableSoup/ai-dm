import random
from classes import ActiveEffect

def find_actor_by_name(name, players, actors):
    """Utility function to find any actor (player or NPC) by name."""
    name_lower = name.lower()
    for p in players:
        if p.name.lower() == name_lower:
            return p
    for a in actors:
        if a.name.lower() == name_lower:
            return a
    return None

def apply_armor(party, players, actors, target_name, dodge_bonus, duration_text):
    """
    Applies a magical armor effect to a target, increasing their dodge.
    This also creates an ActiveEffect to track the spell's duration.
    """
    target = find_actor_by_name(target_name, players, actors)
    if not target:
        return f"Error: Target '{target_name}' not found."
    
    effect = ActiveEffect(name="Armor Spell", duration_text=duration_text, target=target)
    party.active_effects.append(effect)
    
    # We can assume a 'dodge' attribute exists or add it. Let's add it if it doesn't.
    if not hasattr(target, 'dodge'):
        target.dodge = 0
    target.dodge += dodge_bonus

    return f"{target.name} is surrounded by a field of force, increasing their dodge by {dodge_bonus}. Effect: {effect}"

def apply_charm(party, players, actors, target_name, duration_text):
    """
    Applies a charm effect to a target, changing their attitude towards the caster.
    """
    target = find_actor_by_name(target_name, players, actors)
    if not target:
        return f"Error: Target '{target_name}' not found."

    effect = ActiveEffect(name="Charmed", duration_text=duration_text, target=target)
    party.active_effects.append(effect)
    
    # This would change the NPC's 'attitude' value in a more complex system.
    # For now, the effect is tracked.
    return f"{target.name} is now charmed. They view the caster as a friend. Effect: {effect}"

def apply_strength_buff(party, players, actors, target_name, duration_text):
    """
    Applies a strength buff to a target, increasing their Strength pips.
    """
    target = find_actor_by_name(target_name, players, actors)
    if not target:
        return f"Error: Target '{target_name}' not found."

    pips_to_add = random.randint(1, 6)
    
    # Assuming Strength is in the 'attributes' dictionary
    if 'strength' in target.attributes:
        target.attributes['strength'] += pips_to_add
    else:
        return f"Error: {target.name} does not have a 'strength' attribute."

    effect = ActiveEffect(name="Strength Spell", duration_text=duration_text, target=target)
    party.active_effects.append(effect)
    
    return f"{target.name}'s muscles bulge with magical power, increasing their Strength by {pips_to_add} pips. Effect: {effect}"

def deal_damage(players, actors, target_name, damage_dice_roll, damage_type):
    """
    Deals a specified amount of damage of a certain type to a target.
    """
    target = find_actor_by_name(target_name, players, actors)
    if not target:
        return f"Error: Target '{target_name}' not found."

    total_damage = sum(random.randint(1, 6) for _ in range(damage_dice_roll))
    
    result = target.take_damage(total_damage)
    return f"A blast of {damage_type} hits {target.name}! {result}"