import tkinter as tk
from tkinter import ttk

class DropdownGroup:
    """A class to create and manage multiple dropdowns in a Tkinter window."""
    def __init__(self, parent, dropdown_data, callback=None):
        """
        Initialize dropdowns.

        :param parent: The Tkinter parent widget (e.g., a frame or root window).
        :param dropdown_data: A dictionary where keys are labels and values are lists of dropdown options.
        :param callback: A function to call when a dropdown selection changes.
        """
        self.parent = parent
        self.dropdown_vars = {}  # Dictionary to store dropdown variables
        self.dropdowns = {}  # Dictionary to store dropdown widgets
        self.callback = callback  # Store the callback function

        # Loop through the provided data and create dropdowns dynamically
        for idx, (label, options) in enumerate(dropdown_data.items()):
            ttk.Label(parent, text=label).grid(row=idx, column=0, padx=10, pady=5, sticky="w")
            var = tk.StringVar()  # Create a variable to store the selection
            dropdown = ttk.Combobox(parent, textvariable=var, values=options, state="readonly" if options else "normal")
            dropdown.grid(row=idx, column=1, padx=10, pady=5, sticky="ew")

            # Store the variable and widget in dictionaries
            self.dropdown_vars[label] = var
            self.dropdowns[label] = dropdown

            # If a callback function is provided, bind it to dropdown selection change
            if callback:
                dropdown.bind("<<ComboboxSelected>>", lambda event, key=label: callback(key))

    def get_selections(self):
        """Retrieve the selected values from all dropdowns, ensuring manually entered values are captured correctly."""
        selections = {}
        for label, var in self.dropdown_vars.items():
            widget = self.dropdowns[label]

            # Check if the widget is manually editable
            if widget["state"] == "normal":
                selections[label] = widget.get().strip()  # Always fetch directly from the combobox
            else:
                selections[label] = var.get().strip()  # Use stored StringVar

            # Debugging print to check if Period is correctly retrieved
            # print(f"DEBUG: {label} = '{selections[label]}'")
        return selections
    
    def update_dropdown_options(self, label, options, allow_typing=False):
        """Update dropdown options dynamically and allow manual input if needed."""
        if label in self.dropdowns:
            dropdown = self.dropdowns[label]
            dropdown["values"] = options
            self.dropdown_vars[label].set("")  # Reset selection

            # Allow manual input for certain selections
            if allow_typing:
                dropdown.config(state="normal")
            else:
                dropdown.config(state="readonly")
