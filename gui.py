import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Frame, Entry, Button, Menu, filedialog
from character_creator import CharacterCreatorWindow
import os
import ast
import json

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
        file_menu.add_command(label="Character Creator", command=self.open_character_creator)
        file_menu.add_separator()
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

        if self.debug_win and self.debug_win.winfo_exists():
            self.debug_win.refresh_all_tabs()

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
    
    def open_character_creator(self):
        """Opens the character creation tool window."""
        creator_win = CharacterCreatorWindow(self.root)
        creator_win.grab_set()


class DebugWindow(tk.Toplevel):
    """A Toplevel window for inspecting and modifying game state via tabs."""

    def __init__(self, master, game_manager):
        super().__init__(master)
        self.title("Game State Inspector")
        self.geometry("900x700")
        self.game_manager = game_manager

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_inspector = Frame(self.notebook)
        self.tab_initiative = Frame(self.notebook)
        self.tab_history = Frame(self.notebook)
        self.tab_party = Frame(self.notebook)
        self.tab_environment = Frame(self.notebook)

        self.notebook.add(self.tab_inspector, text="Object Inspector")
        self.notebook.add(self.tab_initiative, text="Initiative")
        self.notebook.add(self.tab_history, text="Game History")
        self.notebook.add(self.tab_party, text="Party")
        self.notebook.add(self.tab_environment, text="Environment")
        
        self._create_inspector_tab()
        self._create_initiative_tab()
        self._create_history_tab()
        self._create_party_tab()
        self._create_environment_tab()

    def refresh_all_tabs(self):
        """Refreshes the content of all tabs in the debug panel."""
        self.populate_entity_list()
        self.refresh_initiative_tab()
        self.refresh_history_tab()
        self.refresh_party_tab()
        self.refresh_environment_tab()

    def _on_mousewheel(self, event, canvas):
        """Cross-platform mouse wheel scrolling."""
        if event.num == 5 or event.delta == -120:
            canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta == 120:
            canvas.yview_scroll(-1, "units")
        return "break"

    def _bind_scroll_recursive(self, widget, canvas):
        """Binds mouse wheel events to a widget and all its children."""
        widget.bind('<MouseWheel>', lambda e, c=canvas: self._on_mousewheel(e, c))
        widget.bind('<Button-4>', lambda e, c=canvas: self._on_mousewheel(e, c))
        widget.bind('<Button-5>', lambda e, c=canvas: self._on_mousewheel(e, c))
        for child in widget.winfo_children():
            if not isinstance(child, tk.Canvas):
                self._bind_scroll_recursive(child, canvas)

    def _add_simple_list_item(self, container_frame, entry_widget_list):
        entry = Entry(container_frame)
        entry.pack(fill=tk.X, expand=True, padx=2, pady=1)
        entry_widget_list.append(entry)

    def _remove_simple_list_item(self, entry_widget_list):
        if entry_widget_list:
            widget_to_remove = entry_widget_list.pop()
            widget_to_remove.destroy()
    
    def _change_quantity(self, entry_widget, amount):
        try:
            current_val = int(entry_widget.get())
            new_val = max(0, current_val + amount)
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, str(new_val))
        except ValueError:
            pass

    def _add_structured_item(self, scrollable_frame, widget_list, template_dict, attr_name):
        """Creates a new row of widgets for a structured list item (e.g., inventory)."""
        blank_item = {}
        for k, v in template_dict.items():
            if isinstance(v, str):
                blank_item[k] = "new item"
            elif isinstance(v, int):
                blank_item[k] = 0
            else:
                blank_item[k] = False
        
        # Ensure any object that should have an equipped status gets one
        equipped_keys = ['equipped', 'prepared']
        has_equipped_key = any(key in blank_item for key in equipped_keys)
        if not has_equipped_key:
            key_name = 'prepared' if attr_name == 'spells' else 'equipped'
            blank_item[key_name] = False
            
        self._create_structured_list_row(scrollable_frame, blank_item, widget_list, attr_name)

    def _remove_structured_item(self, widget_list, row_frame, widget_dict_to_remove):
        """Removes a row of widgets from a structured list UI."""
        row_frame.destroy()
        widget_list.remove(widget_dict_to_remove)

    def _create_structured_list_row(self, parent_frame, item_dict, widget_list, attr_name):
        """Creates the UI for a single structured list item and adds it to the list."""
        item_widgets = {}
        row_frame = Frame(parent_frame, bd=1, relief=tk.RIDGE)
        row_frame.pack(fill=tk.X, expand=True, padx=2, pady=2)

        left_frame = Frame(row_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        right_frame = Frame(row_frame)
        right_frame.pack(side=tk.RIGHT)

        # UNIVERSAL CHECK: Ensure any dictionary item gets an equipped/prepared key if it lacks one.
        equipped_keys = ['equipped', 'prepared']
        has_equipped_key = any(key in item_dict for key in equipped_keys)
        if isinstance(item_dict, dict) and not has_equipped_key:
            key_to_add = 'prepared' if attr_name == 'spells' else 'equipped'
            item_dict[key_to_add] = False

        # Sort to ensure the equipped checkbox always appears on the far right
        sorted_items = sorted(item_dict.items(), key=lambda x: x[0] not in equipped_keys and x[0] != 'quantity')
        
        for key, val in sorted_items:
            parent = right_frame if key in equipped_keys or key == 'quantity' else left_frame
            self._create_widget_for_kv(parent, key, val, item_widgets)

        remove_button = Button(right_frame, text="X", fg="red",
                               command=lambda wl=widget_list, rf=row_frame, iw=item_widgets: self._remove_structured_item(wl, rf, iw))
        remove_button.pack(side=tk.RIGHT, padx=5, pady=2)

        widget_list.append(item_widgets)

    def _create_widget_for_kv(self, parent_frame, key, val, item_widgets_dict):
        """Creates the appropriate widget for a given key-value pair."""
        widget_frame = Frame(parent_frame)
        widget_frame.pack(side=tk.LEFT, padx=5, pady=2)

        tk.Label(widget_frame, text=f"{key}:").pack(side=tk.LEFT)

        if isinstance(val, bool) or key in ['equipped', 'prepared']:
            bool_var = tk.BooleanVar(value=bool(val))
            chk = tk.Checkbutton(widget_frame, variable=bool_var)
            chk.pack(side=tk.LEFT)
            item_widgets_dict[key] = bool_var
        elif isinstance(val, int):
            qty_entry = Entry(widget_frame, width=4)
            qty_entry.insert(0, str(val))
            minus_btn = Button(widget_frame, text="-", command=lambda e=qty_entry: self._change_quantity(e, -1))
            plus_btn = Button(widget_frame, text="+", command=lambda e=qty_entry: self._change_quantity(e, 1))
            minus_btn.pack(side=tk.LEFT)
            qty_entry.pack(side=tk.LEFT)
            plus_btn.pack(side=tk.LEFT)
            item_widgets_dict[key] = qty_entry
        else:
            entry = Entry(widget_frame, width=15)
            entry.insert(0, str(val))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_widgets_dict[key] = entry

    def _create_dict_row(self, parent_frame, key, value, widget_list):
        """Creates a single editable row for the attitudes editor."""
        row_frame = Frame(parent_frame)
        row_frame.pack(fill="x", expand=True, pady=1)
        
        key_entry = Entry(row_frame, font=("Arial", 10))
        key_entry.insert(0, str(key))
        key_entry.pack(side="left", fill="x", expand=True)

        tk.Label(row_frame, text=":", font=("Arial", 10, "bold")).pack(side="left", padx=3)

        val_entry = Entry(row_frame, font=("Arial", 10))
        val_entry.insert(0, str(value))
        val_entry.pack(side="left", fill="x", expand=True)
        
        widget_tuple = (key_entry, val_entry)
        
        remove_button = Button(row_frame, text="X", fg="red", relief="flat",
                               command=lambda rf=row_frame, wt=widget_tuple, wl=widget_list: self._remove_dict_item(rf, wt, wl))
        remove_button.pack(side="left", padx=5)

        widget_list.append(widget_tuple)

    def _add_dict_item(self, parent_frame, widget_list):
        """Adds a new, blank key-value entry row to the attitudes editor."""
        self._create_dict_row(parent_frame, "Name", "Neutral", widget_list)

    def _remove_dict_item(self, row_frame, widget_tuple, widget_list):
        """Removes a row from the attitudes editor UI."""
        row_frame.destroy()
        if widget_tuple in widget_list:
            widget_list.remove(widget_tuple)

    def _create_inspector_tab(self):
        self.displayed_entities, self.selected_entity, self.attribute_widgets = [], None, {}
        paned_window = tk.PanedWindow(self.tab_inspector, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        left_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        self.entity_listbox = tk.Listbox(left_frame)
        self.entity_listbox.pack(fill=tk.BOTH, expand=True)
        self.entity_listbox.bind("<<ListboxSelect>>", self.show_entity_details)
        paned_window.add(left_frame, width=250)
        right_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        self.main_canvas = tk.Canvas(right_frame)
        scrollbar = tk.Scrollbar(right_frame, orient="vertical", command=self.main_canvas.yview)
        self.details_frame = Frame(self.main_canvas)
        self.details_frame.bind("<Configure>", lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")))
        self.main_canvas.create_window((0, 0), window=self.details_frame, anchor="nw")
        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        self.main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        paned_window.add(right_frame)
        Button(self.tab_inspector, text="Save Changes to Selected Entity", command=self.save_entity_details).pack(side=tk.BOTTOM, pady=5, fill=tk.X)
        self.populate_entity_list()

    def populate_entity_list(self):
        self.entity_listbox.delete(0, tk.END)
        self.displayed_entities.clear()
        if not self.game_manager.turn_order: return
        current_actor = self.game_manager.turn_order[self.game_manager.current_turn_index]
        all_entities = self.game_manager.environment.players + self.game_manager.environment.actors + self.game_manager.environment.objects
        for entity in all_entities:
            if hasattr(entity, 'location') and entity.location == current_actor.location:
                self.displayed_entities.append(entity)
                self.entity_listbox.insert(tk.END, f"{entity.__class__.__name__}: {entity.name}")

    def show_entity_details(self, event=None):
        sel_indices = self.entity_listbox.curselection()
        if not sel_indices: return
        
        self.selected_entity = self.displayed_entities[sel_indices[0]]
        for widget in self.details_frame.winfo_children(): widget.destroy()
        self.attribute_widgets = {}
        
        all_attr_keys = set(vars(self.selected_entity).keys()) | {'memories', 'quotes'}
        attrs = sorted([attr for attr in all_attr_keys if attr not in ['source_data', 'manager']])

        self.details_frame.grid_columnconfigure(1, weight=1)
        self._bind_scroll_recursive(self.details_frame, self.main_canvas)
        
        for i, attr_name in enumerate(attrs):
            value = getattr(self.selected_entity, attr_name, [])
            tk.Label(self.details_frame, text=attr_name).grid(row=i, column=0, sticky="nw", padx=5, pady=5)
            
            # Condition to identify any list of dictionary-like objects
            is_structured_list = isinstance(value, list) and value and isinstance(value[0], dict)
            # Also treat known empty lists as structured
            if not is_structured_list and attr_name in ['inventory', 'spells', 'abilities', 'actions'] and isinstance(value, list):
                 is_structured_list = True

            if is_structured_list:
                self._create_structured_list_ui(self.details_frame, i, value, attr_name)

            elif attr_name in ['memories', 'quotes']:
                widget = tk.Text(self.details_frame, height=5, wrap=tk.WORD)
                if isinstance(value, list):
                    widget.insert('1.0', '\n'.join(map(str, value)))
                else:
                    widget.insert('1.0', str(value))
                widget.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
                self.attribute_widgets[attr_name] = widget
            
            elif attr_name == 'attitudes':
                normalized_attitudes = value if isinstance(value, dict) else {k: v for d in value for k, v in d.items()}
                main_container = Frame(self.details_frame, bd=1, relief=tk.SOLID)
                main_container.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
                items_frame = Frame(main_container)
                items_frame.pack(fill="x", expand=True, padx=2, pady=2)
                sub_widgets = []
                for key, val in normalized_attitudes.items():
                    self._create_dict_row(items_frame, key, val, sub_widgets)
                add_button = Button(main_container, text="+ Add Attitude", command=lambda f=items_frame, w=sub_widgets: self._add_dict_item(f, w))
                add_button.pack(fill="x", expand=True, side="bottom")
                self.attribute_widgets[attr_name] = sub_widgets
            
            elif isinstance(value, list):
                 self._create_simple_list_ui(self.details_frame, i, value, attr_name)
                 
            elif isinstance(value, dict):
                dict_frame = Frame(self.details_frame, bd=1, relief=tk.SOLID)
                dict_frame.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
                dict_frame.grid_columnconfigure(1, weight=1)
                sub_entries = {}
                for j, (key, val) in enumerate(value.items()):
                    tk.Label(dict_frame, text=key).grid(row=j, column=0, sticky="w", padx=2, pady=2)
                    entry = Entry(dict_frame)
                    entry.insert(0, str(val))
                    entry.grid(row=j, column=1, sticky="ew", padx=2, pady=2)
                    sub_entries[key] = entry
                self.attribute_widgets[attr_name] = sub_entries
            else:
                widget = Entry(self.details_frame)
                widget.insert(0, str(value))
                widget.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
                self.attribute_widgets[attr_name] = widget
    
    def _create_structured_list_ui(self, parent, row_index, value, attr_name):
        """Creates a generic UI for a list of dictionaries."""
        main_container = Frame(parent, bd=1, relief=tk.SOLID)
        main_container.grid(row=row_index, column=1, sticky="ew", padx=2, pady=2)
        main_container.grid_columnconfigure(0, weight=1)
        list_canvas = tk.Canvas(main_container, height=150, bd=0, highlightthickness=0)
        list_scrollbar = tk.Scrollbar(main_container, orient="vertical", command=list_canvas.yview)
        scrollable_frame = Frame(list_canvas)
        scrollable_frame.bind("<Configure>", lambda e, c=list_canvas: c.configure(scrollregion=c.bbox("all")))
        list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        main_container.grid_rowconfigure(0, weight=1)
        item_widget_list = []
        self.attribute_widgets[attr_name] = item_widget_list
        for item_dict in value:
            self._create_structured_list_row(scrollable_frame, item_dict, item_widget_list, attr_name)
        self._bind_scroll_recursive(scrollable_frame, list_canvas)
        
        # Use existing item as a template, or create a default one if the list is empty
        template = value[0] if value else {}
        if not template:
            if attr_name == 'inventory':
                template = {'item': 'new_item', 'quantity': 1, 'equipped': False}
            elif attr_name == 'spells':
                template = {'name': 'new_spell', 'level': 1, 'prepared': False}
            elif attr_name == 'abilities':
                template = {'name': 'new_ability', 'effect': 'description'}
            elif attr_name == 'actions':
                 template = {"skill": "strength", "difficulty": 10, "pass": "success", "fail": "nothing"}
            else: # A generic fallback for other unknown list types
                template = {'name': 'new_item', 'description': 'a new description'}

        add_button = Button(main_container, text="+ Add New Item", command=lambda sf=scrollable_frame, iwl=item_widget_list, t=template, an=attr_name: self._add_structured_item(sf, iwl, t, an))
        add_button.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _create_simple_list_ui(self, parent, row_index, value, attr_name):
        list_container = Frame(parent, bd=1, relief=tk.SOLID)
        list_container.grid(row=row_index, column=1, sticky="ew", padx=2, pady=2)
        list_container.grid_columnconfigure(0, weight=1)
        list_canvas = tk.Canvas(list_container, height=120)
        list_scrollbar = tk.Scrollbar(list_container, orient="vertical", command=list_canvas.yview)
        scrollable_frame = Frame(list_canvas)
        scrollable_frame.bind("<Configure>", lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        list_container.grid_rowconfigure(0, weight=1)
        entry_widgets = []
        for item in value:
            entry = Entry(scrollable_frame)
            entry.insert(0, str(item))
            entry.pack(fill=tk.X, expand=True, padx=2, pady=1)
            entry_widgets.append(entry)
        self.attribute_widgets[attr_name] = entry_widgets
        self._bind_scroll_recursive(scrollable_frame, list_canvas)
        button_frame = Frame(list_container)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        add_button = Button(button_frame, text="+ Add Item", command=lambda sf=scrollable_frame, ew=entry_widgets: self._add_simple_list_item(sf, ew))
        add_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        remove_button = Button(button_frame, text="- Remove Last", command=lambda ew=entry_widgets: self._remove_simple_list_item(ew))
        remove_button.pack(side=tk.LEFT, expand=True, fill=tk.X)

    def save_entity_details(self):
        if not self.selected_entity: return
        
        for attr, collection in self.attribute_widgets.items():
            orig_val = getattr(self.selected_entity, attr, None)
            try:
                if attr in ['memories', 'quotes']:
                    text_content = collection.get('1.0', tk.END).strip()
                    new_list = [line for line in text_content.split('\n') if line.strip()]
                    setattr(self.selected_entity, attr, new_list)

                elif attr == 'attitudes':
                    new_dict = {}
                    if isinstance(collection, list):
                        for (key_entry, val_entry) in collection:
                            key, val = key_entry.get().strip(), val_entry.get().strip()
                            if key: new_dict[key] = val
                    setattr(self.selected_entity, attr, new_dict)

                elif isinstance(collection, list) and isinstance(orig_val, list):
                    if collection and isinstance(collection[0], dict):
                        # This now handles all structured lists, including inventory
                        new_list_of_dicts = []
                        for item_widget_dict in collection:
                            new_item_dict = {}
                            for key, widget in item_widget_dict.items():
                                val = widget.get() if isinstance(widget, (tk.BooleanVar, Entry)) else widget
                                new_item_dict[key] = val
                            
                            # Attempt to cast saved values back to their original types
                            template_dict = (orig_val[0] if orig_val else {}) or new_item_dict
                            for key in new_item_dict:
                                if key in template_dict:
                                    # Use string as a fallback type
                                    orig_type = type(template_dict.get(key, ''))
                                    try:
                                        current_val = new_item_dict[key]
                                        if orig_type is bool and not isinstance(current_val, bool):
                                            new_item_dict[key] = str(current_val).lower() in ('true', '1', 'yes')
                                        elif type(current_val) is not orig_type:
                                            new_item_dict[key] = orig_type(current_val)
                                    except (ValueError, TypeError): pass
                            new_list_of_dicts.append(new_item_dict)
                        setattr(self.selected_entity, attr, new_list_of_dicts)
                    else:
                        new_list = []
                        item_type = type(orig_val[0]) if orig_val else str
                        for entry_widget in collection:
                            try:
                                new_list.append(item_type(entry_widget.get()))
                            except (ValueError, TypeError):
                                new_list.append(entry_widget.get())
                        setattr(self.selected_entity, attr, new_list)

                elif isinstance(collection, dict) and isinstance(orig_val, dict):
                    new_dict = {}
                    for key, entry_widget in collection.items():
                        val_str = entry_widget.get()
                        orig_type = type(orig_val.get(key, ''))
                        try:
                            new_dict[key] = orig_type(val_str)
                        except (ValueError, TypeError):
                            new_dict[key] = val_str
                    setattr(self.selected_entity, attr, new_dict)
                
                elif isinstance(collection, Entry):
                    val_str = collection.get()
                    if isinstance(orig_val, bool):
                        new_val = val_str.lower() in ('true', '1', 'yes')
                    elif orig_val is None:
                        new_val = val_str if val_str.lower() != 'none' else None
                    else:
                        new_val = type(orig_val)(val_str)
                    setattr(self.selected_entity, attr, new_val)

            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save attribute '{attr}'.\nError: {e}")

        messagebox.showinfo("Success", f"Attributes for {self.selected_entity.name} have been updated.")
        self.show_entity_details()

    def _create_initiative_tab(self):
        self.initiative_text = scrolledtext.ScrolledText(self.tab_initiative, wrap=tk.WORD, state='disabled', font=("Courier", 10))
        self.initiative_text.pack(fill="both", expand=True)
        self.refresh_initiative_tab()

    def refresh_initiative_tab(self):
        if not self.game_manager.turn_order: return
        initiative_str = self.game_manager.get_initiative_order()
        self.initiative_text.config(state='normal')
        self.initiative_text.delete('1.0', tk.END)
        self.initiative_text.insert('1.0', initiative_str)
        self.initiative_text.config(state='disabled')

    def _create_history_tab(self):
        self.history_text = scrolledtext.ScrolledText(self.tab_history, wrap=tk.WORD, state='disabled')
        self.history_text.pack(fill="both", expand=True)
        self.refresh_history_tab()

    def refresh_history_tab(self):
        if not self.game_manager.turn_order: return
        self.history_text.config(state='normal')
        self.history_text.delete('1.0', tk.END)
        history_str = self.game_manager.game_history.get_history_string()
        self.history_text.insert('1.0', history_str)
        self.history_text.config(state='disabled')
        
    def _create_party_tab(self):
        self.party_text = scrolledtext.ScrolledText(self.tab_party, wrap=tk.WORD, state='disabled', font=("Courier", 10))
        self.party_text.pack(fill="both", expand=True)
        self.refresh_party_tab()

    def refresh_party_tab(self):
        if not self.game_manager.turn_order: return
        party = self.game_manager.party
        party_status = f"Party Name: {party.name}\n\n"
        party_status += "--- Members ---\n"
        party_status += party.get_party_status()
        self.party_text.config(state='normal')
        self.party_text.delete('1.0', tk.END)
        self.party_text.insert('1.0', party_status)
        self.party_text.config(state='disabled')
        
    # --- ENVIRONMENT TAB METHODS START HERE ---

    def _get_descriptive_name(self, item, index):
        item_node_name = f"Item {index+1}"
        if isinstance(item, dict):
            if 'name' in item: item_node_name = item['name']
            elif 'item' in item: item_node_name = f"{item['item']} (x{item.get('quantity', 1)})"
            elif 'zone' in item: item_node_name = f"Zone {item['zone']}"
            elif 'skill' in item: item_node_name = f"Action: {item['skill']}"
            elif 'door_ref' in item: item_node_name = f"Exit via {item['door_ref']}"
        return item_node_name
        
    def _add_node_to_tree(self, parent_node_id, parent_data, data, key_name=""):
        FLATTENED_LISTS = ['objects', 'actions', 'inventory', 'exits']

        if isinstance(data, dict):
            node_text = key_name
            if key_name == 'trap': node_text = f"Trap: {data.get('name', 'Unnamed Trap')}"
            
            node_id = self.env_tree.insert(parent_node_id, "end", text=node_text, open=False)
            self.tree_item_map[node_id] = {'data': data, 'parent': parent_data, 'key': key_name}
            for key, value in data.items():
                self._add_node_to_tree(node_id, data, value, key_name=key)

        elif isinstance(data, list):
            if key_name in FLATTENED_LISTS:
                for i, item in enumerate(data):
                    item_node_name = self._get_descriptive_name(item, i)
                    self._add_node_to_tree(parent_node_id, data, item, key_name=item_node_name)
            else:
                node_id = self.env_tree.insert(parent_node_id, "end", text=key_name, open=False)
                self.tree_item_map[node_id] = {'data': data, 'parent': parent_data, 'key': key_name}
                for i, item in enumerate(data):
                    item_node_name = self._get_descriptive_name(item, i)
                    self._add_node_to_tree(node_id, data, item, key_name=item_node_name)

    def _create_environment_tab(self):
        self.tree_item_map, self.selected_env_item, self.env_attribute_widgets = {}, None, {}
        paned_window = tk.PanedWindow(self.tab_environment, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        left_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        self.env_tree = ttk.Treeview(left_frame)
        tree_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.env_tree.yview)
        self.env_tree.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.pack(side="right", fill="y")
        self.env_tree.pack(fill="both", expand=True)
        self.env_tree.bind("<<TreeviewSelect>>", self.show_env_details)
        paned_window.add(left_frame, width=300)

        right_frame = Frame(paned_window, bd=2, relief=tk.SUNKEN)
        self.env_canvas = tk.Canvas(right_frame)
        details_scrollbar = tk.Scrollbar(right_frame, orient="vertical", command=self.env_canvas.yview)
        self.env_details_frame = Frame(self.env_canvas)
        self.env_details_frame.bind("<Configure>", lambda e: self.env_canvas.configure(scrollregion=self.env_canvas.bbox("all")))
        self.env_canvas.create_window((0, 0), window=self.env_details_frame, anchor="nw")
        self.env_canvas.configure(yscrollcommand=details_scrollbar.set)
        self.env_canvas.pack(side="left", fill="both", expand=True)
        details_scrollbar.pack(side="right", fill="y")
        paned_window.add(right_frame)
        
        button_frame = Frame(self.tab_environment)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        Button(button_frame, text="Save Changes", command=self.save_env_details).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.add_menu_button = ttk.Menubutton(button_frame, text="Add...")
        self.add_menu = Menu(self.add_menu_button, tearoff=0)
        self.add_menu_button["menu"] = self.add_menu
        self.add_menu_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        Button(button_frame, text="Remove Selected", fg="red", command=self.remove_env_item).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.refresh_environment_tab()

    def refresh_environment_tab(self):
        if not self.game_manager.turn_order: return
        for i in self.env_tree.get_children(): self.env_tree.delete(i)
        self.tree_item_map.clear()
        
        for widget in self.env_details_frame.winfo_children(): widget.destroy()
        self.selected_env_item = None
        self._update_add_menu()

        env = self.game_manager.environment
        if hasattr(env, 'rooms') and isinstance(env.rooms, dict):
            rooms_root = self.env_tree.insert("", "end", text="Rooms", open=True)
            self.tree_item_map[rooms_root] = {'data': env.rooms, 'parent': env, 'key': 'rooms'}
            for room_id, room_data in env.rooms.items():
                self._add_node_to_tree(rooms_root, env.rooms, room_data, key_name=f"{room_id}: {room_data.get('name', '')}")

        if hasattr(env, 'doors') and isinstance(env.doors, dict):
            doors_root = self.env_tree.insert("", "end", text="Doors", open=False)
            self.tree_item_map[doors_root] = {'data': env.doors, 'parent': env, 'key': 'doors'}
            for door_id, door_data in env.doors.items():
                self._add_node_to_tree(doors_root, env.doors, door_data, key_name=f"{door_id}: {door_data.get('name', '')}")

    def show_env_details(self, event=None):
        """Displays editable widgets for the selected environment item."""
        selection = self.env_tree.selection()
        if not selection: 
            self.selected_env_item = None
            self._update_add_menu()
            return
        
        selected_id = selection[0]
        self.selected_env_item = self.tree_item_map.get(selected_id)
        if not self.selected_env_item: return

        for widget in self.env_details_frame.winfo_children():
            widget.destroy()
        self.env_attribute_widgets.clear()
        
        data = self.selected_env_item['data']
        
        self.env_details_frame.grid_columnconfigure(1, weight=1)
        self._bind_scroll_recursive(self.env_details_frame, self.env_canvas)

        if isinstance(data, dict):
            i = 0
            for key, value in data.items():
                tk.Label(self.env_details_frame, text=key).grid(row=i, column=0, sticky="nw", padx=5, pady=2)

                if key == 'description':
                    widget = tk.Text(self.env_details_frame, height=4, wrap=tk.WORD)
                    widget.insert("1.0", str(value))
                    widget.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
                    self.env_attribute_widgets[key] = widget
                elif isinstance(value, (str, int, float, bool)):
                    widget = Entry(self.env_details_frame)
                    widget.insert(0, str(value))
                    widget.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
                    self.env_attribute_widgets[key] = widget
                else:
                    tk.Label(self.env_details_frame, text=f"<{type(value).__name__}> (Not directly editable)").grid(row=i, column=1, sticky="w", padx=5, pady=2)
                i += 1
        elif isinstance(data, (str, int, float, bool)):
             key = self.selected_env_item['key']
             tk.Label(self.env_details_frame, text=f"Value for '{key}'").grid(row=0, column=0, sticky="nw", padx=5, pady=2)
             entry = Entry(self.env_details_frame)
             entry.insert(0, str(data))
             entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
             self.env_attribute_widgets['value'] = entry

        self._update_add_menu()

    def save_env_details(self):
        if not self.selected_env_item:
            messagebox.showwarning("Warning", "No environment item selected.")
            return

        data, parent, key = self.selected_env_item['data'], self.selected_env_item['parent'], self.selected_env_item['key']

        if isinstance(data, dict):
            for attr_key, widget in self.env_attribute_widgets.items():
                if attr_key in data:
                    new_val_str = widget.get("1.0", tk.END).strip() if isinstance(widget, tk.Text) else widget.get()
                    orig_type = type(data[attr_key])
                    try:
                        data[attr_key] = new_val_str.lower() in ('true', '1', 'yes') if orig_type is bool else orig_type(new_val_str)
                    except (ValueError, TypeError):
                        messagebox.showerror("Save Error", f"Invalid value for '{attr_key}'. Could not convert '{new_val_str}' to {orig_type.__name__}.")
                        return
        elif 'value' in self.env_attribute_widgets:
            new_val_str = self.env_attribute_widgets['value'].get()
            orig_type = type(data)
            try:
                new_val = new_val_str.lower() in ('true', '1', 'yes') if orig_type is bool else orig_type(new_val_str)
                if isinstance(parent, dict): parent[key] = new_val
                elif isinstance(parent, list): parent[key] = new_val
            except (ValueError, TypeError):
                 messagebox.showerror("Save Error", f"Invalid value. Could not convert '{new_val_str}' to {orig_type.__name__}.")
                 return
        
        messagebox.showinfo("Success", "Changes saved successfully.")
        self.refresh_environment_tab()
    
    def _get_template(self, template_name, context_data=None):
        if template_name == 'zone':
            next_zone_num = len(context_data.get('zones', [])) + 1 if context_data else 1
            return {"zone": next_zone_num, "description": "A new zone.", "objects": [], "exits": []}
        elif template_name == 'object':
            return {"name": "New Object", "description": "A new object.", "actions": []}
        elif template_name == 'exit':
            return {"door_ref": "some_door_id", "to_room": "some_room_id", "to_zone": 1, "description": "An exit."}
        elif template_name == 'trap':
            return {"name": "new trap", "status": "armed", "known": "", "attack": 10, "damage": 5, "actions": []}
        elif template_name == 'action':
            return {"skill": "strength", "difficulty": 10, "pass": "success", "fail": "nothing"}
        elif template_name == 'inventory_item':
            return {"item": "new_item_id", "quantity": 1}
        return {}

    def _add_item_to_list(self, parent_dict, list_key, template):
        if not isinstance(parent_dict.get(list_key), list):
            parent_dict[list_key] = []
        parent_dict[list_key].append(template)
        self.refresh_environment_tab()

    def _add_item_as_dict_key(self, parent_dict, key, template):
        if key not in parent_dict:
            parent_dict[key] = template
            self.refresh_environment_tab()
    
    def _update_add_menu(self):
        self.add_menu.delete(0, "end")
        if not self.selected_env_item:
            self.add_menu.add_command(label="Add Room", command=self._add_new_room)
            self.add_menu.add_command(label="Add Door", command=self._add_new_door)
            return

        data, key = self.selected_env_item['data'], self.selected_env_item['key']
        
        if isinstance(data, dict):
            if key == 'rooms': self.add_menu.add_command(label="Add Room", command=self._add_new_room)
            elif key == 'doors': self.add_menu.add_command(label="Add Door", command=self._add_new_door)
            elif 'room_id' in data:
                self.add_menu.add_command(label="Add Zone", command=lambda d=data: self._add_item_to_list(d, 'zones', self._get_template('zone', d)))
            elif 'zone' in data:
                self.add_menu.add_command(label="Add Object", command=lambda d=data: self._add_item_to_list(d, 'objects', self._get_template('object')))
                self.add_menu.add_command(label="Add Exit", command=lambda d=data: self._add_item_to_list(d, 'exits', self._get_template('exit')))
                if 'trap' not in data: self.add_menu.add_command(label="Add Trap", command=lambda d=data: self._add_item_as_dict_key(d, 'trap', self._get_template('trap')))
            elif 'name' in data and 'door_ref' not in data:
                self.add_menu.add_command(label="Add Action", command=lambda d=data: self._add_item_to_list(d, 'actions', self._get_template('action')))
                if 'inventory' not in data: self.add_menu.add_command(label="Add Inventory", command=lambda d=data: self._add_item_to_list(d, 'inventory', []))
                else: self.add_menu.add_command(label="Add Inventory Item", command=lambda d=data: self._add_item_to_list(d, 'inventory', self._get_template('inventory_item')))
            elif 'door_id' in data:
                self.add_menu.add_command(label="Add Action", command=lambda d=data: self._add_item_to_list(d, 'actions', self._get_template('action')))

        if self.add_menu.index("end") is None:
            self.add_menu.add_command(label="(Nothing to add here)", state="disabled")
            
    def _add_new_room(self):
        rooms, i = self.game_manager.environment.rooms, 1
        while f"new_room_{i}" in rooms: i += 1
        new_id = f"new_room_{i}"
        rooms[new_id] = {"name": "New Room", "room_id": new_id, "zones": []}
        self.refresh_environment_tab()

    def _add_new_door(self):
        doors, i = self.game_manager.environment.doors, 1
        while f"new_door_{i}" in doors: i += 1
        new_id = f"new_door_{i}"
        doors[new_id] = {"name": "New Door", "door_id": new_id, "status": "closed", "actions": []}
        self.refresh_environment_tab()

    def remove_env_item(self):
        if not self.selected_env_item:
            return messagebox.showwarning("Warning", "No environment item selected to remove.")
        parent, data, key = self.selected_env_item['parent'], self.selected_env_item['data'], self.selected_env_item['key']
        
        msg = f"Are you sure you want to permanently remove '{key}'?" if isinstance(key, str) else "Are you sure you want to permanently remove this item?"
        if messagebox.askyesno("Confirm Removal", msg):
            try:
                if isinstance(parent, list): parent.remove(data)
                elif isinstance(parent, dict): del parent[key]
                else: return messagebox.showerror("Error", "Cannot remove this type of element.")
                self.refresh_environment_tab()
            except (ValueError, KeyError):
                messagebox.showerror("Error", "Could not remove the item.")
                self.refresh_environment_tab()

if __name__ == "__main__":
    main_window = tk.Tk()
    class DummyGameManager:
        def __init__(self): self.turn_order = []
        def start_game(self): self.turn_order = ["player"]; return "Dummy game started."
        def process_player_command(self, cmd): return f"Processed: {cmd}"
    app = GameGUI(main_window, DummyGameManager())
    main_window.mainloop()