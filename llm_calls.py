import requests
import json
from actions import execute_skill_check, manage_item, manage_party_member, move_party, cast_spell
import textwrap
import copy

def execute_function_call(actor, function_name, arguments, environment, players, actors, game_history, party, llm_config):
    """
    A helper to execute the function call from the LLM's response.
    This function is now passed the necessary game state components.
    """
    if function_name == "execute_skill_check":
        mechanical_result = execute_skill_check(actor, environment=environment, players=players, actors=actors, **arguments)
        game_history.add_action(actor.name, f"attempted to use {arguments.get('skill', 'a skill')} on {arguments.get('target', 'a target')}.")
        return mechanical_result
    
    elif function_name == "manage_item":
        mechanical_result = manage_item(actor=actor, environment=environment, party=party, players=players, actors=actors, **arguments)
        action_desc = arguments.get('action', 'manage')
        item_desc = arguments.get('item_name', 'an item')
        target_desc = f" on {arguments.get('target_name', 'a target')}" if 'target_name' in arguments else ""
        game_history.add_action(actor.name, f"attempted to {action_desc} {item_desc}{target_desc}.")
        return mechanical_result

    elif function_name == "manage_party_member":
        mechanical_result = manage_party_member(actor=actor, party=party, actors=actors, **arguments)
        action_desc = arguments.get('action', 'manage')
        member_desc = arguments.get('member_name', 'a character')
        game_history.add_action(actor.name, f"attempted to {action_desc} {member_desc} from the party.")
        return mechanical_result

    elif function_name == "move_party":
        mechanical_result = move_party(actor=actor, environment=environment, party=party, **arguments)
        dest_desc = arguments.get('destination_zone', 'a new area')
        game_history.add_action(actor.name, f"attempted to move the party to {dest_desc}.")
        return mechanical_result
    
    elif function_name == "cast_spell":
        mechanical_result = cast_spell(actor=actor, environment=environment, players=players, actors=actors, party=party, game_history=game_history, llm_config=llm_config, **arguments)
        action_desc = arguments.get('spell_name', 'a spell')
        target_desc = arguments.get('target_name', 'a target')
        game_history.add_action(actor.name, f"attempted to cast {action_desc} on {target_desc}.")
        return mechanical_result

    mechanical_result = f"Error: The AI tried to call an unknown function '{function_name}'."
    game_history.add_action(actor.name, mechanical_result)
    return mechanical_result

def player_action(input_command, actor, game_history, environment, players, actors, party, llm_config, debug=False):
    """
    Sends the current game state and player command to the AI model,
    which then chooses an action (a function) to execute.
    """
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    
    # Get objects from the new Environment method
    objects_in_zone = environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]
    
    actors_in_room = [a.name for a in players + actors if a.location == actor.location and a.name != actor.name]

    doors_in_room = []
    if current_zone_data and 'exits' in current_zone_data:
        for exit_data in current_zone_data['exits']:
            door_ref = exit_data.get('door_ref')
            if door_ref:
                door = environment.get_door_by_id(door_ref)
                if door:
                    doors_in_room.append(door['name'])
    
    current_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    
    prompt_template = textwrap.dedent("""
    You are an AI assistant for a text-based game. Your task is to determine if a described action requires a mechanical function call.

    Input: '{input_command}'

    **CONTEXT**
    - Actor Name: {actor_name}
    - Actor Skills: {actor_skills}
    - Actors Present: {actors_present}
    - Objects Present: {objects_present}
    - Doors Present: {doors_present}
    - Traps Present: {traps_present}
    - Recent Game History: {game_history}

    **FUNCTION SELECTION RULES - Follow these steps STRICTLY:**
    1.  **Analyze the INTENT.** Is the character trying to perform a specific, mechanical action?
    2.  **Check for SKILL USE.** If the action involves using a skill, you **MUST** call `execute_skill_check`.
        - The `skill` argument must be a relevant skill from `{actor_skills}`.
        - The `target` argument must match an item from the lists.
    3.  **IGNORE DIALOGUE AND FLAVOR TEXT.** If the input is just dialogue, an emotional reaction, or a description of an action without a clear target (e.g., "fiddling with a lockpick," "observing the room," "muttering to himself"), it is NOT a mechanical action. In this case, you **MUST NOT** call any function. Return an empty response.
    4.  **PRIORITY:** It is better to do nothing than to call a function incorrectly. If you are not certain, do not call a function.
    """).strip()

    prompt = prompt_template.format(
        input_command=input_command,
        actor_name=actor.name,
        actor_skills=list(actor.skills.keys()),
        actors_present=actors_in_room,
        objects_present=object_names,
        doors_present=doors_in_room,
        traps_present=[current_trap['name']] if current_trap else [],
        game_history=game_history.get_history_string()
    )

    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": llm_config['tools'],
        "tool_choice": "auto"
    }
    
    if debug:
        print("\n--- LLM Narrative Request Payload ---")
        prompt_content = payload["messages"][0]["content"]
        print("--- Prompt ---")
        print(prompt_content)
        print("--- End Prompt ---")
        
        temp_payload_for_log = copy.deepcopy(payload)
        temp_payload_for_log["messages"][0]["content"] = "[See prompt above]"
        print(json.dumps(temp_payload_for_log, indent=2))
        print("-----------------------------------\n")
        
    try:
        response = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        
        if debug:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
            
        message = response.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            game_history.add_dialogue(actor.name, input_command)
            return None
            
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        return execute_function_call(actor, function_name, arguments, environment, players, actors, game_history, party, llm_config)

    except Exception as e:
        mechanical_result = f"Error communicating with AI: {e}"
        game_history.add_action(actor.name, mechanical_result)
        return mechanical_result

