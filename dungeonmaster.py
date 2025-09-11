# run_game.py
import tkinter as tk
from gui import GameGUI  # We will import the GUI we already made
from game_manager import GameManager # And the Game Manager we just created
import config # Assuming you still have your API key in config.py

def main():
    """Initializes and runs the game application."""

    # --- LLM Configuration ---
    # This is taken from your original dungeonmaster.py
    llm_config = {
        "url": "http://localhost:1234/v1/chat/completions",
        "headers": {"Content-Type": "application/json"},
        "model": "local-model/gemma-3-12b",
        "tools": [
            {   "type": "function", "function": {
                    "name": "execute_skill_check", "description": "Use a non-magical skill on an object or another character.",
                    "parameters": {"type": "object", "properties": {
                        "skill": {"type": "string", "description": "The name of the skill being used."},
                        "target": {"type": "string", "description": "The target of the skill."}
                        },
                        "required": ["skill", "target"]
                    }
                }
            }
        ]
    }
    
    # Initialize the Game Manager
    try:
        game_manager = GameManager(llm_config)
    except Exception as e:
        print(f"Failed to initialize game manager: {e}")
        return

    # Initialize the Tkinter window and the GUI
    root = tk.Tk()
    # Pass the game_manager instance to the GUI
    app = GameGUI(root, game_manager) 
    root.mainloop()

if __name__ == "__main__":
    main()