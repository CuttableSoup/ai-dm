import sys
from datetime import datetime

from config import SCENARIO_FILE
from game_state import game_state, scenario_data
from utils import Tee
from actions import execute_look, pass_turn
from llm_integration import get_llm_action_and_execute
from npc_ai import get_enemy_action
from narrative_ai import get_llm_story_response
from game_setup import load_scenario, setup_initial_encounter, roll_initiative
from d6_rules import ATTITUDE_HOSTILE

# --- 7. Main Game Loop ---
def main_game_loop():
    """The main loop that runs the game."""
    log_filename = f"game_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    original_stdout = sys.stdout
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        # Redirect all print statements to both the console and the log file
        sys.stdout = Tee(original_stdout, log_file)

        if not load_scenario(SCENARIO_FILE) or not setup_initial_encounter():
            sys.stdout = original_stdout
            return

        # Keywords to help determine the type of input
        action_keywords = ["attack", "climb", "lift", "run", "swim", "dodge", "fly", "ride", "pilot", "operate", "pick", "repair", "craft", "track", "move", "go", "enter", "use", "look", "search", "take", "get", "grab", "check", "status", "inventory", "shoot", "drop", "equip", "unequip", "wear", "remove"]
        mechanical_summary_keywords = ["attack:", "hit!", "miss!", "roll:", "success", "failure", "vs dn"]
        
        player = game_state["players"][0]
        # NOTE: Pass the 'player' object directly.
        initial_look = execute_look(player)
        print(f"\nSCENE START: {scenario_data.get('scenario_name', 'Unnamed Scenario')}\n{initial_look}")

        is_combat_mode = False
        turn_summaries = []
        # Initial turn order is just players then npcs
        game_state["turn_order"] = game_state["players"] + game_state["npcs"]
        last_active_actor = player

        # --- The Game Loop ---
        while True:
            # Check if combat should start or end
            player_room = game_state["players"][0].current_room
            hostiles_in_room = any(e.attitude == ATTITUDE_HOSTILE and e.current_room == player_room and not e.is_incapacitated() for e in game_state["npcs"])
            
            # Start combat if it's not already active and there are hostiles
            if not is_combat_mode and hostiles_in_room and any(p.attitude == ATTITUDE_HOSTILE for p in game_state["players"]):
                print("\n" + "="*20); print("HOSTILITIES DETECTED! Entering Combat Mode!"); print("="*20)
                is_combat_mode = True; game_state["round_number"] = 1
                roll_initiative()
                if not game_state["turn_order"]:
                    print("No one is left to fight.")
                    is_combat_mode = False
                else:
                    print(f"\n--- Beginning Combat Round {game_state['round_number']} ---")
                game_state["current_turn_entity_index"] = 0
            
            # End combat if it's active but there are no more hostiles
            elif is_combat_mode and not hostiles_in_room:
                print("\n" + "="*20); print("COMBAT ENDS. No active hostiles present."); print("="*20)
                is_combat_mode = False
                game_state["turn_order"] = game_state["players"] + game_state["npcs"]
                game_state["current_turn_entity_index"] = 0

            # --- End of Round Summary ---
            if game_state["current_turn_entity_index"] >= len(game_state["turn_order"]):
                last_turn_actor = last_active_actor
                # Find the last significant action to summarize for the narrator
                action_summary_for_narrator = next((s for s in reversed(turn_summaries) if any(k in s.lower() for k in mechanical_summary_keywords)), "The characters paused and took in their surroundings.")
                print(f"\nNARRATIVE SUMMARY:\n{get_llm_story_response(action_summary_for_narrator, last_turn_actor)}\n")
                
                turn_summaries = []
                game_state["current_turn_entity_index"] = 0
                if is_combat_mode:
                    game_state["round_number"] += 1
                    print(f"--- End of Combat Round {game_state['round_number'] - 1} ---")
                    roll_initiative() # Re-roll initiative for the new round
                    if not game_state["turn_order"]:
                        is_combat_mode = False
                    else:
                        print(f"\n--- Beginning Combat Round {game_state['round_number']} ---")
            
            if not game_state["turn_order"]:
                print("No one available. Game over?")
                break

            current_entity = game_state["turn_order"][game_state["current_turn_entity_index"]]

            # Skip turns for characters not in the player's room during non-combat
            if not is_combat_mode and current_entity.current_room != player.current_room:
                game_state["current_turn_entity_index"] += 1
                continue

            summary = ""
            if current_entity.is_incapacitated():
                # --- MODIFIED: Suppress "cannot act" message for mindless traps ---
                is_mindless_trap = "trap" in current_entity.statuses
                if not is_mindless_trap:
                    summary = f"{current_entity.name} is incapacitated and cannot act."
            else:
                # --- Player's Turn ---
                if current_entity in game_state["players"]:
                    command = input(f"Your action, {current_entity.name} (in {current_entity.current_room}, Zone {current_entity.current_zone}): ")
                    if command.lower() in ["quit", "exit"]:
                        print("Exiting game.")
                        break
                    
                    # If the command looks like an action, send it to the AI for interpretation
                    if any(keyword in command.lower() for keyword in action_keywords):
                        summary = get_llm_action_and_execute(command, current_entity, is_combat_mode)
                    else: # Otherwise, treat it as simple dialogue
                        # NOTE: Pass the 'current_entity' object directly.
                        summary = pass_turn(current_entity, reason=command)
                
                # --- NPC's Turn ---
                else:
                    last_summary = turn_summaries[-1] if turn_summaries else "The scene begins."
                    summary = get_enemy_action(current_entity, is_combat_mode, last_summary)

            # Print the outcome of the turn, but only if there is something to say
            if summary:
                # Check if the summary is just dialogue.
                is_dialogue = summary.strip().startswith(f'{current_entity.name}: "') and summary.strip().endswith('"')

                if is_dialogue:
                    print(f"\n{summary}\n") # Print only the dialogue
                else:
                    # For all other actions, use the detailed outcome format
                    print(f"\n-- Outcome for {current_entity.name}'s turn --\n{summary}\n----------------------------------")
                
                turn_summaries.append(summary)
                last_active_actor = current_entity

            # Move to the next character in the turn order
            game_state["current_turn_entity_index"] += 1

    # Restore standard output and inform the user where the log file is saved
    sys.stdout = original_stdout
    print(f"Game log saved to: {log_filename}")

if __name__ == "__main__":
    main_game_loop()
