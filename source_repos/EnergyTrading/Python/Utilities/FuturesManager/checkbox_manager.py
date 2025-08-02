import tkinter as tk
from tkinter import ttk
import pandas as pd

class CheckboxManager:
    def __init__(self, app):
        self.app = app
        self.level_0_selection = tk.StringVar(value="")

    def add_level_0_dropdown(self, df, comparison=False):
        """
        Add a dropdown for selecting level-0 column values.
        :param df: DataFrame with MultiIndex columns.
        :param comparison: Whether this dropdown is for the comparison plot.
        """
        # Determine the target frame
        target_frame = (
            self.app.comparison_checkbox_frame
            if comparison
            else self.app.main_checkbox_frame
        )

        # Clear existing widgets in the target frame
        for widget in target_frame.winfo_children():
            widget.destroy()

        # Extract unique level-0 column values
        if isinstance(df.columns, pd.MultiIndex):
            level_0_values = list(df.columns.get_level_values(0).unique())
        else:
            level_0_values = list(df.columns)

        # Debug: Print level-0 values
        print(f"Level-0 values for dropdown: {level_0_values}")

        # Add a label for the dropdown
        tk.Label(target_frame, text="Select Level-0 Column:").pack(anchor="w", pady=(5, 2))

        # Create the dropdown for level-0 selection
        dropdown = ttk.Combobox(
            target_frame,
            state="readonly",
            values=level_0_values,
            width=self.app.calculate_dropdown_width(level_0_values),
        )
        dropdown.pack(anchor="w", pady=5)
        dropdown.bind(
            "<<ComboboxSelected>>",
            lambda event: self.update_checkboxes(df, dropdown.get(), comparison),
        )

        # Initialize the dropdown with the first level-0 value
        if level_0_values:
            dropdown.current(0)  # Set the first value as selected
            self.update_checkboxes(df, level_0_values[0], comparison)


    def update_plot_columns(self, selected_columns, comparison=False):
        """
        Update the plot based on selected columns.
        :param selected_columns: Dictionary of selected columns with BooleanVars.
        :param comparison: Whether to update the comparison plot.
        """
        # Get the selected columns
        selected_cols = [col for col, var in selected_columns.items() if var.get()]

        # Debug: Print selected columns
        print(f"Selected columns for {'comparison' if comparison else 'main'} plot: {selected_cols}")

        if not selected_cols:
            print("No columns selected. Nothing to plot.")
            return

        # Filter the appropriate DataFrame
        if comparison:
            if self.app.data_manager.comparison_filtered_df is not None:
                filtered_df = self.app.data_manager.comparison_filtered_df[selected_cols]
                print(f"Filtered DataFrame for comparison plot:\n{filtered_df.head()}")
                self.app.plot_manager.plot_comparison(
                    filtered_df, title=f"Comparison Plot ({self.level_0_selection.get()})"
                )
        else:
            if self.app.data_manager.current_filtered_df is not None:
                filtered_df = self.app.data_manager.current_filtered_df[selected_cols]
                print(f"Filtered DataFrame for main plot:\n{filtered_df.head()}")
                self.app.plot_manager.plot_main(
                    filtered_df, title=f"Main Plot ({self.level_0_selection.get()})"
                )


            
    def update_checkboxes(self, df, level_0_value, comparison=False):
        """
        Update checkboxes based on the selected level-0 column value.
        :param df: DataFrame containing MultiIndex columns.
        :param level_0_value: The selected level-0 column value.
        :param comparison: Whether to update checkboxes for the comparison plot.
        """
        # Determine the target frame
        target_frame = (
            self.app.comparison_checkbox_frame
            if comparison
            else self.app.main_checkbox_frame
        )

        # Clear existing checkboxes in the target frame
        for widget in target_frame.winfo_children():
            widget.destroy()

        # Filter columns by the selected level-0 value
        if isinstance(df.columns, pd.MultiIndex):
            filtered_df = df.loc[:, df.columns.get_level_values(0) == level_0_value]
            filtered_df.columns = filtered_df.columns.droplevel(0)  # Drop level-0 for checkbox display
        else:
            filtered_df = df[[level_0_value]]

        # Debug: Print filtered DataFrame
        print(f"Filtered DataFrame for level-0 value '{level_0_value}':\n{filtered_df.head()}")

        # Initialize the selected columns dictionary
        selected_columns = {col: tk.BooleanVar(value=True) for col in filtered_df.columns}
        if comparison:
            self.selected_columns_comparison = selected_columns
        else:
            self.selected_columns_main = selected_columns

        # Add a label to distinguish checkboxes
        label_text = "Columns (Comparison):" if comparison else "Columns (Main):"
        tk.Label(target_frame, text=label_text).pack(anchor="w", pady=(5, 2))

        # Create a checkbox for each filtered column
        for col, var in selected_columns.items():
            checkbox = tk.Checkbutton(
                target_frame,
                text=col,
                variable=var,
                command=lambda: self.update_plot_columns(selected_columns, comparison),
            )
            checkbox.pack(anchor="w", padx=5, pady=2)

        # Trigger an initial update to the plots
        self.update_plot_columns(selected_columns, comparison)

