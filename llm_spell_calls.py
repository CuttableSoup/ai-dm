import requests
import json
import textwrap
from actions_spells import apply_armor, apply_charm, apply_strength_buff
from classes import GameState

SPELL_FUNCTION_MAP = {
    "apply_armor": apply_armor,
    "apply_charm": apply_charm,
    "apply_strength_buff": apply_strength_buff
}

SPELL_TOOLS = [
]

def resolve_spell_effect(caster, spell, target, game_state: GameState, llm_config: dict):
    """
    Makes a focused LLM call to determine the mechanical effect of a spell.
    Now passes the GameState object to the mechanical functions.
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
    3.  Extract the correct parameters for the function from the spell description.
    4.  You MUST call a function. Do not respond with text.
    """).strip()

    prompt = prompt_template.format(
        caster_name=caster.name,
        target_name=target.name,
        spell_name=spell['name'],
        spell_description=spell.get('summary', 'No summary available.')
    )

    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": SPELL_TOOLS,
        "tool_choice": "auto"
    }
    

    try:
        response = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        
            
        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return "Error: The AI rules engine failed to select a spell effect function."
            
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])

        if function_name in SPELL_FUNCTION_MAP:
            return SPELL_FUNCTION_MAP[function_name](game_state=game_state, **arguments)
        else:
            return f"Error: AI chose an unknown spell function '{function_name}'."

    except Exception as e:
        return f"Error resolving spell effect with AI: {e}"