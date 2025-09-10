# game_classes.py
from collections import deque
from d6_rules import D6_SKILLS_BY_ATTRIBUTE

class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, scenario_data, all_items, all_spells):
        self.rooms = {room['room_id']: room for room in scenario_data.get('environment', {}).get('rooms', [])}
        self.doors = {door['door_id']: door for door in scenario_data.get('environment', {}).get('doors', [])}
        self.all_items = {item['name'].lower(): item for item in all_items} # Store items by lowercased name for easy lookup
        self.all_spells = all_spells
        self.actors = []  # A list to hold all Actor objects in the environment

    def add_actor(self, actor):
        """Adds an actor to the environment's list of actors."""
        if actor not in self.actors:
            self.actors.append(actor)

    def get_actors_in_room(self, room_id):
        """Returns a list of actors in a specific room."""
        return [actor for actor in self.actors if actor.location['room_id'] == room_id]

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
        room = self.get_room_by_id(room_id)
        if room:
            for zone_data in room.get('zones', []):
                for obj in zone_data.get('objects', []):
                    if obj['name'].lower() == object_name.lower():
                        return obj
            for obj in room.get('objects', []):
                if obj['name'].lower() == object_name.lower():
                    return obj
        return None

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
        return self.all_spells.get(spell_name.lower())

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

    def add_member(self, character):
        """Adds a character to the party."""
        if character not in self.members:
            self.members.append(character)
            print(f"{character.name} has joined the party '{self.name}'.")

    def remove_member(self, character):
        """Removes a character from the party."""
        if character in self.members:
            self.members.remove(character)
            print(f"{character.name} has left the party '{self.name}'.")

    def get_party_members(self):
        """Returns a list of all current party members."""
        return self.members

    def get_party_status(self):
        """Returns a string describing the status of all party members."""
        if not self.members:
            return "The party is empty."
        
        status_lines = [f"{member.name} (HP: {member.cur_hp}/{member.max_hp})" for member in self.members]
        return "\n".join(status_lines)