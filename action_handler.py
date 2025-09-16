# action_handler.py
import actions
from game_state import GameState

class ActionHandler:
    """
    This class is the central dispatcher for all game actions.
    It takes a function call from the LLM and executes the
    corresponding mechanical function from the actions.py module.
    """
    def __init__(self, game_state: GameState, llm_config: dict):
        self.game_state = game_state
        self.llm_config = llm_config

        # This dictionary maps the function names the LLM can call
        # to the actual Python functions in the actions module.
        self.function_map = {
            "execute_skill_check": actions.execute_skill_check,
            "manage_item": actions.manage_item,
            "manage_party_member": actions.manage_party_member,
            "move_party": actions.move_party,
            "cast_spell": actions.cast_spell,
        }

    def execute_action(self, actor, function_name: str, arguments: dict):
        """
        Executes a game action based on the function name and arguments.

        Returns:
            A string summarizing the mechanical result of the action.
        """
        if function_name not in self.function_map:
            error_msg = f"Error: The AI tried to call an unknown function '{function_name}'."
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg

        # Get the actual function from our map
        action_function = self.function_map[function_name]

        # Add the required game_state and actor to the arguments
        arguments['game_state'] = self.game_state
        arguments['actor'] = actor
        
        # Some functions require llm_config, so we add it if needed
        if function_name == "cast_spell":
            arguments['llm_config'] = self.llm_config

        try:
            # Call the function with the unpacked arguments dictionary
            mechanical_result = action_function(**arguments)
            
            # Log the action to game history
            # (You can make this more descriptive if you like)
            action_desc = f"executed {function_name} with arguments {arguments}."
            self.game_state.game_history.add_action(actor.name, action_desc)

            return mechanical_result
        except Exception as e:
            error_msg = f"Error executing function '{function_name}': {e}"
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg