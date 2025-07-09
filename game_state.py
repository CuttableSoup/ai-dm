# --- Global State Variables ---
# These variables store the game's data and are accessed throughout the program.
scenario_data = {}  # Holds all the data from the scenario.json file
game_state = {
    "players": [], "npcs": [], "environment": None,
    "turn_order": [], "current_turn_entity_index": 0, "round_number": 1
}
