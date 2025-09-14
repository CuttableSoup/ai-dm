# classes.py
from collections import deque
from d6_rules import D6_SKILLS_BY_ATTRIBUTE

output_log = []
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
        # Use setattr to dynamically assign attributes from the object's data dictionary
        for key, value in object_data.items():
            setattr(self, key, value)
        # Store location for easy reference
        self.location = {'room_id': room_id, 'zone': zone_id}

class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, scenario_data, all_items, players_data, actors_data, load_character_sheet_func):
        self.rooms = {room['room_id']: room for room in scenario_data.get('environment', {}).get('rooms', [])}
        self.doors = {door['door_id']: door for door in scenario_data.get('environment', {}).get('doors', [])}
        self.all_items = {item['name'].lower(): item for item in all_items}
        
        self.objects = [] # A list to hold all Object instances
        self.actors = []  # A list to hold all Actor instances
        self.players = [] # A list to hold player-controlled Actor instances

        # --- Instantiate Objects ---
        for room in self.rooms.values():
            # Instantiate objects defined globally in the room
            for obj_data in room.get('objects', []):
                self.objects.append(Object(obj_data, room['room_id']))
            # Instantiate objects defined within specific zones
            for zone_data in room.get('zones', []):
                for obj_data in zone_data.get('objects', []):
                    self.objects.append(Object(obj_data, room['room_id'], zone_data.get('zone')))

        # --- Instantiate Players ---
        for player_data in players_data:
            sheet_path = player_data['sheet']
            char_sheet = load_character_sheet_func(sheet_path)
            if char_sheet:
                player_actor = Actor(char_sheet, player_data['location'])
                player_actor.is_player = True
                self.players.append(player_actor)
            else:
                print(f"Warning: Could not load player character sheet: {sheet_path}")

        # --- Instantiate NPCs ---
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

    def take_damage(self, damage):
        self.cur_hp -= damage
        if self.cur_hp < 0:
            self.cur_hp = 0
        return f"{self.name} took {damage} damage and now has {self.cur_hp} HP."

    def heal_damage(self, healing):
        self.cur_hp += healing
        if self.cur_hp > self.max_hp:
            self.cur_hp = self.max_hp
        return f"{self.name} healed {healing} HP and now has {self.cur_hp} HP."

class GameHistory:
    """Records the past few actions and dialogues in the game."""
    def __init__(self, max_entries=5):
        self.history = deque(maxlen=max_entries)

    def add_action(self, actor_name, action_description):
        self.history.append(f"ACTION: {actor_name} - {action_description}")

    def add_dialogue(self, actor_name, dialogue_text):
        self.history.append(f"DIALOGUE: {actor_name}: \"{dialogue_text}\"")

    def get_history_string(self):
        if not self.history:
            return "No recent history."
        return "\n".join(list(self.history))

class Party:
    """Manages a group of player characters."""
    def __init__(self, name="The Adventurers"):
        self.name = name
        self.members = []
        self.reputation = {}  # Tracks reputation with different factions
        self.inventory = []   # A shared party inventory
        self.active_effects = []

    def add_member(self, character):
        """Adds a character to the party."""
        output_log = []
        if character not in self.members:
            self.members.append(character)
            output_log.append(f"{character.name} has joined the party '{self.name}'.")

    def remove_member(self, character):
        """Removes a character from the party."""
        if character in self.members:
            self.members.remove(character)
            output_log.append(f"{character.name} has left the party '{self.name}'.")

    def get_party_members(self):
        """Returns a list of all current party members."""
        return self.members

    def get_party_status(self):
        """Returns a string describing the status of all party members."""
        if not self.members:
            return "The party is empty."
        
        status_lines = [f"{member.name} (HP: {member.cur_hp}/{member.max_hp})" for member in self.members]
        return "\n".join(status_lines)