import collections
from d6_rules import *
from game_state import game_state

class Environment:
    """Manages the game world's rooms, objects, and exits."""
    def __init__(self, environment_data):
        self.rooms = environment_data.get("rooms", {})
        self.location = environment_data.get("location", "")

    def get_room(self, room_key):
        """Returns the data for a specific room."""
        return self.rooms.get(room_key)

class GameEntity:
    """Represents a character (player, NPC, object, etc) in the game."""
    def __init__(self, character_sheet_data, location):
        # Basic information
        self.source_data = character_sheet_data
        self.id = character_sheet_data.get("id")
        self.name = character_sheet_data.get("name")
        
        # Descriptive information
        self.qualities = character_sheet_data.get("qualities", {})
        self.languages = character_sheet_data.get("languages", [])
        self.memories = character_sheet_data.get("memories", [])
        self.statuses = character_sheet_data.get("statuses", [])

        # Personality and attitude
        personality_data = character_sheet_data.get("personality", "neutral")
        if isinstance(personality_data, list) and personality_data:
            self.personality = personality_data[0]
        else:
            self.personality = personality_data

        attitude_data = character_sheet_data.get("attitudes", [])
        default_attitude = ATTITUDE_INDIFFERENT
        if isinstance(attitude_data, list) and attitude_data:
            default_attitude_entry = next((att for att in attitude_data if "default" in att), None)
            if default_attitude_entry:
                default_attitude = default_attitude_entry.get("default", ATTITUDE_INDIFFERENT)
        self.attitude = default_attitude
        
        # Game mechanics data
        self.experience = character_sheet_data.get("experience", 0)
        self.allies = character_sheet_data.get("allies", "none")
        
        # Attributes, skills, and equipment
        self.attributes = {k.lower(): v for k, v in character_sheet_data.get("attributes", {}).items()}
        self.skills = {k.lower(): v for k, v in character_sheet_data.get("skills", {}).items()}
        self.equipment = character_sheet_data.get("equipment", [])
        self.inventory = character_sheet_data.get("inventory", [])

        # Spells
        self.spells = character_sheet_data.get("spells", [])
        
        # Combat-related stats
        self.max_hitpoints = character_sheet_data.get("hitpoints", 30)
        self.current_hitpoints = self.max_hitpoints
        self.initiative_roll = 0
        
        # Location is a dictionary including room and zone
        self.current_room = location.get("room")
        self.current_zone = location.get("zone")

    def get_attribute_descriptors_string(self):
        """Creates a human-readable string of the character's attributes."""
        descriptors = []
        for attr, pips in self.attributes.items():
            descriptor = get_attribute_descriptor(attr, pips)
            if descriptor and descriptor != "Average":
                descriptors.append(f"{attr.capitalize()}: {descriptor}")
        return ", ".join(descriptors) if descriptors else "Average"

    def get_status_summary(self):
        """Provides a quick summary of the character's current state, including location."""
        # Status summary now includes zone
        base_summary = f"{self.name} (Status: {self.get_hitpoint_status()}, Room: {self.current_room}, Zone: {self.current_zone})"
        return base_summary

    def get_hitpoint_status(self):
        """Returns the character's current health status as a string based on hitpoints."""
        hp_percentage = (self.current_hitpoints / self.max_hitpoints) * 100

        if hp_percentage >= 75:
            return "Healthy"
        elif hp_percentage >= 50:
            return "Wounded"
        elif hp_percentage >= 25:
            return "Severely Wounded"
        elif hp_percentage > 0:
            return "Near Death"
        else:
            return "Incapacitated"

    def get_hitpoint_penalty_pips(self):
        """Returns the penalty (in pips) based on current hitpoints."""
        hp_percentage = (self.current_hitpoints / self.max_hitpoints) * 100
        if hp_percentage <= 25:
            return 6  # Significant penalty for low health
        elif hp_percentage <= 50:
            return 3  # Moderate penalty
        return 0

    

    def apply_damage(self, damage_roll_total, resistance_roll_total):
        """Calculates and applies damage to the character based on hitpoints."""
        if self.current_hitpoints <= 0:
            return f"{self.name} is already incapacitated."
            
        outcome = f"Damage roll: {damage_roll_total} vs Resistance roll: {resistance_roll_total}. "
        if damage_roll_total <= resistance_roll_total:
            outcome += f"{self.name} resists the damage."
            return outcome

        damage_taken = damage_roll_total - resistance_roll_total
        self.current_hitpoints -= damage_taken
        self.current_hitpoints = max(0, self.current_hitpoints) # Ensure hitpoints don't go below 0

        outcome += f"{self.name} takes {damage_taken} damage and is now {self.get_hitpoint_status()} ({self.current_hitpoints}/{self.max_hitpoints} HP)!"
        return outcome

    def is_incapacitated(self):
        """Checks if the character is unable to take actions."""
        return self.current_hitpoints <= 0

    def get_attribute_or_skill_pips(self, trait_name):
        """Gets the total number of pips for a given attribute or skill."""
        trait_name_lower = trait_name.lower()
        governing_attribute_name = next((k.lower() for k, v in D6_SKILLS_BY_ATTRIBUTE.items() if trait_name_lower in [s.lower() for s in v]), None)
        
        if governing_attribute_name:
            return self.skills.get(trait_name_lower, 0) + self.attributes.get(governing_attribute_name, 0)
            
        if trait_name_lower in self.attributes:
            return self.attributes[trait_name_lower]
            
        # if DEBUG: print(f"[WARN] Trait '{trait_name}' not found for {self.name}. Returning 0 pips.")
        return 0

    def get_resistance_pips(self):
        """Gets the pips used for resisting damage, usually based on Physique."""
        return self.attributes.get("physique", 0)

    def get_weapon_details(self, weapon_name_or_type="melee"):
        """Finds a weapon in the character's equipment."""
        for item in self.equipment:
            if item.get("type", "").lower() == "weapon":
                return item # Return the first equipped weapon
        
        # Default unarmed strike now includes range
        return {"name": "Unarmed", "skill": "brawling", "damage": self.attributes.get("physique", 6), "range": 0}

def get_zone_distance(start_zone, end_zone, room_key):
    """
    Calculates the shortest distance in zones between a start and end zone using BFS.
    This is the core of the range system.
    """
    if start_zone == end_zone:
        return 0

    room_data = game_state["environment"].get_room(room_key)
    if not room_data or not isinstance(room_data.get("zones"), dict):
        return -1 # Invalid room data, cannot calculate distance

    layout = room_data["zones"]
    
    # A queue for our search, storing (zone_id, distance_from_start)
    queue = collections.deque([(start_zone, 0)])
    # A set to keep track of zones we've already visited to avoid loops
    visited = {start_zone}

    while queue:
        current_zone, distance = queue.popleft()

        # Get adjacent zones from the layout. Keys are strings in JSON.
        adjacent_zones = layout.get(str(current_zone), {}).get("adjacent_zones", [])

        for neighbor in adjacent_zones:
            # If we found the target, return the distance traveled.
            if neighbor == end_zone:
                return distance + 1
            
            # If we haven't visited this neighbor yet, add it to the queue.
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    
    return -1 # Target was not found/unreachable
