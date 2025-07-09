import requests
from game_state import game_state, scenario_data
from config import NARRATIVE_MODEL, LLM_API_URL

def get_llm_story_response(mechanical_summary, actor):
    """
    Generates a narrative summary of the events that just occurred.
    """
    actor_room_key = actor.current_room
    entities_in_room = [e for e in game_state['players'] + game_state['npcs'] if e.current_room == actor_room_key]
    statuses = "\n".join([p.get_status_summary() for p in entities_in_room]) if entities_in_room else "None"
    
    actor_room = game_state["environment"].get_room(actor.current_room)
    prompt_template = scenario_data["prompts"]["narrative_summary"]

    # Format the prompt with all the necessary context
    prompt = prompt_template.format(
        actor_name=actor.name,
        room_name=actor_room.get("name"),
        room_description=actor_room.get("description"),
        statuses=statuses,
        mechanical_summary=mechanical_summary
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {"model": NARRATIVE_MODEL, "messages": [{"role": "user", "content": prompt}]}
    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30).json()
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or f"LLM (empty response): {mechanical_summary}"
    except Exception as e:
        return f"LLM Error: Could not get narration. {e}"
