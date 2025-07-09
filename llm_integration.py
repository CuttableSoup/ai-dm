import json
import requests
from config import ACTION_MODEL, LLM_API_URL, DEBUG
from game_state import game_state
from actions import (
    execute_look, execute_check_self, execute_move, execute_move_zone,
    execute_attack, execute_skill_check, execute_take_item, execute_drop_item,
    execute_equip_item, execute_unequip_item, pass_turn
)

# The toolset is updated for zones, range, and new actions
available_tools = [
    {   "type": "function", "function": {
            "name": "execute_look", "description": "Get a detailed description of the current room, including zones, objects, exits, and other characters.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
    {   "type": "function", "function": {
            "name": "execute_check_self", "description": "Check your own character's status, including health, condition, equipment, inventory, and location.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
    {   "type": "function", "function": {
            "name": "execute_move", "description": "Move your character through a named exit into an adjacent room.",
            "parameters": {"type": "object", "properties": { "exit_name": {"type": "string", "description": "The name of the exit to move through."}}, "required": ["exit_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_move_zone", "description": "Move to an adjacent numbered zone within the current room to change position. This triggers a passive perception check for traps.",
            "parameters": {"type": "object", "properties": { "target_zone": {"type": "integer", "description": "The number of the adjacent zone to move to."}}, "required": ["target_zone"]}}},
    {   "type": "function", "function": {
            "name": "execute_attack", "description": "Performs an attack against a single target in the same room. The success depends on weapon range and zone distance.",
            "parameters": {"type": "object", "properties": { "target_name": {"type": "string", "description": "The name of the character being attacked."}}, "required": ["target_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_skill_check", "description": "Use a skill on an object, an exit, or another character. To search the general area for hidden things, provide 'Search' as the skill_name and nothing else.",
            "parameters": {"type": "object", "properties": {
                "skill_name": {"type": "string", "description": "The name of the skill being used, e.g., 'Search'."},
                "target_name": {"type": "string", "description": "Optional: The character being targeted by the skill (must be in the same zone)."},
                "object_name": {"type": "string", "description": "Optional: The object or exit being targeted by the skill (must be in the right zone)."}}, "required": ["skill_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_take_item", "description": "Take an item from a container, an object, or an incapacitated character in your current zone.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item to take."},
                "source_name": {"type": "string", "description": "The name of the object or character to take from."}}, "required": ["item_name", "source_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_drop_item", "description": "Drop an item from your inventory or equipment onto the floor of your current zone.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item you want to drop."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_equip_item", "description": "Equip or take out an item from your inventory. You cannot equip an item if the location (e.g. head, chest, hands) is already full.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item from your inventory to equip."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "execute_unequip_item", "description": "Unequip, stow, or put away an item, moving it from your equipment to your inventory.",
            "parameters": {"type": "object", "properties": {
                "item_name": {"type": "string", "description": "The name of the item you are currently wearing/wielding."}}, "required": ["item_name"]}}},
    {   "type": "function", "function": {
            "name": "pass_turn", "description": "Use this if the character wants to wait, do nothing, defend, or say something that doesn't require a skill check.",
            "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Optional: a brief reason for passing, such as dialogue."}},"required": []}}}
]

def get_llm_action_and_execute(command, actor, is_combat):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """
    actor_room = game_state["environment"].get_room(actor.current_room)
    other_chars_in_room = [e for e in game_state['players'] + game_state['npcs'] if e.id != actor.id and e.current_room == actor.current_room]
    
    current_zone_data = actor_room.get("zones", {}).get(str(actor.current_zone), {})
    adjacent_zones = current_zone_data.get("adjacent_zones", [])
    character_locations = ", ".join([f"{c.name} in Zone {c.current_zone}" for c in other_chars_in_room]) or 'None'
    objects_in_room = [o for o in actor_room.get("objects", [])]
    object_locations = ", ".join([f"{o['name']} in Zone {o.get('zone', 'N/A')}" for o in objects_in_room]) or 'None'

    # An explicit, rule-based prompt to guide the AI
    prompt_template = """You are an AI assistant for a text-based game. Your task is to translate a player's command into a specific function call.
Player Command: '{command}'

**CONTEXT**
- Your Status: {actor_description}
- Your Location: Zone {actor_zone}
- Adjacent Zones: {adjacent_zones}
- Characters Present: {character_locations}
- Interactable Objects & Exits Present: {object_locations}

**FUNCTION SELECTION RULES - Follow these steps:**
1.  **Is the command an attack on a CHARACTER?**
    - If yes, call `execute_attack`.
    - The `target_name` parameter MUST be a character from the 'Characters Present' list.

2.  **Is the command to search the general area (e.g., 'search the room')?**
    - If yes, you **MUST** call `execute_skill_check` with ONLY the `skill_name` 'Search'.
    - Do **NOT** provide `object_name` or `target_name`.

3.  **Is the command using a skill (like search, lift, investigate) on an OBJECT or EXIT?**
    - If yes, you **MUST** call `execute_skill_check`.
    - The `skill_name` should be the skill used (e.g., 'Search').
    - The `object_name` **MUST** be the name of the object/exit from the 'Interactable Objects & Exits Present' list (e.g., 'Crumbling Stones').
    - Do **NOT** use the `target_name` parameter for objects/exits.

4.  **Is the command using a skill on another CHARACTER?**
    - If yes, call `execute_skill_check`.
    - The `target_name` **MUST** be a character from the 'Characters Present' list.
    - Do **NOT** use the `object_name` parameter for characters.

5.  **Is the command to move between ZONES?**
    - If yes, call `execute_move_zone`.

6.  **If none of the above rules match**, choose another appropriate function like `execute_look`, `execute_move` (for room exits), `execute_take_item`, or `pass_turn`.

Based on these strict rules, select the correct function and parameters.
"""

    prompt = prompt_template.format(
        actor_description=actor.get_status_summary(),
        actor_zone=actor.current_zone,
        adjacent_zones=", ".join(map(str, adjacent_zones)) or "None",
        character_locations=character_locations,
        object_locations=object_locations,
        command=command
    )
    if DEBUG: print(f"\n[DEBUG] PROMPT FOR LLM ACTION:\n---\n{prompt}\n---\n")

    # Prepare and send the request to the AI model
    headers = {"Content-Type": "application/json"}
    payload = {"model": ACTION_MODEL, "messages": [{"role": "user", "content": prompt}], "tools": available_tools, "tool_choice": "auto"}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        if DEBUG: print(f"[DEBUG] LLM Action Response: {json.dumps(response, indent=2)}")

        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return f"{actor.name} is unable to decide on an action and passes the turn."
            
        # Extract the function name and arguments from the AI's response
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        # NOTE: Pass the 'actor' object directly instead of a name to avoid ambiguity.
        # Call the chosen function
        if function_name == "execute_attack": return execute_attack(actor, **arguments)
        if function_name == "execute_skill_check": return execute_skill_check(actor, **arguments)
        if function_name == "execute_take_item": return execute_take_item(actor, **arguments)
        if function_name == "execute_drop_item": return execute_drop_item(actor, **arguments)
        if function_name == "execute_equip_item": return execute_equip_item(actor, **arguments)
        if function_name == "execute_unequip_item": return execute_unequip_item(actor, **arguments)
        if function_name == "pass_turn": return pass_turn(actor, **arguments)
        if function_name == "execute_move": return execute_move(actor, **arguments)
        if function_name == "execute_move_zone": return execute_move_zone(actor, **arguments)
        if function_name == "execute_look": return execute_look(actor, **arguments)
        if function_name == "execute_check_self": return execute_check_self(actor, **arguments)
        
        return f"Error: The AI tried to call an unknown function '{function_name}'."
    except Exception as e:
        return f"Error communicating with AI: {e}"