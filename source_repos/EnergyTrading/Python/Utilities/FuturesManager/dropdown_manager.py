import tkinter as tk
from tkinter import ttk
from ast import literal_eval
import pandas as pd


class DropdownManager:
    def __init__(self, app):
        self.app = app
        self.dropdown_widgets = []  # Main dropdowns
        self.comparison_dropdown_widgets = []  # Comparison dropdowns

    def create_new_dropdown(self, data, parent_frame, level=0, comparison=False):
        """Create a new dropdown for navigating hierarchical data."""
        if isinstance(data, dict):
            values = [str(key) for key in data.keys()]
            dropdown = ttk.Combobox(parent_frame, state="readonly", width=30)
            dropdown["values"] = values
            dropdown.pack(anchor="w", pady=2)

            if comparison:
                dropdown.bind(
                    "<<ComboboxSelected>>",
                    lambda event: self.on_select_secondary(event, dropdown, data, level),
                )
                self.comparison_dropdown_widgets = self.comparison_dropdown_widgets[:level] + [dropdown]
            else:
                dropdown.bind(
                    "<<ComboboxSelected>>",
                    lambda event: self.on_select(event, dropdown, data, level),
                )
                self.dropdown_widgets = self.dropdown_widgets[:level] + [dropdown]

        elif isinstance(data, pd.DataFrame):
            self.app.checkbox_manager.add_level_0_dropdown(data, comparison)

    def reset_below_level(self, level, comparison=False):
        """Reset widgets below the specified dropdown level."""
        widgets = self.comparison_dropdown_widgets if comparison else self.dropdown_widgets
        for widget in widgets[level + 1:]:
            widget.destroy()
        if comparison:
            self.comparison_dropdown_widgets = self.comparison_dropdown_widgets[:level + 1]
        else:
            self.dropdown_widgets = self.dropdown_widgets[:level + 1]

    def on_select(self, event, dropdown, data, level):
        """Handle navigation through main dropdowns."""
        selected_key = literal_eval(dropdown.get()) if dropdown.get().startswith("(") else dropdown.get()
        self.reset_below_level(level)
        self.app.data_manager.update_selected_keys(level, selected_key, comparison=False)
        self.create_new_dropdown(data[selected_key], self.app.dropdown_frame, level + 1)

    def on_select_secondary(self, event, dropdown, data, level):
        """Handle navigation through comparison dropdowns."""
        selected_key = literal_eval(dropdown.get()) if dropdown.get().startswith("(") else dropdown.get()
        self.reset_below_level(level, comparison=True)
        self.app.data_manager.update_selected_keys(level, selected_key, comparison=True)
        self.create_new_dropdown(data[selected_key], self.app.comparison_dropdown_frame, level + 1, comparison=True)
