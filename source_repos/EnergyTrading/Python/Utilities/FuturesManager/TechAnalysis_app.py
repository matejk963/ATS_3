# -*- coding: utf-8 -*-
"""
Created on Thu Jan 16 17:28:32 2025

@author: krajcovic
"""

import pickle
import tkinter as tk
from tkinter import ttk
from ast import literal_eval
import pandas as pd
import matplotlib.pyplot as plt
plt.ioff()  # Disable interactive plotting

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Load the data dictionary
file_path = r'W:\Data\Data\Futures\data_dict.pkl'

with open(file_path, 'rb') as f:
    data_dict = pickle.load(f)


class DictExplorerApp:
    def __init__(self, root, data):
        self.root = root
        self.data = data
        self.current_data = data
        self.selected_keys = []  # Track selected keys
        self.dropdown_widgets = []  # Initialize dropdown widgets
        self.plot_canvas = None  # For Matplotlib plot
    
        # Main layout
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
    
        # Dropdown and button layout
        self.top_frame = tk.Frame(self.main_frame)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
    
        # Left frame for dropdowns
        self.dropdown_frame = tk.Frame(self.top_frame)
        self.dropdown_frame.pack(side=tk.LEFT, padx=5, pady=5)
    
        # Create the first dropdown
        self.create_new_dropdown(self.current_data, self.dropdown_frame)
    
        # Add "Compare" button aligned with the first dropdown
        self.compare_button = tk.Button(self.top_frame, text="Compare", command=self.add_comparison_dropdown)
        self.compare_button.pack(side=tk.LEFT, padx=5, pady=5)
    
        # Create the second dropdown frame for comparison (aligned with the "Compare" button)
        self.comparison_dropdown_frame = tk.Frame(self.top_frame)
        self.comparison_dropdown_frame.pack(side=tk.LEFT, padx=5, pady=5)
    
        # Chart and checkboxes for the main plot
        self.main_chart_frame = tk.Frame(self.main_frame)
        self.main_chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        self.main_checkbox_frame = tk.Frame(self.main_chart_frame, width=200)
        self.main_checkbox_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
    
        self.main_plot_frame = tk.Frame(self.main_chart_frame)
        self.main_plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # Chart and checkboxes for the comparison plot
        self.comparison_chart_frame = tk.Frame(self.main_frame)
        self.comparison_chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        self.comparison_checkbox_frame = tk.Frame(self.comparison_chart_frame, width=200)
        self.comparison_checkbox_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
    
        self.comparison_plot_frame = tk.Frame(self.comparison_chart_frame)
        self.comparison_plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # Unified slider frame
        self.slider_frame = None
    
        # Initialize date variables (empty until sliders are added)
        self.start_date_var = tk.StringVar(value="")
        self.end_date_var = tk.StringVar(value="")
    
        self.comparison_dropdown_widgets = []
        
    @staticmethod
    def calculate_dropdown_width(values):
        """Calculate the width for the dropdown based on the longest string in values."""
        if not values:
            return 10  # Default width if no values
        longest_value = max(values, key=len)
        return len(longest_value) + 2  # Add padding for better display
    
    def create_new_dropdown(self, data, parent_frame, level=0, comparison=False):
        """Create a new dropdown for the given data."""
        if isinstance(data, dict):
            values = [str(key) for key in data.keys()]
            width = self.calculate_dropdown_width(values)  # Dynamically calculate width
            dropdown = ttk.Combobox(parent_frame, state="readonly", width=width)
            dropdown["values"] = values
            dropdown.pack(anchor="w", pady=2)

            # Bind the event based on whether it's a comparison dropdown
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
            # Populate a dropdown for column selection
            self.populate_column_dropdown(data, parent_frame, level, comparison=comparison)

    def populate_column_dropdown(self, df, parent_frame, level, comparison=False):
        """Populate a dropdown for selecting columns in a DataFrame."""
        if isinstance(df.columns, pd.MultiIndex):
            unique_columns = list(df.columns.get_level_values(0).unique())
        else:
            unique_columns = list(df.columns.unique())

        width = self.calculate_dropdown_width(unique_columns)  # Dynamically calculate width
        dropdown = ttk.Combobox(parent_frame, state="readonly", width=width)
        dropdown["values"] = unique_columns
        dropdown.pack(anchor="w", pady=2)

        # Bind event based on whether it's a comparison dropdown
        dropdown.bind(
            "<<ComboboxSelected>>",
            lambda event: self.on_column_selected(event, df, level, comparison)
        )

        if comparison:
            self.comparison_dropdown_widgets = self.comparison_dropdown_widgets[:level] + [dropdown]
        else:
            self.dropdown_widgets = self.dropdown_widgets[:level] + [dropdown]

    def on_column_selected(self, event, df, level, comparison=False):
        """Handle selection of a column from the column-level dropdown."""
        dropdown = event.widget
        selected_column = dropdown.get()
    
        # Reset lower-level widgets and plots
        self.reset_below_level(level, comparison)
    
        # Filter the DataFrame based on the selected column
        if isinstance(df.columns, pd.MultiIndex):
            filtered_df = df.loc[:, df.columns.get_level_values(0) == selected_column]
            filtered_df.columns = filtered_df.columns.droplevel(0)
        else:
            filtered_df = df[[selected_column]]
    
        # Set the filtered data
        if comparison:
            self.comparison_filtered_df = filtered_df
            self.add_column_checkboxes(filtered_df, comparison=True)
        else:
            self.current_filtered_df = filtered_df
            self.add_column_checkboxes(filtered_df, comparison=False)
    
        # Add a unified date range slider for both plots
        combined_index = pd.Index([])
        if hasattr(self, "current_filtered_df") and self.current_filtered_df is not None:
            combined_index = combined_index.union(self.current_filtered_df.index, sort=False)
        if hasattr(self, "comparison_filtered_df") and self.comparison_filtered_df is not None:
            combined_index = combined_index.union(self.comparison_filtered_df.index, sort=False)
    
        self.add_unified_date_range_slider()
    
        # Trigger plotting
        self.update_unified_plot_with_slider(combined_index)


    def on_top_level_column_select(self, event, df, comparison=False):
        """Handle column selection in dropdown for main or comparison plots."""
        dropdown = event.widget
        selected_column = dropdown.get()
    
        if isinstance(df.columns, pd.MultiIndex):
            # Filter for the selected top-level column
            filtered_df = df.loc[:, df.columns.get_level_values(0) == selected_column]
            filtered_df.columns = filtered_df.columns.droplevel(0)
        else:
            filtered_df = df[[selected_column]]
    
        # Defer plotting until column checkboxes and sliders are configured
        if comparison:
            self.comparison_filtered_df = filtered_df
            self.add_date_range_slider(filtered_df, selected_column, comparison=True)
            self.add_column_checkboxes(filtered_df, comparison=True)
        else:
            self.current_filtered_df = filtered_df
            self.add_date_range_slider(filtered_df, selected_column)
            self.add_column_checkboxes(filtered_df)

    def on_select(self, event, dropdown, data, level):
        """Handle navigation through dropdown selections."""
        selected_key_str = dropdown.get()
        selected_key = literal_eval(selected_key_str) if selected_key_str.startswith("(") else selected_key_str
    
        # Reset dropdowns below the current level
        self.reset_below_level(level)
    
        # Update selected keys
        if level < len(self.selected_keys):
            self.selected_keys = self.selected_keys[:level]
        self.selected_keys.append(selected_key)
    
        # Navigate deeper
        next_data = data[selected_key]
        self.create_new_dropdown(next_data, self.dropdown_frame, level + 1)
    
    def on_select_secondary(self, event, dropdown, data, level):
        """Handle navigation through secondary dropdown selections."""
        selected_key_str = dropdown.get()
        selected_key = literal_eval(selected_key_str) if selected_key_str.startswith("(") else selected_key_str
    
        # Reset dropdowns below the current level
        self.reset_below_level(level, comparison=True)
    
        # Update selected keys
        if level < len(self.selected_comparison_keys):
            self.selected_comparison_keys = self.selected_comparison_keys[:level]
        self.selected_comparison_keys.append(selected_key)
    
        # Navigate deeper
        next_data = data[selected_key]
        self.create_new_dropdown(next_data, self.comparison_dropdown_frame, level + 1, comparison=True)

            
    def reset_below_level(self, level, comparison=False):
        """Reset all dropdowns and widgets below the specified level."""
        if comparison:
            for widget in self.comparison_dropdown_widgets[level + 1:]:
                widget.destroy()
            self.comparison_dropdown_widgets = self.comparison_dropdown_widgets[:level + 1]
    
            if hasattr(self, "comparison_plot_canvas") and self.comparison_plot_canvas:
                self.comparison_plot_canvas.get_tk_widget().destroy()
                self.comparison_plot_canvas = None
    
            if hasattr(self, "comparison_slider_frame") and self.comparison_slider_frame:
                self.comparison_slider_frame.destroy()
                self.comparison_slider_frame = None
    
            self.comparison_filtered_df = None
        else:
            for widget in self.dropdown_widgets[level + 1:]:
                widget.destroy()
            self.dropdown_widgets = self.dropdown_widgets[:level + 1]
    
            if hasattr(self, "plot_canvas") and self.plot_canvas:
                self.plot_canvas.get_tk_widget().destroy()
                self.plot_canvas = None
    
            if hasattr(self, "slider_frame") and self.slider_frame:
                self.slider_frame.destroy()
                self.slider_frame = None
    
            self.current_filtered_df = None

    # Add slider for daterange
    def update_plot_with_slider(self, df, selected_column, index_values, comparison=False):
        """Update the plot based on slider values."""
        start_date = index_values[
            int(self.comparison_start_slider.get() if comparison else self.start_slider.get())
        ]
        end_date = index_values[
            int(self.comparison_end_slider.get() if comparison else self.end_slider.get())
        ]
    
        # Filter data by date range
        filtered_df = df.loc[start_date:end_date]
    
        # Generate dynamic titles
        if comparison:
            last_key = self.selected_comparison_keys[-1] if self.selected_comparison_keys else selected_column
            level_0_value = self.selected_comparison_keys[0] if self.selected_comparison_keys else ""
            comparison_title = f"Comparison Plot: {last_key} | {level_0_value}"
            self.update_plots(
                main_df=self.current_filtered_df if hasattr(self, "current_filtered_df") else None,
                comparison_df=filtered_df,
                comparison_title=comparison_title,
            )
        else:
            last_key = self.selected_keys[-1] if self.selected_keys else selected_column
            level_0_value = self.selected_keys[0] if self.selected_keys else ""
            main_title = f"Main Plot: {last_key} | {level_0_value}"
            self.update_plots(
                main_df=filtered_df,
                comparison_df=self.comparison_filtered_df if hasattr(self, "comparison_filtered_df") else None,
                main_title=main_title,
            )
            
    def add_column_checkboxes(self, df, comparison=False):
        """Add checkboxes for selecting columns and update the plot accordingly."""
        # Determine the target frame
        target_frame = self.comparison_checkbox_frame if comparison else self.main_checkbox_frame
    
        # Clear existing checkboxes in the target frame
        for widget in target_frame.winfo_children():
            widget.destroy()
    
        # Select columns with default value True
        selected_columns = {col: tk.BooleanVar(value=True) for col in df.columns}
    
        # Add a label to distinguish checkboxes
        label_text = "Columns:" if comparison else "Columns:"
        tk.Label(target_frame, text=label_text).pack(anchor="w")
    
        # Add a checkbox for each column
        for col, var in selected_columns.items():
            checkbox = tk.Checkbutton(
                target_frame,
                text=col,
                variable=var,
                command=lambda: self.update_plot_columns(selected_columns, comparison=comparison),
            )
            checkbox.pack(anchor="w", padx=5, pady=2)
    
        # Trigger an initial update to the plots
        self.update_plot_columns(selected_columns, comparison=comparison)

    def add_date_range_slider(self, df, selected_column, comparison=False):
        """Add sliders to filter the DataFrame by date range."""
        # Destroy the existing slider frame before creating a new one
        if comparison:
            if hasattr(self, "comparison_slider_frame") and self.comparison_slider_frame:
                self.comparison_slider_frame.destroy()
                self.comparison_slider_frame = None
        else:
            if hasattr(self, "slider_frame") and self.slider_frame:
                self.slider_frame.destroy()
                self.slider_frame = None
    
        # Filter non-NaN values
        non_nan_df = df.copy()
        index_values = non_nan_df.index
    
        # Create the slider frame below the respective plot
        if comparison:
            self.comparison_slider_frame = tk.Frame(self.main_frame)
            self.comparison_slider_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(5, 10))
            frame = self.comparison_slider_frame
        else:
            self.slider_frame = tk.Frame(self.main_frame)
            self.slider_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(5, 10))
            frame = self.slider_frame
    
        # Create start slider
        start_label = tk.Label(frame, text="Start Date:")
        start_label.pack(side=tk.LEFT, padx=5)
    
        start_slider = tk.Scale(
            frame,
            from_=0,
            to=len(index_values) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            showvalue=True,
            command=lambda value: self.update_start_date(non_nan_df, selected_column, index_values, value, comparison),
        )
        start_slider.set(0)
        start_slider.pack(side=tk.LEFT, padx=5)
    
        # Initialize start date variable
        if comparison:
            self.comparison_start_slider = start_slider
            self.comparison_start_date_var = tk.StringVar(value=str(index_values[0]))
            tk.Label(frame, textvariable=self.comparison_start_date_var).pack(side=tk.LEFT, padx=5)
        else:
            self.start_slider = start_slider
            self.start_date_var = tk.StringVar(value=str(index_values[0]))
            tk.Label(frame, textvariable=self.start_date_var).pack(side=tk.LEFT, padx=5)
    
        # Create end slider
        end_label = tk.Label(frame, text="End Date:")
        end_label.pack(side=tk.LEFT, padx=5)
    
        end_slider = tk.Scale(
            frame,
            from_=0,
            to=len(index_values) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            showvalue=True,
            command=lambda value: self.update_end_date(non_nan_df, selected_column, index_values, value, comparison),
        )
        end_slider.set(len(index_values) - 1)
        end_slider.pack(side=tk.LEFT, padx=5)
    
        # Initialize end date variable
        if comparison:
            self.comparison_end_slider = end_slider
            self.comparison_end_date_var = tk.StringVar(value=str(index_values[-1]))
            tk.Label(frame, textvariable=self.comparison_end_date_var).pack(side=tk.LEFT, padx=5)
        else:
            self.end_slider = end_slider
            self.end_date_var = tk.StringVar(value=str(index_values[-1]))
            tk.Label(frame, textvariable=self.end_date_var).pack(side=tk.LEFT, padx=5)
    
        # Update the plot with initial slider values
        self.update_plot_with_slider(non_nan_df, selected_column, index_values, comparison)
        
    def add_unified_date_range_slider(self):
        """Add a single set of sliders for both plots."""
        # Destroy any existing unified slider frame
        if hasattr(self, "unified_slider_frame") and self.unified_slider_frame:
            self.unified_slider_frame.destroy()
    
        # Determine the combined date range
        combined_index = pd.Index([])
        if hasattr(self, "current_filtered_df") and self.current_filtered_df is not None:
            combined_index = combined_index.union(self.current_filtered_df.index)
        if hasattr(self, "comparison_filtered_df") and self.comparison_filtered_df is not None:
            combined_index = combined_index.union(self.comparison_filtered_df.index)
        
        # Ensure non-empty index
        if combined_index.empty:
            return
    
        # Sort the index
        combined_index = combined_index.sort_values()
    
        # Create the slider frame below the respective plots
        self.unified_slider_frame = tk.Frame(self.main_frame)
        self.unified_slider_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(5, 10))
    
        frame = self.unified_slider_frame
    
        # Create start slider
        start_label = tk.Label(frame, text="Start Date:")
        start_label.pack(side=tk.LEFT, padx=5)
    
        self.start_slider = tk.Scale(
            frame,
            from_=0,
            to=len(combined_index) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            showvalue=True,
            command=lambda value: self.update_unified_slider_dates(combined_index, value, "start"),
        )
        self.start_slider.set(0)
        self.start_slider.pack(side=tk.LEFT, padx=5)
    
        # Initialize start date variable
        self.start_date_var = tk.StringVar(value=str(combined_index[0]))
        tk.Label(frame, textvariable=self.start_date_var).pack(side=tk.LEFT, padx=5)
    
        # Create end slider
        end_label = tk.Label(frame, text="End Date:")
        end_label.pack(side=tk.LEFT, padx=5)
    
        self.end_slider = tk.Scale(
            frame,
            from_=0,
            to=len(combined_index) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            showvalue=True,
            command=lambda value: self.update_unified_slider_dates(combined_index, value, "end"),
        )
        self.end_slider.set(len(combined_index) - 1)
        self.end_slider.pack(side=tk.LEFT, padx=5)
    
        # Initialize end date variable
        self.end_date_var = tk.StringVar(value=str(combined_index[-1]))
        tk.Label(frame, textvariable=self.end_date_var).pack(side=tk.LEFT, padx=5)
    
        # Update the plots with initial slider values
        self.update_unified_plot_with_slider(combined_index)



    def update_start_date(self, df, selected_column, index_values, value, comparison=False):
        """Update the start date from the slider."""
        if comparison:
            self.comparison_start_date_var.set(str(index_values[int(value)]))
            self.update_plot_with_slider(df, selected_column, index_values, comparison=True)
        else:
            self.start_date_var.set(str(index_values[int(value)]))
            self.update_plot_with_slider(df, selected_column, index_values, comparison=False)
    
    
    def update_end_date(self, df, selected_column, index_values, value, comparison=False):
        """Update the end date from the slider."""
        if comparison:
            self.comparison_end_date_var.set(str(index_values[int(value)]))
            self.update_plot_with_slider(df, selected_column, index_values, comparison=True)
        else:
            self.end_date_var.set(str(index_values[int(value)]))
            self.update_plot_with_slider(df, selected_column, index_values, comparison=False)
            
    def update_unified_slider_dates(self, index_values, value, slider_type):
        """Update the start or end date based on slider value."""
        if slider_type == "start":
            self.start_date_var.set(str(index_values[int(value)]))
        elif slider_type == "end":
            self.end_date_var.set(str(index_values[int(value)]))
        # Update both plots with the new slider values
        self.update_unified_plot_with_slider(index_values)
        

    def update_plot_columns(self, selected_columns, comparison=False):
        """Update the plot based on selected columns for primary or comparison plots."""
        if comparison:
            if hasattr(self, "comparison_filtered_df"):
                selected_cols = [col for col, var in selected_columns.items() if var.get()]
                if selected_cols:
                    filtered_df = self.comparison_filtered_df[selected_cols]
                    last_key = self.selected_comparison_keys[-1] if self.selected_comparison_keys else ""
                    level_0_value = self.selected_comparison_keys[0] if self.selected_comparison_keys else ""
                    comparison_title = f"Comparison Plot: {last_key} | {level_0_value}"
                    self.update_plots(
                        main_df=self.current_filtered_df,
                        comparison_df=filtered_df,
                        comparison_title=comparison_title,
                    )
        else:
            if hasattr(self, "current_filtered_df"):
                selected_cols = [col for col, var in selected_columns.items() if var.get()]
                if selected_cols:
                    filtered_df = self.current_filtered_df[selected_cols]
                    last_key = self.selected_keys[-1] if self.selected_keys else ""
                    level_0_value = self.selected_keys[0] if self.selected_keys else ""
                    main_title = f"Main Plot: {last_key} | {level_0_value}"
                    self.update_plots(
                        main_df=filtered_df,
                        main_title=main_title,
                    )

    def update_unified_plot_with_slider(self, combined_index):
        """Update both plots based on the unified slider's date range."""
        if combined_index.empty:
            print("Warning: Combined index is empty. Cannot update plots.")
            return
    
        # Get slider values
        start_date = combined_index[int(self.start_slider.get())]
        end_date = combined_index[int(self.end_slider.get())]
    
        # Filter data for main plot
        main_df = None
        if hasattr(self, "current_filtered_df") and self.current_filtered_df is not None:
            main_df = self.current_filtered_df.loc[start_date:end_date]
    
        # Filter data for comparison plot
        comparison_df = None
        if hasattr(self, "comparison_filtered_df") and self.comparison_filtered_df is not None:
            comparison_df = self.comparison_filtered_df.loc[start_date:end_date]
    
        # Update both plots
        self.update_plots(
            main_df=main_df,
            main_title="Main Plot",
            comparison_df=comparison_df,
            comparison_title="Comparison Plot"
        )


                
    def plot_main(self, df, title, plot_height=4):  # Reduced plot height
        """Plot the main DataFrame."""
        if hasattr(self, "plot_canvas") and self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None
    
        plt.close('all')
    
        if df.empty:
            print(f"Warning: No data to plot for {title}")
            return
    
        fig, ax = plt.subplots(figsize=(8, plot_height))  # Adjusted width and height
        for column in df.columns:
            df[column].plot(ax=ax, label=column)
            last_index = df.index[-1]
            last_value = df[column].iloc[-1]
            ax.text(
                last_index + pd.Timedelta(days=1),
                last_value,
                f"{last_value:.2f}",
                color=ax.lines[-1].get_color(),
                fontsize=10,
                ha="left",
                va="center",
            )
    
        ax.set_title(title, fontsize=14)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.set_xlabel("Date")
        ax.set_ylabel("Values")
        ax.grid(True)
        ax.legend()
    
        self.plot_canvas = FigureCanvasTkAgg(fig, master=self.main_plot_frame)
        self.plot_canvas.draw()
        self.plot_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    
    def plot_comparison(self, df, title, plot_height=2):  # Smaller height for comparison
        """Plot the comparison DataFrame."""
        if hasattr(self, "comparison_plot_canvas") and self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
            self.comparison_plot_canvas = None
    
        plt.close('all')
    
        if df.empty:
            print(f"Warning: No data to plot for {title}")
            return
    
        fig, ax = plt.subplots(figsize=(8, plot_height))  # Adjusted width and height
        for column in df.columns:
            df[column].plot(ax=ax, label=column)
            last_index = df.index[-1]
            last_value = df[column].iloc[-1]
            ax.text(
                last_index + pd.Timedelta(days=1),
                last_value,
                f"{last_value:.2f}",
                color=ax.lines[-1].get_color(),
                fontsize=10,
                ha="left",
                va="center",
            )
    
        ax.set_title(title, fontsize=14)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.set_xlabel("Date")
        ax.set_ylabel("Values")
        ax.grid(True)
        ax.legend()
    
        self.comparison_plot_canvas = FigureCanvasTkAgg(fig, master=self.comparison_plot_frame)
        self.comparison_plot_canvas.draw()
        self.comparison_plot_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


    def update_plots(self, main_df=None, main_title=None, comparison_df=None, comparison_title=None):
        """Manage plotting of main and comparison plots, and adjust layout."""
        # Clear existing plots if necessary
        if hasattr(self, "plot_canvas") and self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None
    
        if hasattr(self, "comparison_plot_canvas") and self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
            self.comparison_plot_canvas = None
    
        # Generate dynamic titles if not provided
        if not main_title and self.selected_keys:
            main_title = f"Main Plot: {self.selected_keys[-1]} | {self.selected_keys[0]}"
        if not comparison_title and hasattr(self, "selected_comparison_keys") and self.selected_comparison_keys:
            comparison_title = f"Comparison Plot: {self.selected_comparison_keys[-1]} | {self.selected_comparison_keys[0]}"
    
        # Adjust the height of the main plot based on whether a comparison plot exists
        plot_height = 4 if comparison_df is not None else 6
    
        # Plot the main DataFrame
        if main_df is not None:
            self.plot_main(main_df, main_title, plot_height=plot_height)
    
        # Plot the comparison DataFrame
        if comparison_df is not None:
            self.plot_comparison(comparison_df, comparison_title)

    # Comparison plot    
    def add_comparison_dropdown(self):
        """Create secondary dropdowns for comparison."""
        # Clear any existing widgets in the comparison dropdown frame
        if hasattr(self, "comparison_dropdown_frame"):
            for widget in self.comparison_dropdown_frame.winfo_children():
                widget.destroy()
        else:
            # Create the comparison dropdown frame next to the "Compare" button
            self.comparison_dropdown_frame = tk.Frame(self.dropdown_frame)
            self.comparison_dropdown_frame.pack(side=tk.RIGHT, padx=5, pady=5)
    
        # Initialize selected_comparison_keys and dropdown widgets
        self.selected_comparison_keys = []
        self.comparison_dropdown_widgets = []
    
        # Create the first comparison dropdown
        self.create_new_dropdown(self.data, self.comparison_dropdown_frame, level=0, comparison=True)
    
        # Create a comparison plot frame if it doesn't exist
        if not hasattr(self, "comparison_plot_frame"):
            self.comparison_plot_frame = tk.Frame(self.main_frame)
            self.comparison_plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)


    def add_comparison_plot(self, df):
        """Add a secondary plot below the primary plot."""
        if hasattr(self, "comparison_plot_frame"):
            self.comparison_plot_frame.destroy()
        
        self.comparison_plot_frame = tk.Frame(self.plot_frame)
        self.comparison_plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # Filter columns for default unchecked checkboxes
        selected_columns = {col: tk.BooleanVar(value=False) for col in df.columns}
        self.add_column_checkboxes(df, selected_columns, comparison=True)
    
        # Default plot with no columns selected
        self.update_plot_columns(selected_columns, comparison=True)




    def clear_plot(self):
        if self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None
            
    def on_closing(self):
        """Handle application cleanup on close."""
        # Destroy Matplotlib plot canvases
        if hasattr(self, "plot_canvas") and self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None
        if hasattr(self, "comparison_plot_canvas") and self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
            self.comparison_plot_canvas = None
    
        # Destroy slider frames
        if hasattr(self, "slider_frame") and self.slider_frame:
            self.slider_frame.destroy()
            self.slider_frame = None
        if hasattr(self, "comparison_slider_frame") and self.comparison_slider_frame:
            self.comparison_slider_frame.destroy()
            self.comparison_slider_frame = None
    
        # Destroy all dropdown widgets
        for widget in self.dropdown_widgets:
            widget.destroy()
        self.dropdown_widgets = []
        for widget in self.comparison_dropdown_widgets:
            widget.destroy()
        self.comparison_dropdown_widgets = []
    
        # Quit and destroy the root Tkinter window
        self.root.quit()  # Exit the mainloop
        self.root.destroy()  # Destroy all Tkinter objects




    def reset(self):
        """Reset the application to its initial state."""
        self.current_data = self.data
        self.selected_keys = []
        self.selected_comparison_keys = []
    
        # Destroy all dropdown widgets
        for widget in self.dropdown_widgets:
            widget.destroy()
        self.dropdown_widgets = []
    
        for widget in self.comparison_dropdown_widgets:
            widget.destroy()
        self.comparison_dropdown_widgets = []
    
        # Destroy all plot canvases
        if hasattr(self, "plot_canvas") and self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None
    
        if hasattr(self, "comparison_plot_canvas") and self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
            self.comparison_plot_canvas = None
    
        # Clear both checkbox frames
        for widget in self.main_checkbox_frame.winfo_children():
            widget.destroy()
    
        for widget in self.comparison_checkbox_frame.winfo_children():
            widget.destroy()
    
        # Destroy all slider frames
        if hasattr(self, "slider_frame") and self.slider_frame:
            self.slider_frame.destroy()
            self.slider_frame = None
    
        if hasattr(self, "comparison_slider_frame") and self.comparison_slider_frame:
            self.comparison_slider_frame.destroy()
            self.comparison_slider_frame = None
    
        # Recreate the initial dropdown
        self.create_new_dropdown(self.current_data, self.dropdown_frame)


# Initialize and run the Tkinter app
def run_dict_explorer(data):
    root = tk.Tk()
    root.title("Dictionary Explorer")
    app = DictExplorerApp(root, data)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)  # Bind cleanup to window close
    root.mainloop()




run_dict_explorer(data_dict)
