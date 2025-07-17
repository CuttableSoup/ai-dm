# d6_rules.py

import random

# Attitude statistics represent an NPC's disposition towards the players.
ATTITUDE_HELPFUL = "helpful"
ATTITUDE_FRIENDLY = "friendly"
ATTITUDE_INDIFFERENT = "indifferent"
ATTITUDE_UNFRIENDLY = "unfriendly"
ATTITUDE_HOSTILE = "hostile"

# A list of skills that are primarily used for combat and can cause damage.
COMBAT_SKILLS = ["melee_combat", "brawling", "firearms", "missile_weapons", "gunnery", "throwing", "demolitions"]

# This dictionary maps each skill to its governing attribute.
# This is crucial for determining the total number of dice to roll for a skill check.
D6_SKILLS_BY_ATTRIBUTE = {
    "physique": [
        "climb_jump", "lifting", "running", "stamina", "swim"
    ],
    "agility": [
        "acrobatics", "brawling", "dodge", "flying", "melee_combat", "riding", "hide"
    ],
    "coordination": [
        "firearms", "gunnery", "lockpicking", "missile_weapons", "piloting", "sleight_of_hand", "throwing", "vehicle_operation"
    ],
    "intellect": [
        "aliens", "astrography", "bureaucracy", "business", "cultures", "demolitions", "languages",
        "medicine", "navigation", "scholar", "security", "tactics", "technology"
    ],
    "perception": [
        "artist", "forgery", "gambling", "investigation", "know_how", "repair_crafting", "search", "streetwise", "survival", "tracking"
    ],
    "presence": [
        "animal_handling", "charm", "command", "con", "disguise", "intimidation", "persuasion", "willpower"
    ],
}

# This dictionary defines which skills can be used to oppose another skill check.
OPPOSED_SKILLS = {
    # --- Agility Skills ---
    "brawling": ["brawling", "dodge"],
    "mlee_combat": ["melee_combat", "dodge"],
    # --- Coordination Skills ---
    "firearms": ["dodge"],
    "gGunnery": ["dodge"],
    "missile_weapons": ["dodge"],
    "sSleight_of_hand": ["search"],
    "throwing": ["dodge", "throwing"],
    # --- Intellect Skills ---
    "security": ["security", "technology"],
    # --- Perception Skills ---
    "forgery": ["forgery", "investigation"],
    "hide": ["search", "investigation", "tracking"],
    # --- Presence Skills ---
    "charm": ["willpower"],
    "con": ["willpower", "investigation", "streetwise"],
    "Intimidation": ["willpower"],
    "persuasion": ["willpower", "con"],
}

# Provides descriptive words for different levels of an attribute score.
ATTRIBUTE_DESCRIPTORS = {
    "physique": {
            1: "frail",
            2: "weak",
            3: "standard",
            4: "strong",
            5: "herculean"
        },
    "agility": {
            1: "clumsy",
            2: "awkward",
            3: "ordinary",
            4: "agile",
            5: "nimble"
        },
    "coordination": {
            1: "uncoordinated",
            2: "clumsy",
            3: "typical",
            4: "coordinated",
            5: "precise"
        },
    "intellect": {
            1: "stupid",
            2: "unintelligent",
            3: "normal",
            4: "intelligent",
            5: "genius"
        },
    "perception": {
            1: "oblivious",
            2: "unobservant",
            3: "fair",
            4: "perceptive",
            5: "insightful"
        },
    "presence": {
            1: "uncharismatic",
            2: "shy",
            3: "unremarkable",
            4: "charismatic",
            5: "commanding"
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