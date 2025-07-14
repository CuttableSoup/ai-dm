import random

# Attitude statistics represent an NPC's disposition towards the players.
ATTITUDE_HELPFUL = "Helpful"
ATTITUDE_FRIENDLY = "Friendly"
ATTITUDE_INDIFFERENT = "Indifferent"
ATTITUDE_UNFRIENDLY = "Unfriendly"
ATTITUDE_HOSTILE = "Hostile"

# A list of skills that are primarily used for combat and can cause damage.
COMBAT_SKILLS = ["Melee_Combat", "Brawling"]

# This dictionary maps each skill to its governing attribute.
# This is crucial for determining the total number of dice to roll for a skill check.
D6_SKILLS_BY_ATTRIBUTE = {
    "Physique": [
        "Brawling"
    ],
    "Agility": [
        "Dodge", "Melee_Combat"
    ],
    "Coordination": [
        
    ],
    "Intellect": [
        
    ],
    "Perception": [
        
    ],
    "Presence": [
        
    ],
}

# This dictionary defines which skills can be used to oppose another skill check.
OPPOSED_SKILLS = {
    # --- Agility Skills ---
    "Melee_Combat": ["Melee_Combat", "Dodge"],
}