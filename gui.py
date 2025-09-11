# gui.py
import tkinter as tk
from tkinter import scrolledtext, Frame, Entry, Button, Menu

class GameGUI:
    """A simple graphical user interface for a text-based game."""

    def __init__(self, root, game_manager):
        """
        Initializes the GUI, setting up the window and all its widgets.
        Args:
            root (tk.Tk): The main window object for the application.
            game_manager (GameManager): The game logic and state manager.
        """
        self.root = root
        self.game_manager = game_manager # Add this line
        self.root.title("Dungeon Master AI")
        self.root.geometry("800x600") # Set a default size

        self._create_menu()
        self._create_widgets()

    def _create_menu(self):
        """Creates the main menu bar for the application."""
        self.menu_bar = Menu(self.root)
        self.root.config(menu=self.menu_bar)

        # File Menu
        file_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Game", command=self.new_game) # Placeholder
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

    def _create_widgets(self):
        """Creates and arranges all the widgets in the main window."""
        
        # --- Create a top frame for the output text box ---
        # Using a Frame helps organize widget layout
        output_frame = Frame(self.root, bd=1, relief=tk.SUNKEN)
        output_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Output text box (read-only)
        self.output_text = scrolledtext.ScrolledText(
            output_frame, 
            wrap=tk.WORD, 
            state='disabled', # Start as read-only
            font=("Arial", 10)
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        # --- Create a bottom frame for input widgets ---
        input_frame = Frame(self.root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        # Input text entry
        self.input_entry = Entry(input_frame, font=("Arial", 11))
        # The '<Return>' event is triggered when the user presses the Enter key
        self.input_entry.bind("<Return>", self.process_input)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        # Send button
        self.send_button = Button(input_frame, text="Send", command=self.process_input)
        self.send_button.pack(side=tk.RIGHT, padx=(5, 0))

    def process_input(self, event=None):
        """
        Processes the user's input from the entry widget.
        'event=None' is needed to handle calls from both the button and the Enter key.
        """
        user_input = self.input_entry.get()
        
        if not user_input.strip():
            return

        self.input_entry.delete(0, tk.END)
        self.add_output(f"> {user_input}\n")

        # --- INTEGRATION POINT ---
        # Call the game manager to process the command
        game_response = self.game_manager.process_player_command(user_input)
        self.add_output(f"{game_response}\n\n")

    def add_output(self, text):
        """
        Adds text to the output window, ensuring it's scrolled to the end.
        Args:
            text (str): The text to be added to the output box.
        """
        # Set state to normal to allow text insertion
        self.output_text.config(state='normal')
        self.output_text.insert(tk.END, text)
        # Set state back to disabled to make it read-only for the user
        self.output_text.config(state='disabled')
        # Scroll to the bottom to see the new text
        self.output_text.see(tk.END)

    def new_game(self):
        """Starts a new game by clearing the screen and calling the game manager."""
        self.output_text.config(state='normal')
        self.output_text.delete('1.0', tk.END) # Clear the screen
        
        # Call the game manager's start function
        initial_text = self.game_manager.start_game()
        self.add_output(initial_text + "\n")


if __name__ == "__main__":
    # This block runs when the script is executed directly
    main_window = tk.Tk()
    app = GameGUI(main_window)
    main_window.mainloop()