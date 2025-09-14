import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Frame, Entry, Button, Menu, filedialog
from character_creator import CharacterCreatorWindow
import os
import ast
import json # <-- Added this import

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
        creator_win.grab_set() # This makes the creator window modal


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

    # --- Helper methods for the Inspector Tab ---
    def _on_mousewheel(self, event, canvas):
        """Cross-platform mouse wheel scrolling that stops event propagation."""
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
        """Creates a new row of widgets for a structured list item."""
        blank_item = {}
        for k, v in template_dict.items():
            if k in ['name', 'item', 'id', 'spell', 'attitude', 'target']:
                blank_item[k] = "default" if attr_name == 'attitudes' else "new item"
            elif isinstance(v, str):
                blank_item[k] = ""
            elif isinstance(v, int):
                blank_item[k] = 0
            else:
                blank_item[k] = False
        
        equippable_attrs = ['inventory', 'spells', 'abilities']
        if attr_name in equippable_attrs and 'equipped' not in blank_item:
            blank_item['equipped'] = False
            
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

        equippable_attrs = ['inventory', 'spells', 'abilities']
        if attr_name in equippable_attrs and 'equipped' not in item_dict:
            item_dict['equipped'] = False

        for key, val in item_dict.items():
            parent = right_frame if key in ['quantity', 'equipped'] else left_frame
            self._create_widget_for_kv(parent, key, val, item_widgets)

        remove_button = Button(right_frame, text="X", fg="red", command=lambda wl=widget_list, rf=row_frame, iw=item_widgets: self._remove_structured_item(wl, rf, iw))
        remove_button.pack(side=tk.RIGHT, padx=5, pady=2)

        widget_list.append(item_widgets)

    def _create_widget_for_kv(self, parent_frame, key, val, item_widgets_dict):
        """Creates the appropriate widget for a given key-value pair."""
        widget_frame = Frame(parent_frame)
        widget_frame.pack(side=tk.LEFT, padx=5, pady=2)

        # FIX: Ensure name-like keys are always editable Entry widgets
        if key in ['name', 'item', 'id', 'spell', 'attitude', 'target']:
            tk.Label(widget_frame, text=f"{key}:").pack(side=tk.LEFT)
            entry = Entry(widget_frame, width=15)
            entry.insert(0, str(val))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_widgets_dict[key] = entry
        elif isinstance(val, bool) or key == 'equipped':
            tk.Label(widget_frame, text=f"{key}:").pack(side=tk.LEFT)
            bool_var = tk.BooleanVar(value=bool(val))
            chk = tk.Checkbutton(widget_frame, variable=bool_var)
            chk.pack(side=tk.LEFT)
            item_widgets_dict[key] = bool_var
        elif isinstance(val, int):
            tk.Label(widget_frame, text=f"{key}:").pack(side=tk.LEFT)
            qty_entry = Entry(widget_frame, width=4)
            qty_entry.insert(0, str(val))
            minus_btn = Button(widget_frame, text="-", command=lambda e=qty_entry: self._change_quantity(e, -1))
            plus_btn = Button(widget_frame, text="+", command=lambda e=qty_entry: self._change_quantity(e, 1))
            minus_btn.pack(side=tk.LEFT)
            qty_entry.pack(side=tk.LEFT)
            plus_btn.pack(side=tk.LEFT)
            item_widgets_dict[key] = qty_entry
        else:
            tk.Label(widget_frame, text=f"{key}:").pack(side=tk.LEFT)
            entry = Entry(widget_frame, width=15)
            entry.insert(0, str(val))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_widgets_dict[key] = entry

    # --- Tab 1: Object Inspector ---
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
        sel = self.entity_listbox.curselection()
        if not sel: return
        self.selected_entity = self.displayed_entities[sel[0]]
        for widget in self.details_frame.winfo_children(): widget.destroy()
        self.attribute_widgets = {}
        
        attrs = sorted([attr for attr in vars(self.selected_entity) if attr not in ['source_data', 'manager']])
        self.details_frame.grid_columnconfigure(1, weight=1)

        self._bind_scroll_recursive(self.details_frame, self.main_canvas)

        for i, attr_name in enumerate(attrs):
            value = getattr(self.selected_entity, attr_name)
            tk.Label(self.details_frame, text=attr_name).grid(row=i, column=0, sticky="nw", padx=5, pady=5)
            
            if isinstance(value, list) and value:
                if isinstance(value[0], dict):
                    main_container = Frame(self.details_frame, bd=1, relief=tk.SOLID)
                    main_container.grid(row=i, column=1, sticky="ew", padx=2, pady=2)
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

                    template = value[0] if value else {}
                    add_button = Button(main_container, text="+ Add New Item", command=lambda sf=scrollable_frame, iwl=item_widget_list, t=template, an=attr_name: self._add_structured_item(sf, iwl, t, an))
                    add_button.grid(row=1, column=0, columnspan=2, sticky="ew")
                
                else:
                    self._create_simple_list_ui(self.details_frame, i, value, attr_name)

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
                if isinstance(collection, list) and isinstance(orig_val, list):
                    if collection and isinstance(collection[0], dict): # Check based on widget structure
                        new_list_of_dicts = []
                        for item_widget_dict in collection:
                            new_item_dict = {}
                            for key, widget in item_widget_dict.items():
                                val = None
                                if isinstance(widget, tk.BooleanVar): val = widget.get()
                                elif isinstance(widget, Entry): val = widget.get()
                                else: val = widget # Raw, uneditable value like a name
                                new_item_dict[key] = val
                            
                            # Try to convert types back based on original template
                            if orig_val:
                                template_dict = orig_val[0]
                                for key in new_item_dict:
                                    if key in template_dict:
                                        orig_type = type(template_dict.get(key, ''))
                                        current_val = new_item_dict[key]
                                        try:
                                            if orig_type is bool and not isinstance(current_val, bool):
                                                new_item_dict[key] = str(current_val).lower() in ('true', '1', 'yes')
                                            elif type(current_val) is not orig_type:
                                                new_item_dict[key] = orig_type(current_val)
                                        except (ValueError, TypeError):
                                            pass # Keep as string if conversion fails
                            new_list_of_dicts.append(new_item_dict)
                        setattr(self.selected_entity, attr, new_list_of_dicts)
                    
                    else: # Simple list of entry widgets
                        new_list = []
                        item_type = str
                        if orig_val and orig_val[0] is not None: item_type = type(orig_val[0])
                        for entry_widget in collection:
                            val_str = entry_widget.get()
                            try: new_list.append(item_type(val_str))
                            except (ValueError, TypeError): new_list.append(val_str)
                        setattr(self.selected_entity, attr, new_list)

                elif isinstance(collection, dict) and isinstance(orig_val, dict):
                    new_dict = {}
                    for key, entry_widget in collection.items():
                        val_str = entry_widget.get()
                        orig_type = type(orig_val.get(key, ''))
                        try: new_dict[key] = orig_type(val_str)
                        except (ValueError, TypeError): new_dict[key] = val_str
                    setattr(self.selected_entity, attr, new_dict)

                elif isinstance(collection, Entry):
                    val_str = collection.get()
                    if isinstance(orig_val, bool): new_val = val_str.lower() in ('true', '1', 'yes')
                    elif orig_val is None: new_val = val_str if val_str.lower() != 'none' else None
                    else: new_val = type(orig_val)(val_str)
                    setattr(self.selected_entity, attr, new_val)

            except Exception as e:
                print(f"Could not save attribute '{attr}'. Error: {e}")

        print(f"Updated attributes for {self.selected_entity.name}")
        self.show_entity_details()

    # --- Tab 2: Initiative ---
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

    # --- Tab 3: Game History ---
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
        
    # --- Tab 4: Party ---
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

    # --- Tab 5: Environment ---
    def _create_environment_tab(self):
        self.env_tree = ttk.Treeview(self.tab_environment)
        self.env_tree.pack(fill="both", expand=True)
        self.refresh_environment_tab()

    def refresh_environment_tab(self):
        if not self.game_manager.turn_order: return
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