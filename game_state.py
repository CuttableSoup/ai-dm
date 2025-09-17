# game_state.py
from classes import Environment, GameHistory, Party

class GameState:
    """
    A container for all the core components of the game world state.
    This makes it easier to pass the game state around without having
    functions with dozens of arguments.
    """
    def __init__(self, environment: Environment, party: Party, game_history: GameHistory):
        self.environment = environment
        self.party = party
        self.game_history = game_history
        
        # We can derive players and actors directly from the environment
        self.players = environment.players
        self.actors = environment.actors
        self.llm_log = []

    def find_actor_by_name(self, name: str):
        """Utility function to find any actor (player or NPC) by name."""
        name_lower = name.lower()
        for p in self.players:
            if p.name.lower() == name_lower:
                return p
        for a in self.actors:
            if a.name.lower() == name_lower:
                return a
        return None