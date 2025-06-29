import random
import json

def generate_procedural_room(num_zones=8, connectivity=0.2):
    """
    Generates a procedural room layout as a dictionary of zones.

    Args:
        num_zones (int): The total number of zones to create in the room.
        connectivity (float): A factor from 0.0 to 1.0 for how many extra paths to add.
                                0.0 is a simple tree, 1.0 is highly connected.

    Returns:
        dict: A dictionary representing the room's zone layout, ready for JSON.
    """
    if num_zones < 2:
        return {"1": {"name": "Single Zone", "description": "A small, simple area.", "adjacent_zones": []}}

    # --- Step 1: Grow the Room (guarantees all zones are connected) ---
    # This part of the algorithm creates a "spanning tree" to ensure that every
    # zone is reachable from every other zone. It prevents orphaned, unreachable areas.
    zones = {1: {"adjacent_zones": []}}
    all_created_zones = [1]

    for i in range(2, num_zones + 1):
        # Pick a random existing zone to branch off from
        parent_zone = random.choice(all_created_zones)
        
        # Add the new zone and connect it to its parent. This is a two-way street,
        # so the parent needs to know about the new child, and the child needs
        # to know about the parent.
        zones[i] = {"adjacent_zones": [parent_zone]}
        zones[parent_zone]["adjacent_zones"].append(i)
        all_created_zones.append(i)

    # --- Step 2: Add Extra Connections for complexity ---
    # This step turns the simple "tree" structure into a more complex "graph"
    # by adding loops and shortcuts. This makes rooms feel more realistic and less
    # like a simple series of corridors.
    # First, calculate the maximum possible number of extra connections.
    max_extra_connections = (num_zones * (num_zones - 1) / 2) - (num_zones - 1)
    num_extra_connections = int(max_extra_connections * connectivity)

    for _ in range(num_extra_connections):
        try:
            # Pick two random, distinct zones.
            zone_a, zone_b = random.sample(all_created_zones, 2)
            # Make sure they aren't already connected to avoid redundant links.
            if zone_b not in zones[zone_a]["adjacent_zones"]:
                zones[zone_a]["adjacent_zones"].append(zone_b)
                zones[zone_b]["adjacent_zones"].append(zone_a)
        except ValueError:
            # This try/except block handles cases where the room is too small
            # or already too connected to find a valid pair of non-adjacent zones.
            break

    # --- Step 3: Flesh out details ---
    # After the logical structure is built, populate the descriptive fields.
    for zone_id, zone_data in zones.items():
        # Give a generic name and description that can be replaced later.
        zone_data["name"] = f"Area {zone_id}"
        zone_data["description"] = "A procedurally generated area."
        # Sort adjacent zones to make the output cleaner and more predictable.
        zone_data["adjacent_zones"].sort()

    return zones

# --- Example Usage ---
# This block demonstrates how to use the function and will only run when
# the script is executed directly (not when imported as a module).
if __name__ == "__main__":
    # Generate a room with 10 zones and medium connectivity
    new_room_layout = generate_procedural_room(num_zones=10, connectivity=0.3)
    
    # Print it as a formatted JSON string for easy reading.
    print("--- Generated Room Layout ---")
    print(json.dumps(new_room_layout, indent=4))

    # Generate a simple, corridor-like room with no extra connections.
    corridor_layout = generate_procedural_room(num_zones=5, connectivity=0.0)
    print("\n--- Corridor-like Layout (connectivity=0.0) ---")
    print(json.dumps(corridor_layout, indent=4))
