import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Frame, Label, Button, Entry
import yaml
from d6_rules import D6_SKILLS_BY_ATTRIBUTE

# --- Configuration ---
STARTING_POINTS = 65
MIN_ATTRIBUTE = 1

class CharacterCreatorWindow(tk.Toplevel):
    """A Toplevel window for creating a new character with a point-buy system."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Character Creator")
        self.geometry("700x750")

        # --- Initialize Data ---
        self.points_pool = STARTING_POINTS
        self.character_data = self._initialize_character_data()
        self.value_labels = {} # To store references to the value labels for easy updates

        # --- Build UI ---
        self._create_widgets()
        self._update_all_displays()

    def _initialize_character_data(self):
        """Sets up the initial dictionary for the new character."""
        char = {
            'name': "New Character",
            'description': "A new adventurer.",
            'attributes': {
                "physique": MIN_ATTRIBUTE, "dexterity": MIN_ATTRIBUTE,
                "intelligence": MIN_ATTRIBUTE, "wisdom": MIN_ATTRIBUTE,
                "presence": MIN_ATTRIBUTE
            },
            'skills': {}
        }
        # Initialize all known skills to 0
        for skill_list in D6_SKILLS_BY_ATTRIBUTE.values():
            for skill in skill_list:
                char['skills'][skill] = 0
        return char

    def _create_widgets(self):
        """Creates and lays out all the GUI widgets."""
        main_frame = Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Section (Name, Points) ---
        top_frame = Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        Label(top_frame, text="Character Name:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.name_entry = Entry(top_frame, width=30)
        self.name_entry.insert(0, self.character_data['name'])
        self.name_entry.grid(row=0, column=1, sticky="ew")

        self.points_label = Label(top_frame, text=f"Points Remaining: {self.points_pool}", font=("Arial", 12, "bold"))
        self.points_label.grid(row=0, column=2, sticky="e", padx=(20, 0))
        top_frame.grid_columnconfigure(2, weight=1) # Allow points label to push to the right

        # --- Main Paned Window (Attributes | Skills) ---
        paned_window = tk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Attributes Frame (Left) ---
        attr_frame = ttk.LabelFrame(paned_window, text="Attributes")
        paned_window.add(attr_frame, width=250)
        self._create_stats_widgets(attr_frame, self.character_data['attributes'], 'attribute')

        # --- Skills Frame (Right) ---
        skills_notebook = ttk.Notebook(paned_window)
        paned_window.add(skills_notebook)

        for attr, skill_list in D6_SKILLS_BY_ATTRIBUTE.items():
            skill_tab_frame = Frame(skills_notebook, padx=5, pady=5)
            skills_notebook.add(skill_tab_frame, text=attr.capitalize())
            # Create a dictionary of just the skills for this attribute to pass to the widget creator
            skills_for_tab = {skill: self.character_data['skills'][skill] for skill in sorted(skill_list)}
            self._create_stats_widgets(skill_tab_frame, skills_for_tab, 'skill')

        # --- Bottom Section (Save/Cancel) ---
        bottom_frame = Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        Button(bottom_frame, text="Save Character", command=self._save_character, bg="#4CAF50", fg="white").pack(side=tk.RIGHT)
        Button(bottom_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 10))


    def _create_stats_widgets(self, parent, stats_dict, stat_type):
        """Helper to create the label, buttons, and value for a list of stats."""
        for i, (stat_name, stat_value) in enumerate(stats_dict.items()):
            Label(parent, text=f"{stat_name.capitalize()}:").grid(row=i, column=0, sticky="w", pady=2)
            
            # Use a lambda to capture the current stat_name for the button command
            decr_button = Button(parent, text="-", command=lambda s=stat_name: self._change_stat(s, stat_type, -1))
            decr_button.grid(row=i, column=1, padx=(10, 2))

            value_label = Label(parent, text=f"{stat_value: >2}", width=3, relief="sunken")
            value_label.grid(row=i, column=2)
            self.value_labels[stat_name] = value_label # Store reference

            incr_button = Button(parent, text="+", command=lambda s=stat_name: self._change_stat(s, stat_type, 1))
            incr_button.grid(row=i, column=3, padx=2)

    def _change_stat(self, stat_name, stat_type, delta):
        """Handles the logic for increasing or decreasing a stat."""
        is_increase = delta > 0
        current_value = 0
        
        if stat_type == 'attribute':
            current_value = self.character_data['attributes'][stat_name]
        else: # skill
            current_value = self.character_data['skills'][stat_name]

        if is_increase:
            # --- Calculate Cost ---
            cost = 0
            if stat_type == 'attribute':
                cost = 2 * current_value # Cost to go from N to N+1 is 2N
            else: # skill
                cost = current_value + 1 # Cost to go from N to N+1 is N+1
            
            # --- Check and Apply ---
            if self.points_pool >= cost:
                self.points_pool -= cost
                if stat_type == 'attribute':
                    self.character_data['attributes'][stat_name] += 1
                else:
                    self.character_data['skills'][stat_name] += 1
            else:
                messagebox.showwarning("Not Enough Points", "You do not have enough points to raise this stat.")
                return

        else: # is_decrease
            # --- Check Minimums ---
            min_value = MIN_ATTRIBUTE if stat_type == 'attribute' else 0
            if current_value <= min_value:
                return

            # --- Calculate Refund ---
            refund = 0
            if stat_type == 'attribute':
                # The cost to get *from* the previous level (N-1) *to* the current level (N) was 2*(N-1)
                refund = 2 * (current_value - 1)
            else: # skill
                # The cost to get *from* the previous level (N-1) *to* the current level (N) was (N-1)+1 = N
                refund = current_value
            
            # --- Apply Change ---
            self.points_pool += refund
            if stat_type == 'attribute':
                self.character_data['attributes'][stat_name] -= 1
            else:
                self.character_data['skills'][stat_name] -= 1
        
        self._update_all_displays()

    def _update_all_displays(self):
        """Updates all stat values and the points pool label on the screen."""
        self.points_label.config(text=f"Points Remaining: {self.points_pool}")
        
        # Update all attribute and skill value labels
        for stat_name, label in self.value_labels.items():
            value = self.character_data['attributes'].get(stat_name, self.character_data['skills'].get(stat_name))
            if value is not None:
                label.config(text=f"{value: >2}")

    def _save_character(self):
        """Formats character data into YAML and saves it to a file."""
        # Update name from entry widget
        self.character_data['name'] = self.name_entry.get()

        # Create the final character sheet structure with some defaults
        physique_pips = self.character_data['attributes'].get('physique', 0)
        final_sheet = {
            'name': self.character_data['name'],
            'description': self.character_data['description'],
            'qualities': { 'gender': "Unknown", 'race': "Unknown", 'occupation': "Unknown", 'eyes': "Unknown", 'hair': "Unknown", 'skin': "Unknown" },
            'inventory': [],
            'attributes': self.character_data['attributes'],
            'skills': self.character_data['skills'],
            # Base HP on physique (e.g., physique pips + 5)
            'max_hp': physique_pips + 5,
            'cur_hp': physique_pips + 5,
            'statuses': [], 'memories': [], 'personality': [], 'attitudes': [], 'quotes': []
        }

        filepath = filedialog.asksaveasfilename(
            defaultextension=".yaml",
            filetypes=[("YAML Character Sheet", "*.yaml"), ("All Files", "*.*")],
            title="Save Character Sheet",
            initialfile=f"{self.character_data['name'].replace(' ', '_').lower()}.yaml"
        )
        
        if not filepath:
            return

        try:
            with open(filepath, 'w') as f:
                yaml.dump(final_sheet, f, default_flow_style=False, sort_keys=False)
            messagebox.showinfo("Success", f"Character sheet saved successfully to:\n{filepath}")
            self.destroy() # Close the creator window after saving
        except Exception as e:
            messagebox.showerror("Error Saving File", f"An error occurred while saving the file:\n{e}")