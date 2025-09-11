# game_manager.py
import yaml
import os
from classes import Environment, GameHistory
from llm_calls import player_action, npc_action, narration
from d6_rules import roll_d6_dice

# --- Configuration (can be moved to a config file later) ---
SCENARIO_FILE = "scenario.yaml"
INVENTORY_FILE = "inventory.yaml"
SPELLS_FILE = "spells.yaml"
DEBUG = True

class GameManager:
    """Manages the overall game state, logic, and turn progression."""

    def __init__(self, llm_config):
        """Initializes the game by loading all necessary data."""
        self.llm_config = llm_config
        self.game_history = GameHistory()
        self._load_data()
        self._setup_environment()
        self.turn_order = []
        self.current_turn_index = 0

    def _load_data(self):
        """Loads scenario, items, and spells from YAML files."""
        try:
            with open(SCENARIO_FILE, 'r') as f:
                self.scenario_data = yaml.safe_load(f)
            with open(INVENTORY_FILE, 'r') as f:
                self.all_items = yaml.safe_load(f).get('items', [])
            with open(SPELLS_FILE, 'r') as f:
                spells_list = yaml.safe_load(f)
                self.all_spells = {}
                for spell_entry in spells_list:
                    for spell_name, spell_data in spell_entry.items():
                        self.all_spells[spell_name.lower()] = spell_data
        except FileNotFoundError as e:
            raise Exception(f"Error loading game data: {e}")
        except yaml.YAMLError as e:
            raise Exception(f"Error parsing YAML file: {e}")

    def _load_character_sheet(self, filepath):
        """Helper to load a character sheet."""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError) as e:
            print(f"ERROR: Could not load/parse character sheet at {filepath}: {e}")
            return None

    def _setup_environment(self):
        """Instantiates the environment, players, and NPCs."""
        self.environment = Environment(
            self.scenario_data,
            self.all_items,
            self.all_spells,
            self.scenario_data.get('players', []),
            self.scenario_data.get('actors', []),
            self._load_character_sheet
        )
        self.players = self.environment.players
        self.actors = self.environment.actors

    # --- NEW HELPER METHOD ---
    def _process_npc_turns(self):
        """
        A loop that processes all consecutive NPC turns, stopping when a
        player character is next.
        """
        output_log = []
        while True:
            current_character = self.turn_order[self.current_turn_index]

            # If the character is a player, stop processing.
            if current_character.is_player:
                break

            # It's an NPC's turn.
            output_log.append(f"\n--- {current_character.name}'s Turn ---")
            
            npc_turn_result = npc_action(
                current_character, self.game_history, self.environment,
                self.players, self.actors, self.llm_config, DEBUG
            )
            
            if npc_turn_result.get("narrative"):
                output_log.append(npc_turn_result["narrative"])
            
            if npc_turn_result.get("mechanical"):
                output_log.append(f"Mechanics: {npc_turn_result['mechanical']}")
                final_narration = narration(
                    current_character, self.environment, self.players, self.actors,
                    npc_turn_result["mechanical"], self.game_history, self.llm_config, DEBUG
                )
                output_log.append(final_narration)

            # Advance to the next character for the next loop iteration
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        
        return output_log

    # --- UPDATED METHOD ---
    def start_game(self):
        """Rolls initiative and prepares the game for the first turn."""
        all_combatants = self.players + self.actors
        initiative_rolls = []
        for combatant in all_combatants:
            dex_pips = combatant.get_attribute_or_skill_pips('dexterity')
            wis_pips = combatant.get_attribute_or_skill_pips('wisdom')
            score = roll_d6_dice(dex_pips) + roll_d6_dice(wis_pips)
            initiative_rolls.append((score, combatant))

        initiative_rolls.sort(key=lambda x: x[0], reverse=True)
        self.turn_order = [combatant for _, combatant in initiative_rolls]
        self.current_turn_index = 0

        # Generate initial game state description
        output_log = ["--- Game Start ---"]
        initiative_list = "\n".join([f"{i+1}. {c.name}" for i, c in enumerate(self.turn_order)])
        output_log.append(f"Initiative Order:\n{initiative_list}\n")
        
        first_character = self.turn_order[0]
        room, zone = self.environment.get_current_room_data(first_character.location)
        output_log.append(f"Location: {room['name']} - {zone['description']}\n")
        
        # --- LOGIC TO HANDLE NPC STARTING FIRST ---
        # Process any NPC turns at the beginning of combat.
        npc_logs = self._process_npc_turns()
        output_log.extend(npc_logs)

        # Now, prompt the correct player.
        first_player = self.turn_order[self.current_turn_index]
        output_log.append(f"It's {first_player.name}'s turn. What do you do?")
        return "\n".join(output_log)

    # --- UPDATED METHOD ---
    def process_player_command(self, command):
        """Processes a player command, then processes all subsequent NPC turns."""
        if not self.turn_order:
            return "The game hasn't started yet. Please start a new game."

        output_log = []
        
        player_character = self.turn_order[self.current_turn_index]
        if not player_character.is_player:
            return "ERROR: Game is expecting an NPC to act, not a player. State is out of sync."

        mechanical_result = player_action(
            command, player_character, self.game_history,
            self.environment, self.players, self.actors, self.llm_config, DEBUG
        )
        
        if mechanical_result:
            output_log.append(f"Mechanics: {mechanical_result}")
            narrative_text = narration(
                player_character, self.environment, self.players, self.actors,
                mechanical_result, self.game_history, self.llm_config, DEBUG
            )
            output_log.append(narrative_text)
        else:
            self.game_history.add_dialogue(player_character.name, command)
            output_log.append(f"{player_character.name}: \"{command}\"")

        # Advance turn index past the player
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)

        # Process all following NPC turns
        npc_logs = self._process_npc_turns()
        output_log.extend(npc_logs)

        # Prompt the next player
        next_player_character = self.turn_order[self.current_turn_index]
        output_log.append(f"\nIt's now {next_player_character.name}'s turn. What do you do?")

        return "\n".join(output_log)