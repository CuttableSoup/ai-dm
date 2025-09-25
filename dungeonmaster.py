import tkinter as tk
from gui import GameGUI
from game_manager import GameManager
import config

def main():
    """Initializes and runs the game application."""

    llm_config = {}
    tools = [
        {   "type": "function", "function": {
                "name": "execute_skill_check", "description": "Use a non-magical skill on an object or another character.",
                "parameters": {"type": "object", "properties": {
                    "skill": {"type": "string", "description": "The name of the skill being used."},
                    "target": {"type": "string", "description": "The target of the skill (an object or character name)."}
                    },
                    "required": ["skill", "target"]
                }
            }
        },
        {   "type": "function", "function": {
                "name": "manage_item", "description": "Manage an item. Use for equipping, unequipping, using, moving (giving to another character), creating, or destroying items.",
                "parameters": {"type": "object", "properties": {
                    "action": {"type": "string", "description": "The action to perform.", "enum": ["equip", "unequip", "use", "move", "create", "destroy"]},
                    "item_name": {"type": "string", "description": "The name of the item."},
                    "quantity": {"type": "integer", "description": "Optional. The number of items. Defaults to 1."},
                    "target_name": {"type": "string", "description": "Optional. The name of the character to move the item to."}
                    },
                    "required": ["action", "item_name"]
                }
            }
        },
        {   "type": "function", "function": {
                "name": "manage_party_member", "description": "Add or remove a character from the player's party.",
                "parameters": {"type": "object", "properties": {
                    "action": {"type": "string", "description": "The action to perform.", "enum": ["add", "remove"]},
                    "member_name": {"type": "string", "description": "The name of the character to add or remove."}
                    },
                    "required": ["action", "member_name"]
                }
            }
        },
        {   "type": "function", "function": {
                "name": "move_party", "description": "Move the entire party to an adjacent, connected zone.",
                "parameters": {"type": "object", "properties": {
                    "destination_zone": {"type": "string", "description": "The name of the zone to move to (must be an exit from the current zone)."}
                    },
                    "required": ["destination_zone"]
                }
            }
        },
        {   "type": "function", "function": {
                "name": "dialogue", "description": "Character is primarily speaking",
                "parameters": {"type": "object", "properties": {
                    "target": {"type": "string", "description": "The item or person being spoken to."}
                    },
                    "required": ["target"]
                }
            }
        }
    ]

    if config.USE_OPENROUTER_MODEL:
        # Configuration for online model via OpenRouter
        llm_config = {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            },
            "model": "x-ai/grok-4-fast:free", # Example online model
            "tools": tools
        }
    else:
        # Configuration for local offline model
        llm_config = {
            "url": "http://localhost:1234/v1/chat/completions",
            "headers": {"Content-Type": "application/json"},
            "model": "local-model/gemma-3-12b",
            "tools": tools
        }
    
    try:
        game_manager = GameManager(llm_config)
    except Exception as e:
        print(f"Failed to initialize game manager: {e}")
        return

    root = tk.Tk()
    app = GameGUI(root, game_manager) 
    root.mainloop()

if __name__ == "__main__":
    main()