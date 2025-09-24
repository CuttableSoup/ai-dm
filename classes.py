import collections
from dataclasses import dataclass, field
from typing import Dict, List, Any
from d6_rules import D6_SKILLS_BY_ATTRIBUTE

@dataclass
class ActiveEffect:
    """Represents an ongoing spell or condition on a character."""
    name: str
    duration_text: str
    target_name: str

    def __str__(self):
        return f"'{self.name}' on {self.target_name} (Duration: {self.duration_text})"
    
@dataclass
class InventoryItem:
    """Represents a single item in an actor's inventory."""
    item: str
    quantity: int
    equipped: bool = False

@dataclass
class Object:
    """Represents a static object in the game world."""
    name: str
    description: str
    location: Dict[str, Any]
    source_data: Dict[str, Any]
    
    is_interactive: bool = field(default=False)
    max_hp: int = field(default=0)
    cur_hp: int = field(default=0)

    def __post_init__(self):
        """Allows for additional setup after the dataclass __init__ runs."""
        for key, value in self.source_data.items():
            if not hasattr(self, key):
                setattr(self, key, value)

class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, scenario_data, all_items, players_data, actors_data, load_character_sheet_func):
        self.rooms = {room['room_id']: room for room in scenario_data.get('environment', {}).get('rooms', [])}
        self.doors = {door['door_id']: door for door in scenario_data.get('environment', {}).get('doors', [])}
        self.all_items = {item['name'].lower(): item for item in all_items}
        
        self.objects = []
        self.actors = []
        self.players = []

        for room in self.rooms.values():
            for obj_data in room.get('objects', []):
                initial_hp = obj_data.get('hp', 0)
                new_obj = Object(
                    name=obj_data.get('name', 'Unknown Object'),
                    description=obj_data.get('description', ''),
                    location={'room_id': room['room_id'], 'zone': None},
                    source_data=obj_data,
                    is_interactive=obj_data.get('is_interactive', False),
                    max_hp=initial_hp,
                    cur_hp=initial_hp
                )
                self.objects.append(new_obj)
            for zone_data in room.get('zones', []):
                for obj_data in zone_data.get('objects', []):
                    initial_hp = obj_data.get('hp', 0)
                    new_obj = Object(
                        name=obj_data.get('name', 'Unknown Object'),
                        description=obj_data.get('description', ''),
                        location={'room_id': room['room_id'], 'zone': zone_data.get('zone')},
                        source_data=obj_data,
                        is_interactive=obj_data.get('is_interactive', False),
                        max_hp=initial_hp,
                        cur_hp=initial_hp
                    )
                    self.objects.append(new_obj)

        for player_data in players_data:
            sheet_path = player_data['sheet']
            char_sheet = load_character_sheet_func(sheet_path)
            if char_sheet:
                if char_sheet.get('memories') is None:
                    char_sheet['memories'] = []
                
                player_actor = Actor(
                    **char_sheet, 
                    location=player_data['location'], 
                    source_data=char_sheet
                )
                player_actor.is_player = True
                self.players.append(player_actor)
            else:
                print(f"Warning: Could not load player character sheet: {sheet_path}")

        for actor_data in actors_data:
            sheet_path = actor_data['sheet']
            char_sheet = load_character_sheet_func(sheet_path)
            if char_sheet:
                if char_sheet.get('memories') is None:
                    char_sheet['memories'] = []

                new_actor = Actor(
                    **char_sheet,
                    location=actor_data['location'],
                    source_data=char_sheet
                )
                self.actors.append(new_actor)
            else:
                print(f"Warning: Could not load actor character sheet: {sheet_path}")

    def get_room_by_id(self, room_id):
        return self.rooms.get(room_id)

    def get_door_by_id(self, door_id):
        return self.doors.get(door_id)

    def get_current_room_data(self, actor_location):
        room = self.get_room_by_id(actor_location['room_id'])
        if not room:
            return None, None
        
        current_zone_data = None
        for zone_data in room.get('zones', []):
            if zone_data.get('zone') == actor_location['zone']:
                current_zone_data = zone_data
                break
        
        return room, current_zone_data

    def get_object_in_room(self, room_id, object_name):
        """Find an Object instance by name within a specific room."""
        object_name_lower = object_name.lower()
        for obj in self.objects:
            if obj.location['room_id'] == room_id and obj.name.lower() == object_name_lower:
                return obj
        return None
    
    def get_objects_in_zone(self, room_id, zone_id):
        """Returns a list of Object instances in a specific zone."""
        return [obj for obj in self.objects if obj.location['room_id'] == room_id and obj.location['zone'] == zone_id]


    def get_trap_in_room(self, room_id, zone_id):
        room = self.get_room_by_id(room_id)
        if room:
            for zone_data in room.get('zones', []):
                if zone_data.get('zone') == zone_id:
                    return zone_data.get('trap')
        return None

    def get_item_details(self, item_name):
        return self.all_items.get(item_name.lower())

