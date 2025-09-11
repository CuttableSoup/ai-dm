# gui.py
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, Frame, Entry, Button, Menu, filedialog
import os
import ast

class GameGUI:
    """A simple graphical user interface for a text-based game."""

    def __init__(self, root, game_manager):
        self.root = root
        self.game_manager = game_manager
        self.root.title("Dungeon Master AI")
        self.root.geometry("800x600")

        self._create_menu()
        self._create_widgets()
        
        self.debug_win = None

    def _create_menu(self):
        """Creates the main menu bar for the application."""
        self.menu_bar = Menu(self.root)
        self.root.config(menu=self.menu_bar)

        file_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Game", command=self.new_game)
        file_menu.add_command(label="Save Game", command=self.save_game)
        file_menu.add_command(label="Load Game", command=self.load_game)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        debug_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Debug", menu=debug_menu)
        debug_menu.add_command(label="Game State Inspector", command=self.open_debug_window)

    def _create_widgets(self):
        output_frame = Frame(self.root, bd=1, relief=tk.SUNKEN)
        output_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text = scrolledtext.ScrolledText(
            output_frame, wrap=tk.WORD, state='disabled', font=("Arial", 10)
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        input_frame = Frame(self.root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        self.input_entry = Entry(input_frame, font=("Arial", 11))
        self.input_entry.bind("<Return>", self.process_input)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.send_button = Button(input_frame, text="Send", command=self.process_input)
        self.send_button.pack(side=tk.RIGHT, padx=(5, 0))

    def open_debug_window(self):
        if not self.game_manager.turn_order:
            self.add_output("Cannot open debug panel: Game has not started.\n")
            return
        if self.debug_win and self.debug_win.winfo_exists():
            self.debug_win.lift()
        else:
            self.debug_win = DebugWindow(self.root, self.game_manager)

    def process_input(self, event=None):
        """Processes user input and automatically refreshes the debug panel."""
        user_input = self.input_entry.get()
        if not user_input.strip(): return
        
        self.input_entry.delete(0, tk.END)
        self.add_output(f"> {user_input}\n")

        game_response = self.game_manager.process_player_command(user_input)
        self.add_output(f"{game_response}\n\n")

        # --- MODIFIED: Automatically refresh ALL debug tabs if the window is open ---
        if self.debug_win and self.debug_win.winfo_exists():
            self.debug_win.refresh_all_tabs()
        # --- END MODIFIED ---

    def add_output(self, text):
        self.output_text.config(state='normal')
        self.output_text.insert(tk.END, text)
        self.output_text.config(state='disabled')
        self.output_text.see(tk.END)

    def new_game(self):
        self.output_text.config(state='normal')
        self.output_text.delete('1.0', tk.END)
        initial_text = self.game_manager.start_game()
        self.add_output(initial_text + "\n")

    def save_game(self):
        if not self.game_manager or not self.game_manager.turn_order:
            self.add_output("Cannot save: The game has not started yet.\n")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".sav", filetypes=[("Save Files", "*.sav"), ("All Files", "*.*")], title="Save Game")
        if filepath:
            full_text_log = self.output_text.get('1.0', tk.END)
            self.game_manager.gui_text_log = full_text_log
            if self.game_manager.save_game(filepath):
                self.add_output(f"Game saved to {os.path.basename(filepath)}\n")
            else:
                self.add_output("Failed to save game.\n")

    def load_game(self):
        filepath = filedialog.askopenfilename(filetypes=[("Save Files", "*.sav"), ("All Files", "*.*")], title="Load Game")
        if not filepath: return
        loaded_game_manager = self.game_manager.__class__.load_game(filepath)
        if loaded_game_manager:
            self.game_manager = loaded_game_manager
            self.output_text.config(state='normal')
            self.output_text.delete('1.0', tk.END)
            if hasattr(self.game_manager, 'gui_text_log') and self.game_manager.gui_text_log:
                self.output_text.insert('1.0', self.game_manager.gui_text_log)
            self.output_text.insert(tk.END, f"\n--- Game Loaded from {os.path.basename(filepath)} ---\n")
            self.output_text.config(state='disabled')
            self.output_text.see(tk.END)
        else:
            self.add_output("Failed to load game.\n")


class DebugWindow(tk.Toplevel):
    """A Toplevel window for inspecting and modifying game state via tabs."""

    def __init__(self, master, game_manager):
        super().__init__(master)
        self.title("Game State Inspector")
        self.geometry("800x600")
        self.game_manager = game_manager

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_inspector = Frame(self.notebook)
        self.tab_history = Frame(self.notebook)
        self.tab_party = Frame(self.notebook)
        self.tab_environment = Frame(self.notebook)

        self.notebook.add(self.tab_inspector, text="Object Inspector")
        self.notebook.add(self.tab_history, text="Game History")
        self.notebook.add(self.tab_party, text="Party")
        self.notebook.add(self.tab_environment, text="Environment")
        
        self._create_inspector_tab()
        self._create_history_tab()
        self._create_party_tab()
        self._create_environment_tab()

    # --- NEW: Unified refresh method ---
    def refresh_all_tabs(self):
        """Refreshes the content of all tabs in the debug panel."""
        self.populate_entity_list()
        self.refresh_history_tab()
        self.refresh_party_tab()
        self.refresh_environment_tab()

    # --- Tab 1: Object Inspector (Refresh Button Removed) ---
    def _create_inspector_tab(self):
        self.displayed_entities, self.selected_entity, self.attribute_entries = [], None, {}
        paned_window = tk.PanedWindow(self.tab_inspector, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        left_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        self.entity_listbox = tk.Listbox(left_frame)
        self.entity_listbox.pack(fill=tk.BOTH, expand=True)
        self.entity_listbox.bind("<<ListboxSelect>>", self.show_entity_details)
        paned_window.add(left_frame, width=250)
        right_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        canvas = tk.Canvas(right_frame)
        scrollbar = tk.Scrollbar(right_frame, orient="vertical", command=canvas.yview)
        self.details_frame = Frame(canvas)
        self.details_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.details_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        paned_window.add(right_frame)
        Button(self.tab_inspector, text="Save Changes to Selected Entity", command=self.save_entity_details).pack(side=tk.BOTTOM, pady=5, fill=tk.X)
        self.populate_entity_list()

    def populate_entity_list(self):
        self.entity_listbox.delete(0, tk.END)
        self.displayed_entities.clear()
        current_actor = self.game_manager.turn_order[self.game_manager.current_turn_index]
        all_entities = self.game_manager.environment.players + self.game_manager.environment.actors + self.game_manager.environment.objects
        for entity in all_entities:
            if hasattr(entity, 'location') and entity.location == current_actor.location:
                self.displayed_entities.append(entity)
                self.entity_listbox.insert(tk.END, f"{entity.__class__.__name__}: {entity.name}")

    def show_entity_details(self, event=None):
        sel = self.entity_listbox.curselection()
        if not sel: return
        self.selected_entity = self.displayed_entities[sel[0]]
        for widget in self.details_frame.winfo_children(): widget.destroy()
        self.attribute_entries.clear()
        attrs = sorted([attr for attr in vars(self.selected_entity) if attr != 'source_data'])
        for i, attr_name in enumerate(attrs):
            value = getattr(self.selected_entity, attr_name)
            tk.Label(self.details_frame, text=attr_name).grid(row=i, column=0, sticky="w", padx=2, pady=2)
            entry = Entry(self.details_frame, width=60)
            entry.insert(0, str(value))
            entry.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
            self.attribute_entries[attr_name] = entry

    def save_entity_details(self):
        if not self.selected_entity: return
        for attr, entry in self.attribute_entries.items():
            val_str = entry.get()
            orig_val = getattr(self.selected_entity, attr)
            try:
                if isinstance(orig_val, bool): new_val = val_str.lower() in ('true', '1', 'yes')
                elif isinstance(orig_val, (list, dict)): new_val = ast.literal_eval(val_str)
                elif orig_val is None: new_val = val_str if val_str != 'None' else None
                else: new_val = type(orig_val)(val_str)
                setattr(self.selected_entity, attr, new_val)
            except Exception as e:
                print(f"Could not convert '{val_str}' for '{attr}'. Setting as string. Error: {e}")
                setattr(self.selected_entity, attr, val_str)
        print(f"Updated attributes for {self.selected_entity.name}")
        self.show_entity_details()

    # --- Tab 2: Game History (Refresh Button Removed) ---
    def _create_history_tab(self):
        self.history_text = scrolledtext.ScrolledText(self.tab_history, wrap=tk.WORD, state='disabled')
        self.history_text.pack(fill="both", expand=True)
        self.refresh_history_tab()

    def refresh_history_tab(self):
        self.history_text.config(state='normal')
        self.history_text.delete('1.0', tk.END)
        history_str = self.game_manager.game_history.get_history_string()
        self.history_text.insert('1.0', history_str)
        self.history_text.config(state='disabled')
        
    # --- Tab 3: Party (Refresh Button Removed) ---
    def _create_party_tab(self):
        self.party_text = scrolledtext.ScrolledText(self.tab_party, wrap=tk.WORD, state='disabled', font=("Courier", 10))
        self.party_text.pack(fill="both", expand=True)
        self.refresh_party_tab()

    def refresh_party_tab(self):
        party = self.game_manager.party
        party_status = f"Party Name: {party.name}\n\n"
        party_status += "--- Members ---\n"
        party_status += party.get_party_status()
        self.party_text.config(state='normal')
        self.party_text.delete('1.0', tk.END)
        self.party_text.insert('1.0', party_status)
        self.party_text.config(state='disabled')

    # --- Tab 4: Environment (Refresh Button Removed) ---
    def _create_environment_tab(self):
        self.env_tree = ttk.Treeview(self.tab_environment)
        self.env_tree.pack(fill="both", expand=True)
        self.refresh_environment_tab()

    def refresh_environment_tab(self):
        for i in self.env_tree.get_children(): self.env_tree.delete(i)
        env = self.game_manager.environment
        rooms_node = self.env_tree.insert("", "end", text="Rooms", open=False)
        doors_node = self.env_tree.insert("", "end", text="Doors", open=False)
        for room_id, room_data in env.rooms.items():
            room_node = self.env_tree.insert(rooms_node, "end", text=f"{room_id}: {room_data.get('name', 'N/A')}")
            for key, val in room_data.items():
                self.env_tree.insert(room_node, "end", text=f"{key}: {str(val)[:100]}")
        for door_id, door_data in env.doors.items():
            door_node = self.env_tree.insert(doors_node, "end", text=f"{door_id}: {door_data.get('name', 'N/A')}")
            for key, val in door_data.items():
                self.env_tree.insert(door_node, "end", text=f"{key}: {str(val)[:100]}")

if __name__ == "__main__":
    main_window = tk.Tk()
    class DummyGameManager:
        def __init__(self): self.turn_order = []
        def start_game(self): self.turn_order = ["player"]; return "Dummy game started."
        def process_player_command(self, cmd): return f"Processed: {cmd}"
    app = GameGUI(main_window, DummyGameManager())
    main_window.mainloop()