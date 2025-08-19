# d6_rules.py
import random

# A list of skills that are primarily used for combat and can cause damage.
COMBAT_SKILLS = ["melee", "missiles", "throwing"]

# This dictionary maps each skill to its governing attribute.
# This is crucial for determining the total number of dice to roll for a skill check.
D6_SKILLS_BY_ATTRIBUTE = {
    "physique": [
        "athletics", "melee", "throwing", "fortitude", "strength"
    ],
    "dexterity": [
        "acrobatics", "escape", "fly", "trickery", "stealth", "dodge", "reflexes", "missiles"
    ],
    "intelligence": [
        "appraise", "linguistics", "spellcraft", "navigation", "technology", "law", "business", "cultures"
    ],
    "wisdom": [
        "medicine", "survival", "willpower", "miracles", "artistry", "forgery", "gambling", "streetwise", "observation"
    ],
    "presence": [
        "charisma", "deception", "disguise", "husbandry", "intimidation", "psionics"
    ],
}

# This dictionary defines which skills can be used to oppose another skill check.
OPPOSED_SKILLS = {
    # --- Agility Skills ---
    "deception": ["observation"],
    "melee": ["melee", "dodge"],
    "throwing": ["dodge"],
    "missiles": ["dodge"]
}


# --- D6 Dice Mechanics ---
def roll_d6_dice(pips_to_roll):
    """Rolls a number of d6s based on pips."""
    pips_to_roll = max(0, int(pips_to_roll))
    num_dice, pips_modifier = divmod(pips_to_roll, 3)

    if num_dice <= 0:
        return pips_modifier

    rolls = [random.randint(1, 6) for _ in range(num_dice)]
    total = sum(rolls) + pips_modifier

    return total

def roll_d6_check(base_trait_pips, difficulty_number, situational_pips_modifier=0):
    """Performs a standard D6 skill check against a difficulty number."""
    effective_pips = max(0, base_trait_pips + situational_pips_modifier)

    roll_total, = roll_d6_dice(effective_pips)
    if roll_total >= difficulty_number:
        success_level = 1 + (roll_total - difficulty_number) // 5
    else:
        success_level = 0

    return success_level, roll_total