@dataclass
class Actor:
    """Represents an actor in the game."""
    name: str
    max_hp: int
    cur_hp: int
    exp: int
    attributes: Dict[str, int]
    skills: Dict[str, int]
    inventory: List[InventoryItem]
    spells: List[str]
    allies: str
    attitudes: List[Dict[str, str]]
    statuses: List[str]
    personality: List[str]
    languages: List[str]
    qualities: Dict[str, Any]
    memories: List[str]

    location: Dict[str, Any] = field(default_factory=dict)
    source_data: Dict[str, Any] = field(default_factory=dict)
    is_player: bool = False
    
    description: str = ""
    quotes: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """
        Performs post-initialization setup.
        Converts inventory dictionaries into InventoryItem objects.
        """
        if self.inventory and isinstance(self.inventory[0], dict):
            self.inventory = [InventoryItem(**data) for data in self.inventory]

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill."""
        trait_name = trait_name.lower()
        
        if trait_name in self.attributes:
            return self.attributes[trait_name]

        if trait_name in self.skills:
            skill_pips = self.skills[trait_name]
            for attr, skill_list in D6_SKILLS_BY_ATTRIBUTE.items():
                if trait_name in skill_list:
                    return skill_pips + (self.attributes.get(attr, 0))
            return skill_pips

        return 0

class GameHistory:
    """Records the past few actions and dialogues in the game."""
    def __init__(self, max_entries=5):
        self.history = collections.deque(maxlen=max_entries)

    def add_action(self, actor_name, action_description):
        self.history.append(f"{actor_name} - {action_description}")

    def add_dialogue(self, actor_name, dialogue_text):
        self.history.append(f"{actor_name}: \"{dialogue_text}\"")

    def get_history_string(self):
        if not self.history:
            return "No recent history."
        return "\n".join(list(self.history))

class Party:
    """Manages a group of player characters."""
    def __init__(self, name="The Adventurers"):
        self.name = name
        self.members = []
        self.reputation = {}
        self.inventory = []
        self.active_effects = []

    def add_member(self, character):
        """Adds a character to the party."""
        if character not in self.members:
            self.members.append(character)

    def remove_member(self, character):
        """Removes a character from the party."""
        if character in self.members:
            self.members.remove(character)

    def get_party_members(self):
        """Returns a list of all current party members."""
        return self.members

    def get_party_status(self):
        """Returns a string describing the status of all party members."""
        if not self.members:
            return "The party is empty."
        
        status_lines = [f"{member.name} (HP: {member.cur_hp}/{member.max_hp})" for member in self.members]
        return "\n".join(status_lines)
    
@dataclass
class GameState:
    """A container for all the core components of the game world state."""
    environment: 'Environment'
    party: 'Party'
    game_history: 'GameHistory'
    players: List['Actor']
    actors: List['Actor']
    llm_log: list = field(default_factory=list)

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

import actions

class ActionHandler:
    """
    This class is the central dispatcher for all game actions.
    It takes a function call from the LLM and executes the
    corresponding mechanical function from the actions.py module.
    """
    def __init__(self, game_state: GameState, llm_config: dict):
        self.game_state = game_state
        self.llm_config = llm_config

        self.function_map = {
            "execute_skill_check": actions.execute_skill_check,
            "manage_item": actions.manage_item,
            "manage_party_member": actions.manage_party_member,
            "move_party": actions.move_party
        }

    def execute_action(self, actor, function_name: str, arguments: dict):
        """
        Executes a game action based on the function name and arguments.

        Returns:
            A string summarizing the mechanical result of the action.
        """
        arguments['game_state'] = self.game_state
        arguments['actor'] = actor
        
        if function_name == "dialogue":
            return f"\n{actor.name} used dialogue"
        if function_name not in self.function_map:
            error_msg = f"\n Error: The AI tried to call an unknown function '{function_name}'."
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg

        action_function = self.function_map[function_name]

        try:
            mechanical_result = action_function(**arguments)
            if mechanical_result:
                self.game_state.game_history.add_action(actor.name, mechanical_result)
            return mechanical_result
        except Exception as e:
            error_msg = f"Error executing function '{function_name}': {e}"
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg