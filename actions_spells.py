import random
from classes import ActiveEffect, GameState

def apply_armor(game_state: GameState, target_name: str, dodge_bonus: int, duration_text: str):
    """
    Applies a magical armor effect to a target, using the GameState.
    """
    target = game_state.find_actor_by_name(target_name)
    if not target:
        return f"Error: Target '{target_name}' not found."
    
    effect = ActiveEffect(name="Armor Spell", duration_text=duration_text, target=target)
    game_state.party.active_effects.append(effect)
    
    if not hasattr(target, 'dodge'):
        target.dodge = 0
    target.dodge += dodge_bonus

    return f"{target.name} is surrounded by a field of force, increasing their dodge by {dodge_bonus}. Effect: {effect}"

def apply_charm(game_state: GameState, target_name: str, duration_text: str):
    """
    Applies a charm effect to a target, using the GameState.
    """
    target = game_state.find_actor_by_name(target_name)
    if not target:
        return f"Error: Target '{target_name}' not found."

    effect = ActiveEffect(name="Charmed", duration_text=duration_text, target=target)
    game_state.party.active_effects.append(effect)
    
    return f"{target.name} is now charmed. They view the caster as a friend. Effect: {effect}"

def apply_strength_buff(game_state: GameState, target_name: str, duration_text: str):
    """
    Applies a strength buff to a target, using the GameState.
    """
    target = game_state.find_actor_by_name(target_name)
    if not target:
        return f"Error: Target '{target_name}' not found."

    pips_to_add = random.randint(1, 6)
    
    if 'strength' in target.attributes:
        target.attributes['strength'] += pips_to_add
    else:
        return f"Error: {target.name} does not have a 'strength' attribute."

    effect = ActiveEffect(name="Strength Spell", duration_text=duration_text, target=target)
    game_state.party.active_effects.append(effect)
    
    return f"{target.name}'s muscles bulge with magical power, increasing their Strength by {pips_to_add} pips. Effect: {effect}"