def narration(actor, environment, players, actors, mechanical_summary, game_history, llm_config, debug=False):
    """
    Generates a narrative summary of the events that just occurred.
    """
    current_room, current_zone_data = environment.get_current_room_data(actor.location)

    # Get objects from the new Environment method
    objects_in_zone = environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]

    actors_in_room = [a.name for a in players + actors if a.location == actor.location]

    prompt_template = textwrap.dedent("""
    You are the narrator of a grounded, text-based RPG. Your job is to describe the outcome of the player's action in a vivid and engaging way, like a good Dungeon Master.
    **CONTEXT**
    - Current Room: {room_name} - {zone_description}
    - Actors Present in this location: {actors_present}
    - Objects Present in this location: {objects_present}
    - Recent Game History: {game_history}
    - **Mechanical Summary:** {mechanical_summary} <-- This is what actually happened. Your narration MUST align perfectly with this result.

    **Your Task:**
    1.  Write a short (2-3 sentences) narrative description from a third-person perspective focused on {player_name}.
    2.  Start by briefly describing the character's *attempted action*.
    3.  Seamlessly weave in the **Mechanical Summary** to describe the final result.
    4.  Use sensory details (the sound of a lock, the smell of dust, the glint of steel) to immerse the player.
    5.  Keep the tone grounded and cinematic. Avoid overly dramatic or poetic language.
    """).strip()

    prompt = prompt_template.format(
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(object_names) if object_names else "none",
        mechanical_summary=mechanical_summary,
        player_name=actor.name,
        game_history=game_history.get_history_string(),
    )
    
    payload = {"model": llm_config['model'], "messages": [{"role": "user", "content": prompt}]}
    
    if debug:
        print("\n--- LLM Response Request Payload ---")
        prompt_content = payload["messages"][0]["content"]
        print("--- Prompt ---")
        print(prompt_content)
        print("--- End Prompt ---")
        
        temp_payload_for_log = copy.deepcopy(payload)
        temp_payload_for_log["messages"][0]["content"] = "[See prompt above]"
        print(json.dumps(temp_payload_for_log, indent=2))
        print("------------------------------------\n")

    try:
        response = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        
        if debug:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
        
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"LLM Error: Could not get narration. {e}"

