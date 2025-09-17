import yaml
import pickle
from llm_calls import player_action, npc_action, narration
from d6_rules import roll_d6_dice
from classes import GameState
from classes import ActionHandler
from classes import Environment, GameHistory, Party

SCENARIO_FILE = "Training_Grounds.yaml"
INVENTORY_FILE = "inventory.yaml"

class GameManager:
    """Manages the overall game state, logic, and turn progression."""

    def __init__(self, llm_config):
        """Initializes the game by loading all necessary data."""
        self.llm_config = llm_config
        self._load_data()
        self._setup_game_state()
        self.action_handler = ActionHandler(self.game_state, self.llm_config)
        self.turn_order = []
        self.current_turn_index = 0
        self.gui_text_log = ""

    def _load_data(self):
        """Loads scenario, items, and spells from YAML files."""
        try:
            with open(SCENARIO_FILE, 'r') as f:
                self.scenario_data = yaml.safe_load(f)
            with open(INVENTORY_FILE, 'r') as f:
                self.all_items = yaml.safe_load(f).get('items', [])
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

    def _setup_game_state(self):
        """
        Instantiates the environment, players, and NPCs, and then bundles them
        into a single GameState object.
        """
        game_history = GameHistory()
        party = Party()

        actors_data = self.scenario_data.get('actors') or []
        environment = Environment(
            self.scenario_data,
            self.all_items,
            self.scenario_data.get('players', []),
            actors_data,
            self._load_character_sheet
        )

        for player in environment.players:
            party.add_member(player)

        self.game_state = GameState(environment, party, game_history)


    def save_game(self, filepath):
        """Saves the current game state to a file using pickle."""
        try:
            with open(filepath, 'wb') as f:
                pickle.dump(self, f)
            return True
        except Exception as e:
            print(f"Error saving game: {e}")
            return False

    @staticmethod
    def load_game(filepath):
        """Loads a game state from a file using pickle."""
        try:
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading game: {e}")
            return None

    def _process_npc_turns(self):
        output_log = []
        while True:
            if not self.turn_order: break
            current_character = self.turn_order[self.current_turn_index]
            if current_character.is_player: break
            
            output_log.append(f"\n--- {current_character.name}'s Turn ---")
            
            npc_turn_result = npc_action(
                current_character, 
                self.game_state,
                self.action_handler,
                self.llm_config
            )
            
            if npc_turn_result.get("narrative"):
                output_log.append(npc_turn_result["narrative"])
            if npc_turn_result.get("mechanical"):
                mechanical_text = npc_turn_result["mechanical"]
                output_log.append(f"Mechanics: {mechanical_text}")
                
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        return output_log

    def start_game(self):
        all_combatants = self.game_state.players + self.game_state.actors
        
        initiative_rolls = []
        for combatant in all_combatants:
            dex_pips = combatant.get_attribute_or_skill_pips('dexterity')
            wis_pips = combatant.get_attribute_or_skill_pips('wisdom')
            score = roll_d6_dice(dex_pips) + roll_d6_dice(wis_pips)
            initiative_rolls.append((score, combatant))
            
        initiative_rolls.sort(key=lambda x: x[0], reverse=True)
        self.turn_order = [combatant for _, combatant in initiative_rolls]
        self.current_turn_index = 0
        
        output_log = ["--- Welcome Adventurer ---"]
        
        npc_logs = self._process_npc_turns()
        output_log.extend(npc_logs)
        return "\n".join(output_log)

    def process_player_command(self, command):
        if not self.turn_order:
            return "The game hasn't started yet. Please start a new game."
            
        output_log = []
        player_character = self.turn_order[self.current_turn_index]
        
        if not player_character.is_player:
            return "ERROR: Game is expecting an NPC to act, not a player. State is out of sync."
        
        mechanical_result = player_action(
            command,
            player_character,
            self.game_state,
            self.action_handler,
            self.llm_config
        )

        if mechanical_result:
            output_log.append(f"Mechanics: {mechanical_result}")
        else:
            self.game_state.game_history.add_dialogue(player_character.name, command)
            output_log.append(f"{player_character.name}: \"{command}\"")
            
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        
        npc_logs = self._process_npc_turns()
        output_log.extend(npc_logs)
        
        next_player_character = self.turn_order[self.current_turn_index]
        output_log.append(f"\nIt's now {next_player_character.name}'s turn. What do you do?")
        
        return "\n".join(output_log)

    def get_initiative_order(self):
        """Returns a formatted string of the current initiative order."""
        if not self.turn_order:
            return "Initiative has not been rolled yet."

        initiative_lines = ["--- Initiative Order ---"]
        for i, character in enumerate(self.turn_order):
            turn_indicator = "--> " if i == self.current_turn_index else "    "
            line = f"{turn_indicator}{i+1}. {character.name}"
            initiative_lines.append(line)

        return "\n".join(initiative_lines)