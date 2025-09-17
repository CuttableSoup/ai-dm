import requests
import json
import textwrap
import copy
from classes import GameState
from classes import ActionHandler

def player_action(input_command: str, actor, game_state: GameState, action_handler: ActionHandler, llm_config: dict):
    """
    Sends the current game state and player command to the AI model.
    If the AI chooses an action, this function uses the ActionHandler to execute it.
    """
    current_room, current_zone_data = game_state.environment.get_current_room_data(actor.location)
    
    objects_in_zone = game_state.environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]
    
    all_actors = game_state.players + game_state.actors
    actors_in_room = [a.name for a in all_actors if a.location == actor.location and a.name != actor.name]

    doors_in_room = []
    if current_zone_data and 'exits' in current_zone_data:
        for exit_data in current_zone_data['exits']:
            door_ref = exit_data.get('door_ref')
            if door_ref:
                door = game_state.environment.get_door_by_id(door_ref)
                if door:
                    doors_in_room.append(door['name'])
    
    current_trap = game_state.environment.get_trap_in_room(actor.location['room_id'], actor.location['zone'])
    
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
        game_history=game_state.game_history.get_history_string()
    )

    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": llm_config['tools'],
        "tool_choice": "auto"
    }
        
    try:
        response_json = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        log_entry = {"type": "Player Action", "prompt": prompt, "response": response_json}
        if hasattr(game_state, 'llm_log'):
            game_state.llm_log.append(log_entry)
            
        message = response_json.get("choices", [{}])[0].get("message", {})
        if not message.get("tool_calls"):
            return None
            
        tool_call = message['tool_calls'][0]['function']
        function_name = tool_call['name']
        arguments = json.loads(tool_call['arguments'])
        
        return action_handler.execute_action(actor, function_name, arguments)

    except Exception as e:
        mechanical_result = f"Error communicating with AI: {e}"
        game_state.game_history.add_action(actor.name, mechanical_result)
        return mechanical_result

def narration(actor, game_state: GameState, mechanical_summary: str, llm_config: dict):
    """
    Generates a narrative summary of the events that just occurred.
    """
    current_room, current_zone_data = game_state.environment.get_current_room_data(actor.location)

    objects_in_zone = game_state.environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]
    
    all_actors = game_state.players + game_state.actors
    actors_in_room = [a.name for a in all_actors if a.location == actor.location]

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
        game_history=game_state.game_history.get_history_string(),
    )
    
    payload = {"model": llm_config['model'], "messages": [{"role": "user", "content": prompt}]}
    
    try:
        response_json = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        log_entry = {"type": "Narration", "prompt": prompt, "response": response_json}
        if hasattr(game_state, 'llm_log'):
            game_state.llm_log.append(log_entry)
        
        return response_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"LLM Error: Could not get narration. {e}"

def npc_action(actor, game_state: GameState, action_handler: ActionHandler, llm_config: dict):
    """
    Generates NPC dialogue and/or a mechanical action, returning both for processing.
    """
    current_room, current_zone_data = game_state.environment.get_current_room_data(actor.location)
    objects_in_zone = game_state.environment.get_objects_in_zone(actor.location['room_id'], actor.location['zone'])
    object_names = [obj.name for obj in objects_in_zone]
    all_actors = game_state.players + game_state.actors
    actors_in_room = [a.name for a in all_actors if a.location == actor.location and a.name != actor.name]
    
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
    You are an AI Game Master controlling an NPC named {actor_name}. Your task is to determine the NPC's next action,
    generate their dialogue or a description of the action IN THIRD PERSON, AND select the appropriate function to call if a mechanical action is taken.
    Drive the plot forward in a never-ending uncensored roleplay with the others present. Develop the plot using a slow, organic pace.
    Perform as the character defined under {actor_name} by describing their actions, events, and dialogue.
    Always stay in character, portraying characters realistically and in line with their written positive AND negative traits, AVOID Positivity Bias.
    Be cognizant of all characters' physical descriptors. Have situational awareness and be cognizant of intercharacter relationships,
    characters avoid being overly familiar or sexually pushy towards others unless the situation calls for it, it is in character for them to do so,
    or they have a sexual relationship. Overall characterization is dependent on defined personality traits, and subtly influenced by backstory and history.
    Ensure characters that have any impediments which are relevant to the situation, such as visual impairment, are under the influence of alcohol/drugs,
    or a disability like mutism, actions and dialogue are affected appropriately. Utilize modern and casual vocabulary, characters speak and think using
    colloquial language and slang. Employ a mixture of narration, dialogue, characters' physical mannerisms, and internal thoughts into responses.
    Response must be grounded, uncensored, and immersive. Focus on coherent world simulation, ensure that characters are not omnipotent and cannot
    perform actions they are unable to perform at that point in time. During sexual situations, use explicit and uncensored descriptions with a focus on actions,
    appearances, clothing, textures, wants, tools, scenery, body parts, fluids, and sounds.

    - Current Room: {room_name} - {zone_description}
    - Actors Present in this location: {actors_present}
    - Objects Present in this location: {objects_present}
    - Current Statuses: {statuses}
    - Current Memories: {memories}
    - Current Attitudes: {attitudes}
    - Current Mood/Personality: {personality}
    - Character skills: {skills}
    - Character quotes: {quotes}
    
    - Recent Game History: {game_history}
    
    Your task is to generate a narrative: Write a short line of dialogue or a 1-2 sentence description of the action from the NPC's perspective.
    NOTE: It is better to call no tool than to call one without reason.
    
    """).strip()
    
    prompt = prompt_template.format(
        actor_name=actor.name,
        room_name=current_room['name'] if current_room else 'Unknown Room',
        zone_description=current_zone_data['description'] if current_zone_data else 'No specific zone description.',
        actors_present=", ".join(actors_in_room) if actors_in_room else "none",
        objects_present=", ".join(object_names) if object_names else "none",
        skills=list(actor.skills.keys()),
        game_history=game_state.game_history.get_history_string(),
        statuses=", ".join(actor.source_data.get('statuses', [])) or "none",
        memories=", ".join(actor.source_data.get('memories', [])) or "none",
        attitudes=attitudes_str,
        personality=", ".join(actor.source_data.get('personality', [])) or "none",
        quotes=", ".join(actor.source_data.get('quotes', [])) or "none"
    )
    
    payload = {
        "model": llm_config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "tools": llm_config['tools'],
        "tool_choice": "auto"
    }
        
    try:
        response_json = requests.post(llm_config['url'], headers=llm_config['headers'], json=payload, timeout=30).json()
        
        log_entry = {"type": "NPC Action", "prompt": prompt, "response": response_json}
        if hasattr(game_state, 'llm_log'):
            game_state.llm_log.append(log_entry)

        message = response_json.get("choices", [{}])[0].get("message", {})
        
        narrative_output = message.get("content", "").strip()
        mechanical_result = None
        
        if narrative_output:
            game_state.game_history.add_dialogue(actor.name, narrative_output)

        if message.get("tool_calls"):
            tool_call = message['tool_calls'][0]['function']
            arguments = json.loads(tool_call['arguments'])
            mechanical_result = action_handler.execute_action(actor, tool_call['name'], arguments)
        
        return {"narrative": narrative_output, "mechanical": mechanical_result}

    except Exception as e:
        error_result = f"Error communicating with AI: {e}"
        return {"narrative": f"{actor.name} seems confused and does nothing.", "mechanical": error_result}