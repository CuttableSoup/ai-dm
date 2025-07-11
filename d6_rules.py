import random

# Attitude statistics represent an NPC's disposition towards the players.
ATTITUDE_HELPFUL = "Helpful"
ATTITUDE_FRIENDLY = "Friendly"
ATTITUDE_INDIFFERENT = "Indifferent"
ATTITUDE_UNFRIENDLY = "Unfriendly"
ATTITUDE_HOSTILE = "Hostile"

# A list of skills that are primarily used for combat and can cause damage.
COMBAT_SKILLS = ["Melee_Combat", "Brawling", "Firearms", "Missile_Weapons", "Gunnery", "Throwing", "Demolitions"]

# This dictionary maps each skill to its governing attribute.
# This is crucial for determining the total number of dice to roll for a skill check.
D6_SKILLS_BY_ATTRIBUTE = {
    "Physique": [
        "Climb_Jump", "Lifting", "Running", "Stamina", "Swim"
    ],
    "Agility": [
        "Acrobatics", "Brawling", "Dodge", "Flying", "Melee_Combat", "Riding", "Hide"
    ],
    "Coordination": [
        "Firearms", "Gunnery", "Lockpicking", "Missile_Weapons", "Piloting", "Sleight_of_Hand", "Throwing", "Vehicle_Operation"
    ],
    "Intellect": [
        "Aliens", "Astrography", "Bureaucracy", "Business", "Cultures", "Demolitions", "Languages",
        "Medicine", "Navigation", "Scholar", "Security", "Tactics", "Technology"
    ],
    "Perception": [
        "Artist", "Forgery", "Gambling", "Investigation", "Know_How", "Repair_Crafting", "Search", "Streetwise", "Survival", "Tracking"
    ],
    "Presence": [
        "Animal_Handling", "Charm", "Command", "Con", "Disguise", "Intimidation", "Persuasion", "Willpower"
    ],
}

# This dictionary defines which skills can be used to oppose another skill check.
OPPOSED_SKILLS = {
    # --- Agility Skills ---
    "Brawling": ["Brawling", "Dodge"],
    "Melee_Combat": ["Melee_Combat", "Dodge"],
    # --- Coordination Skills ---
    "Firearms": ["Dodge"],
    "Gunnery": ["Dodge"],
    "Missile_Weapons": ["Dodge"],
    "Sleight_of_Hand": ["Search"],
    "Throwing": ["Dodge", "Throwing"],
    # --- Intellect Skills ---
    "Security": ["Security", "Technology"],
    # --- Perception Skills ---
    "Forgery": ["Forgery", "Investigation"],
    "Hide": ["Search", "Investigation", "Tracking"],
    # --- Presence Skills ---
    "Charm": ["Willpower"],
    "Con": ["Willpower", "Investigation", "Streetwise"],
    "Intimidation": ["Willpower"],
    "Persuasion": ["Willpower", "Con"],
}

# Provides descriptive words for different levels of an attribute score.
ATTRIBUTE_DESCRIPTORS = {
    "Physique": {
            1: "Frail",
            2: "Weak",
            3: "Standard",
            4: "Strong",
            5: "Herculean"
        },
    "Agility": {
            1: "Clumsy",
            2: "Awkward",
            3: "Ordinary",
            4: "Agile",
            5: "Nimble"
        },
    "Coordination": {
            1: "Uncoordinated",
            2: "Clumsy",
            3: "Typical",
            4: "Coordinated",
            5: "Precise"
        },
    "Intellect": {
            1: "Stupid",
            2: "Unintelligent",
            3: "Normal",
            4: "Intelligent",
            5: "Genius"
        },
    "Perception": {
            1: "Oblivious",
            2: "Unobservant",
            3: "Fair",
            4: "Perceptive",
            5: "Insightful"
        },
    "Presence": {
            1: "Uncharismatic",
            2: "Shy",
            3: "Unremarkable",
            4: "Charismatic",
            5: "Commanding"
        }
}

def get_attribute_descriptor(attribute_name, pips):
    """Gets the descriptive adjective for an attribute value."""
    attribute_name = attribute_name.capitalize()
    dice = pips // 3
    if dice <= 1:
        level = 1
    elif dice == 2:
        level = 2
    elif dice == 3:
        level = 3
    elif dice == 4:
        level = 4
    else: # 5 or more
        level = 5
    return ATTRIBUTE_DESCRIPTORS.get(attribute_name, {}).get(level, "")

# --- D6 Dice Mechanics ---

def roll_d6_dice(total_pips_to_roll):
    """Rolls a number of d6s based on pips."""
    total_pips_to_roll = max(0, int(total_pips_to_roll))
    num_dice, pips_modifier = divmod(total_pips_to_roll, 3)

    if num_dice <= 0:
        return pips_modifier, f"No dice + {pips_modifier} pips = {pips_modifier}"

    rolls = [random.randint(1, 6) for _ in range(num_dice)]
    final_total = sum(rolls) + pips_modifier

    roll_details_list = [str(r) for r in rolls]
    roll_details_str = (f"Rolls ({num_dice}D{'+'+str(pips_modifier) if pips_modifier else ''}): "
                        f"[{', '.join(roll_details_list)}] + {pips_modifier} = {final_total}")

    return final_total, roll_details_str

def roll_d6_check(actor, base_trait_pips, difficulty_number, situational_pips_modifier=0):
    """Performs a standard D6 skill check against a difficulty number."""
    hitpoint_penalty_pips = actor.get_hitpoint_penalty_pips()
    effective_pips = max(0, base_trait_pips - hitpoint_penalty_pips + situational_pips_modifier)

    roll_total, roll_details = roll_d6_dice(effective_pips)

    details_str = f"{roll_details} vs DN {difficulty_number}."
    if roll_total >= difficulty_number:
        success_level = 1 + (roll_total - difficulty_number) // 5
        details_str += f" Success ({success_level -1} raise(s))!"
    else:
        success_level = 0
        details_str += " Failure."

    return success_level, roll_total, details_str