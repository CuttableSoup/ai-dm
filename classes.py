from collections import deque
from d6_rules import D6_SKILLS_BY_ATTRIBUTE

class ActiveEffect:
    """Represents an ongoing spell or condition on a character."""
    def __init__(self, name, duration_text, target):
        self.name = name
        self.duration_text = duration_text
        self.target_name = target.name
    
    def __str__(self):
        return f"'{self.name}' on {self.target_name} (Duration: {self.duration_text})"

class Object:
    """Represents a static object in the game world."""
    def __init__(self, object_data, room_id, zone_id=None):
        self.source_data = object_data
        for key, value in object_data.items():
            setattr(self, key, value)
        self.location = {'room_id': room_id, 'zone': zone_id}

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
                self.objects.append(Object(obj_data, room['room_id']))
            for zone_data in room.get('zones', []):
                for obj_data in zone_data.get('objects', []):
                    self.objects.append(Object(obj_data, room['room_id'], zone_data.get('zone')))

        for player_data in players_data:
            sheet_path = player_data['sheet']
            char_sheet = load_character_sheet_func(sheet_path)
            if char_sheet:
                player_actor = Actor(char_sheet, player_data['location'])
                player_actor.is_player = True
                self.players.append(player_actor)
            else:
                print(f"Warning: Could not load player character sheet: {sheet_path}")

        for actor_data in actors_data:
            sheet_path = actor_data['sheet']
            char_sheet = load_character_sheet_func(sheet_path)
            if char_sheet:
                self.actors.append(Actor(char_sheet, actor_data['location']))
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
    
    def get_spell_details(self, spell_name):
        """Finds spell details from the game's loaded spells data."""
        all_spells = getattr(self, 'all_spells', {}) 
        return all_spells.get(spell_name.lower())

class Actor:
    """Represents an actor in the game."""
    def __init__(self, character_sheet_data, location):
        self.source_data = character_sheet_data
        for key, value in character_sheet_data.items():
            setattr(self, key, value)
        self.location = location
        self.is_player = False

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
        self.history = deque(maxlen=max_entries)

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

import actions
from classes import GameState

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
            "move_party": actions.move_party,
            "cast_spell": actions.cast_spell,
        }

    def execute_action(self, actor, function_name: str, arguments: dict):
        """
        Executes a game action based on the function name and arguments.

        Returns:
            A string summarizing the mechanical result of the action.
        """
        arguments['game_state'] = self.game_state
        arguments['actor'] = actor
        
        if function_name == "narration":
            return f"\n{actor.name} used narration"
        if function_name not in self.function_map:
            error_msg = f"\n Error: The AI tried to call an unknown function '{function_name}'."
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg

        action_function = self.function_map[function_name]
        
        if function_name == "cast_spell":
            arguments['llm_config'] = self.llm_config

        try:
            mechanical_result = action_function(**arguments)
            if mechanical_result:
                self.game_state.game_history.add_action(actor.name, mechanical_result)
            return mechanical_result
        except Exception as e:
            error_msg = f"Error executing function '{function_name}': {e}"
            self.game_state.game_history.add_action(actor.name, error_msg)
            return error_msg