def npc_action(actor, game_history, environment, players, actors, party, llm_config, debug=False):
    """
    Generates NPC dialogue and/or a mechanical action, returning both for processing.
    """
    # ... (the entire top part of the function with the prompt setup is the same)
    current_room, current_zone_data = environment.get_current_room_data(actor.location)
    objects_in_zone = environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]
    actors_in_room = [a.name for a in players + actors if a.location == actor.location and a.name != actor.name]
    doors_in_room = []
    if current_zone_data and 'exits' in current_zone_data:
        for exit_data in current_zone_data['exits']:
            door_ref = exit_data.get('door_ref')
            if door_ref:
                door = environment.get_door_by_id(door_ref)
                if door:
                    doors_in_room.append(door['name'])
    current_trap = environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    attitudes_list = actor.source_data.get('attitudes', [])
    attitudes_str = "none"
    if attitudes_list:
        formatted_attitudes = [f"{k}: {v}" for d in attitudes_list for k, v in d.items()]
        attitudes_str = ", ".join(formatted_attitudes)
    character_qualities = actor.source_data.get('qualities', {})
    gender = character_qualities.get('gender', 'unknown')
    race = character_qualities.get('race', 'unknown')
    occupation = character_qualities.get('occupation', 'unknown')
    eyes = character_qualities.get('eyes', 'unknown')
    hair = character_qualities.get('hair', 'unknown')
    skin = character_qualities.get('skin', 'unknown')
    prompt_template = textwrap.dedent("""
    You are an AI Game Master controlling an NPC named {actor_name}. Your task is to determine the NPC's next action, generate their dialogue or a description of the action IN THIRD PERSON, AND select the appropriate function to call if a mechanical action is taken.

    **Instructions:**
    1.  **Review the Context:** Use the Personality, Attitudes, and the Recent Game History to decide on a logical and in-character action.
    2.  **Generate Narrative:** Write a short line of dialogue or a 1-2 sentence description of the action from the NPC's perspective. This will be shown to the player.
    3.  **Perform a Mechanical Action (If Necessary):**
        - The arguments for the function must be chosen from the lists of available targets.
        - If the action is just talking, observing, or simple movement without a mechanical check, **DO NOT** call any function. Just provide the narrative text.

    **CONTEXT FOR THE DECISION**
    - Current Room: {room_name} - {zone_description}
    - Actors Present in this location: {actors_present}
    - Objects Present in this location: {objects_present}
    - Recent Game History: {game_history}
    - Current Statuses: {statuses}
    - Current Memories: {memories}
    - Current Attitudes: {attitudes}
    - Current Mood/Personality: {personality}
    - Character skills: {actor_skills}
    - Character quotes: {character_quotes}
    - Character Qualities (for narrative description of {player_name}):
    - Gender: {player_gender}
    - Race: {player_race}
    - Eyes: {player_eyes}
    - Hair: {player_hair}
    - Skin: {player_skin}
    """).strip()
    
    prompt = prompt_template.format(
        actor_name=actor.name,
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(object_names) if object_names else "none",
        actor_skills=list(actor.skills.keys()),
        player_name=actor.name,
        game_history=game_history.get_history_string(),
        statuses=", ".join(actor.source_data.get('statuses', [])) or "none",
        memories=", ".join(actor.source_data.get('memories', [])) or "none",
        attitudes=attitudes_str,
        personality=", ".join(actor.source_data.get('personality', [])) or "none",
        character_quotes=", ".join(actor.source_data.get('quotes', [])) or "none",
        player_gender=gender, player_race=race, player_occupation=occupation,
        player_eyes=eyes, player_hair=hair, player_skin=skin
    )
    
    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": llm_config['tools'],
        "tool_choice": "auto"
    }
    
    if debug:
        print("\n--- LLM Narrative Request Payload ---")
        prompt_content = payload["messages"][0]["content"]
        print("--- Prompt ---")
        print(prompt_content)
        print("--- End Prompt ---")
        
        temp_payload_for_log = copy.deepcopy(payload)
        temp_payload_for_log["messages"][0]["content"] = "[See prompt above]"
        print(json.dumps(temp_payload_for_log, indent=2))
        print("-----------------------------------\n")
        
    try:
        response = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        message = response.get("choices", [{}])[0].get("message", {})
        
        if debug:
            print(f"\n--- LLM Raw Response ---\n{json.dumps(response, indent=2)}\n------------------------\n")
        
        narrative_output = message.get("content", "").strip()
        mechanical_result = None
        
        if narrative_output:
            game_history.add_dialogue(actor.name, narrative_output)

        if message.get("tool_calls"):
            tool_call = message['tool_calls'][0]['function']
            mechanical_result = execute_function_call(actor, tool_call['name'], json.loads(tool_call['arguments']), environment, players, actors, game_history, party, llm_config)
        
        # Return both the narrative and the mechanical result
        return {"narrative": narrative_output, "mechanical": mechanical_result}

    except Exception as e:
        error_result = f"Error communicating with AI: {e}"
        # Return the error in the same format
        return {"narrative": f"{actor.name} seems confused and does nothing.", "mechanical": error_result}