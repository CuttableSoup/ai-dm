import requests
import json
import textwrap
import copy
from actions_spells import apply_armor, apply_charm, apply_strength_buff, deal_damage

# A dictionary to map function names to the actual functions
SPELL_FUNCTION_MAP = {
    "apply_armor": apply_armor,
    "apply_charm": apply_charm,
    "apply_strength_buff": apply_strength_buff,
    "deal_damage": deal_damage,
}

# The list of tools available to the spell-casting LLM
SPELL_TOOLS = [
    {   "type": "function", "function": {
            "name": "apply_armor", "description": "Creates a magical force field on a target, increasing their defense.",
            "parameters": {"type": "object", "properties": {
                "target_name": {"type": "string", "description": "The character receiving the armor."},
                "dodge_bonus": {"type": "integer", "description": "The amount to increase the target's dodge."},
                "duration_text": {"type": "string", "description": "The duration of the spell (e.g., 'Until destroyed')."}
                },
                "required": ["target_name", "dodge_bonus", "duration_text"]
            }
        }
    },
    {   "type": "function", "function": {
            "name": "apply_charm", "description": "Makes a humanoid creature view the caster as a trusted friend.",
            "parameters": {"type": "object", "properties": {
                "target_name": {"type": "string", "description": "The character being charmed."},
                "duration_text": {"type": "string", "description": "The duration of the spell (e.g., 'special')."}
                },
                "required": ["target_name", "duration_text"]
            }
        }
    },
    {   "type": "function", "function": {
            "name": "apply_strength_buff", "description": "Temporarily increases a character's Strength score.",
            "parameters": {"type": "object", "properties": {
                "target_name": {"type": "string", "description": "The character receiving the strength buff."},
                "duration_text": {"type": "string", "description": "The duration of the spell (e.g., '1 hour')."}
                },
                "required": ["target_name", "duration_text"]
            }
        }
    },
    {   "type": "function", "function": {
            "name": "deal_damage", "description": "Deals damage of a specific type to a target.",
            "parameters": {"type": "object", "properties": {
                "target_name": {"type": "string", "description": "The character being damaged."},
                "damage_dice_roll": {"type": "integer", "description": "The number of d6 to roll for damage."},
                "damage_type": {"type": "string", "description": "The type of damage (e.g., 'fire', 'force')."}
                },
                "required": ["target_name", "damage_dice_roll", "damage_type"]
            }
        }
    }
]

def resolve_spell_effect(caster, spell, target, party, players, actors, llm_config, debug=False):
    """
    Makes a focused LLM call to determine the mechanical effect of a spell.
    """
    prompt_template = textwrap.dedent("""
    You are a strict Rules Engine for a tabletop RPG. Your task is to read the description of a spell that has been successfully cast and call the SINGLE function that best represents its mechanical effect.

    **CONTEXT**
    - Caster: {caster_name}
    - Target: {target_name}
    - Spell Name: {spell_name}
    - **Spell Description**: "{spell_description}"

    **INSTRUCTIONS**
    1.  Read the **Spell Description** carefully.
    2.  Based ONLY on the description, choose the ONE function from the available tools that implements the spell's effect.
    3.  Extract the correct parameters for the function from the spell description. For damage, use the caster's skill roll to determine the number of dice.
    4.  You MUST call a function. Do not respond with text.
    """).strip()

    # Calculate damage dice if applicable (half of skill pips)
    skill_pips = caster.get_attribute_or_skill_pips(spell['skill'])
    damage_dice = skill_pips // 2

    prompt = prompt_template.format(
        caster_name=caster.name,
        target_name=target.name,
        spell_name=spell['name'],
        spell_description=spell['summary'].replace("{skill}", str(skill_pips))
    )

    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": SPELL_TOOLS,
        "tool_choice": "auto"
    }
    
    if debug:
        print("\n--- LLM Spell Effect Payload ---")
        print(json.dumps(payload, indent=2))
        print("--------------------------------\n")

    try:
        response = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        
        if debug:
            print(f"\n--- LLM Spell Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------------\n")
            
        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return "Error: The AI rules engine failed to select a spell effect function."
            
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        # Add damage dice to arguments if the function is 'deal_damage'
        if function_name == 'deal_damage':
            arguments['damage_dice_roll'] = damage_dice

        # Execute the chosen spell function
        if function_name in SPELL_FUNCTION_MAP:
            # We need to pass the game state to the function
            return SPELL_FUNCTION_MAP[function_name](party=party, players=players, actors=actors, **arguments)
        else:
            return f"Error: AI chose an unknown spell function '{function_name}'."

    except Exception as e:
        return f"Error resolving spell effect with AI: {e}"