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
file_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\temp\data_dict.pkl'

with open(file_path, 'rb') as f:
    data_dict = pickle.load(f)


class DictExplorerApp:
    def __init__(self, root, data):
        self.root = root
        self.data = data
        self.current_data = data
        self.dropdown_widgets = []  # Track dropdowns for dynamic resetting
        self.selected_keys = []
        self.slider_frame = None  # Frame for the date range slider
        self.plot_canvas = None  # To hold the Matplotlib plot

        # Frame for dropdowns
        self.dropdown_frame = tk.Frame(root)
        self.dropdown_frame.pack(anchor="w", padx=5, pady=5)

        # Display for plots
        self.plot_frame = tk.Frame(root)
        self.plot_frame.pack(padx=5, pady=5)

        # Reset button
        self.reset_button = tk.Button(root, text="Reset", command=self.reset)
        self.reset_button.pack(pady=5)

        self.create_new_dropdown(self.current_data, self.dropdown_frame)
        
        


    def create_new_dropdown(self, data, parent_frame, level=0):
        """Create a new dropdown for the given data."""
        if isinstance(data, dict):
            dropdown = ttk.Combobox(parent_frame, state="readonly")
            dropdown["values"] = [str(key) for key in data.keys()]
            dropdown.pack(anchor="w", pady=2)
            dropdown.bind("<<ComboboxSelected>>", lambda event: self.on_select(event, dropdown, data, level))
            self.dropdown_widgets = self.dropdown_widgets[:level] + [dropdown]
        elif isinstance(data, pd.DataFrame):
            self.populate_column_dropdown(data, parent_frame, level)

    def populate_column_dropdown(self, df, parent_frame, level):
        """Populate a dropdown for unique level 0 column names from the DataFrame."""
        if isinstance(df.columns, pd.MultiIndex):
            unique_columns = list(df.columns.get_level_values(0).unique())
        else:
            unique_columns = list(df.columns.unique())

        dropdown = ttk.Combobox(parent_frame, state="readonly")
        dropdown["values"] = unique_columns
        dropdown.pack(anchor="w", pady=2)
        dropdown.bind("<<ComboboxSelected>>", lambda event: self.on_top_level_column_select(event, df))
        self.dropdown_widgets = self.dropdown_widgets[:level] + [dropdown]

    def on_top_level_column_select(self, event, df):
        """Handle selection of a top-level column and filter the DataFrame."""
        dropdown = event.widget
        selected_column = dropdown.get()  # Get the selected top-level column name
    
        if isinstance(df.columns, pd.MultiIndex):
            # Filter columns matching the selected top-level name
            filtered_df = df.loc[:, df.columns.get_level_values(0) == selected_column]
            filtered_df.columns = filtered_df.columns.droplevel(0)  # Drop the top-level column
        else:
            # For flat column structure
            filtered_df = df[[selected_column]]
    
        # Add the date range slider and plot the data
        self.add_date_range_slider(filtered_df, selected_column)


    def on_select(self, event, dropdown, data, level):
        """Handle navigation through dropdown selections and reset levels below."""
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


    def reset_below_level(self, level):
        """Reset all dropdowns and widgets below the specified level."""
        for widget in self.dropdown_widgets[level + 1:]:
            widget.destroy()
        self.dropdown_widgets = self.dropdown_widgets[:level + 1]

        # Clear the plot
        self.clear_plot()
        if self.slider_frame:
            self.slider_frame.destroy()
            
            
    # Add slider for daterange
    def update_plot_with_slider(self, df, selected_column, index_values):
        """Update the plot based on the selected date range from the sliders."""
        start_index = int(self.start_slider.get())
        end_index = int(self.end_slider.get())
    
        # Map the slider values to actual dates
        start_date = index_values[start_index]
        end_date = index_values[end_index]
    
        # Filter data by date range
        filtered_df = df.loc[start_date:end_date]
    
        # Generate the title
        title = f"{selected_column} - {' → '.join(self.selected_keys)}"
        self.plot_dataframe(filtered_df, title)


        
    def add_date_range_slider(self, df, selected_column):
        """Add a slider to filter the DataFrame by date range."""
        if self.slider_frame:
            self.slider_frame.destroy()
    
        # Filter non-NaN values
        non_nan_df = df.dropna()
        index_values = non_nan_df.index
    
        # Create the slider frame
        self.slider_frame = tk.Frame(self.root)
        self.slider_frame.pack(pady=5)
    
        # Variables to show date labels
        self.start_date_var = tk.StringVar(value=str(index_values[0]))
        self.end_date_var = tk.StringVar(value=str(index_values[-1]))
    
        # Create start and end sliders
        start_label = tk.Label(self.slider_frame, text="Start Date:")
        start_label.pack(side=tk.LEFT, padx=5)
        start_date_label = tk.Label(self.slider_frame, textvariable=self.start_date_var)
        start_date_label.pack(side=tk.LEFT, padx=5)
    
        self.start_slider = tk.Scale(
            self.slider_frame, from_=0, to=len(index_values) - 1,
            resolution=1, orient=tk.HORIZONTAL, length=300,
            command=lambda value: self.update_start_date(non_nan_df, selected_column, index_values, value)
        )
        self.start_slider.set(0)
        self.start_slider.pack(side=tk.LEFT, padx=5)
    
        end_label = tk.Label(self.slider_frame, text="End Date:")
        end_label.pack(side=tk.LEFT, padx=5)
        end_date_label = tk.Label(self.slider_frame, textvariable=self.end_date_var)
        end_date_label.pack(side=tk.LEFT, padx=5)
    
        self.end_slider = tk.Scale(
            self.slider_frame, from_=0, to=len(index_values) - 1,
            resolution=1, orient=tk.HORIZONTAL, length=300,
            command=lambda value: self.update_end_date(non_nan_df, selected_column, index_values, value)
        )
        self.end_slider.set(len(index_values) - 1)
        self.end_slider.pack(side=tk.LEFT, padx=5)
    
        # Plot the initial data
        self.update_plot_with_slider(non_nan_df, selected_column, index_values)

    
    def update_start_date(self, df, selected_column, index_values, value):
        """Update the start date label and refresh the plot."""
        self.start_date_var.set(str(index_values[int(value)]))
        self.update_plot_with_slider(df, selected_column, index_values)
    
    def update_end_date(self, df, selected_column, index_values, value):
        """Update the end date label and refresh the plot."""
        self.end_date_var.set(str(index_values[int(value)]))
        self.update_plot_with_slider(df, selected_column, index_values)
        
    # Add checkbox for plotting columns

        
    def plot_dataframe(self, df, title):
        """Plot the filtered DataFrame."""
        self.clear_plot()  # Clear any existing plot
    
        # Create a new Matplotlib figure
        fig, ax = plt.subplots(figsize=(8, 4))
        df.plot(ax=ax)
        ax.set_title(title, fontsize=14)
        ax.set_xlabel("Date")
        ax.set_ylabel("Values")
        ax.grid(True)
    
        # Add the plot to the Tkinter GUI
        self.plot_canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.plot_canvas.draw()
        self.plot_canvas.get_tk_widget().pack()


    def clear_plot(self):
        """Clear the existing plot from the GUI."""
        if self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()
            self.plot_canvas = None

    def reset(self):
        """Reset the app to the initial state."""
        self.current_data = self.data

        # Clear all dropdowns
        for widget in self.dropdown_widgets:
            widget.destroy()
        self.dropdown_widgets = []

        self.clear_plot()  # Clear any existing plot

        # Create the first dropdown
        self.create_new_dropdown(self.current_data, self.dropdown_frame)
        if self.slider_frame:
            self.slider_frame.destroy()



# Initialize and run the Tkinter app
def run_dict_explorer(data):
    root = tk.Tk()
    root.title("Dictionary Explorer")
    app = DictExplorerApp(root, data)
    root.mainloop()


run_dict_explorer(data_dict)
