import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
import pandas as pd
from tkinter import ttk
from Utilities.tech_analysis.tech_analysis_backup_v2.tech_analysis_tool import TechAnalysisTool
from Utilities.tech_analysis.tech_analysis_backup_v2.tech_analysis_stats import TechAnalysisStats

class TechAnalysisPlot(TechAnalysisTool):
    """Handles plotting functionalities and allows adding moving average via checkboxes."""

    def __init__(self, root):
        """Initialize TechAnalysisPlot as a subclass of TechAnalysisTool."""
        super().__init__(root)

        # ✅ Store references to plots, preventing duplicates
        self.plots = {}

        # ✅ Caching spread_df for each sheet and plot direction
        self.spread_cache = {}

    def create_chart_frame(self, chart_directions, directions_str, history=False):
        """Create the frame for the chart, ensuring history plots have a properly initialized listbox."""

        if directions_str not in self.sheets[self.current_sheet]["plots"]:
            self.sheets[self.current_sheet]["plots"][directions_str] = {}

        self.plots[directions_str] = {}

        # ✅ Create a Frame for the Plot
        self.plots[directions_str]["frame"] = ttk.Frame(
            self.sheets[self.current_sheet]["ui"]["plot_grid"], padding=10, relief="solid", borderwidth=1
        )

        self.plots[directions_str]["frame"].grid(
            row=chart_directions[0], column=chart_directions[1],
            sticky="nsew", padx=10, pady=10
        )

        self.plots[directions_str]["frame"].grid_propagate(False)

        self.sheets[self.current_sheet]["ui"]["plot_grid"].rowconfigure(chart_directions[0], weight=1)
        self.sheets[self.current_sheet]["ui"]["plot_grid"].columnconfigure(chart_directions[1], weight=1)

        # ✅ Add Mean Checkbox
        self.create_checkbox(directions_str)

        # ✅ Create Date Range Selection Frame BELOW the plot
        date_range_frame = ttk.Frame(self.plots[directions_str]["frame"])
        date_range_frame.pack(side="bottom", fill="x", pady=5)

        # ✅ Start Date Dropdown
        self.plots[directions_str]["start_date_var"] = tk.StringVar(value="Select Date")
        self.plots[directions_str]["start_date_dropdown"] = ttk.Combobox(
            date_range_frame, textvariable=self.plots[directions_str]["start_date_var"], values=[], state="readonly"
        )
        self.plots[directions_str]["start_date_dropdown"].pack(side="left", padx=5)

        # ✅ End Date Dropdown
        self.plots[directions_str]["end_date_var"] = tk.StringVar(value="Select Date")
        self.plots[directions_str]["end_date_dropdown"] = ttk.Combobox(
            date_range_frame, textvariable=self.plots[directions_str]["end_date_var"], values=[], state="readonly"
        )
        self.plots[directions_str]["end_date_dropdown"].pack(side="left", padx=5)

        # ✅ Store history flag
        self.plots[directions_str]["history_flag"] = history  

        # ✅ Restore the **original listbox implementation** when `history=True`
        if history:
            listbox_frame = ttk.Frame(self.plots[directions_str]["frame"])
            listbox_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)

            self.plots[directions_str]["column_listbox"] = tk.Listbox(
                listbox_frame, selectmode="multiple", exportselection=False, height=5
            )
            self.plots[directions_str]["column_listbox"].pack(fill="both", expand=True)

            # ✅ Use original behavior of listbox from the first version
            self.update_column_options(directions_str)

        # ✅ Ensure update button works
        update_button = ttk.Button(
            date_range_frame, text="Update",
            command=lambda: self.plot_chart(
                chart_type="main" if directions_str == "row_0_col_0" else "secondary",
                history=self.plots[directions_str].get("history_flag", False),
                directions_str=directions_str
            )
        )
        update_button.pack(side="left", padx=5)


    def create_checkbox(self, directions_str):
        """Create the checkbox frame and checkbutton ONLY if not already created."""
        
        # ✅ Ensure parent frame exists
        if directions_str not in self.plots or "frame" not in self.plots[directions_str]:
            print(f"⚠ Warning: Frame for {directions_str} not found. Creating new frame.")
            self.create_chart_frame([0, 0], directions_str)  # ✅ Create the missing frame

        # ✅ Ensure checkbox frame exists
        if "checkbox_frame" not in self.plots[directions_str]:  
            self.plots[directions_str]["checkbox_frame"] = ttk.Frame(self.plots[directions_str]["frame"])
            self.plots[directions_str]["checkbox_frame"].pack(side="left", fill="y", padx=10, pady=5)

        # ✅ Ensure the `mean_var` is correctly linked to `self.sheets`
        if directions_str not in self.sheets[self.current_sheet]["plots"]:
            self.sheets[self.current_sheet]["plots"][directions_str] = {}

        if "mean_var" not in self.sheets[self.current_sheet]["plots"][directions_str]:
            self.sheets[self.current_sheet]["plots"][directions_str]["mean_var"] = tk.IntVar(value=0)

        # ✅ Retrieve the latest stored `mean_var` from `self.sheets`
        self.plots[directions_str]["mean_var"] = self.sheets[self.current_sheet]["plots"][directions_str]["mean_var"]

        # ✅ Remove old checkbox if it exists
        if "mean_checkbox" in self.plots[directions_str]:
            self.plots[directions_str]["mean_checkbox"].destroy()

        # ✅ Create the checkbox with the latest `mean_var`
        self.plots[directions_str]["mean_checkbox"] = ttk.Checkbutton(
            self.plots[directions_str]["checkbox_frame"], text="Mean",
            variable=self.plots[directions_str]["mean_var"],  # ✅ Correctly linked IntVar
            command=lambda: self.plot_chart(chart_type="main" if directions_str == "row_0_col_0" else "secondary")
        )
        self.plots[directions_str]["mean_checkbox"].pack(side="left")

        print(f"✅ Checkbox recreated with value {self.plots[directions_str]['mean_var'].get()} for {directions_str} in {self.current_sheet}")

    def update_column_options(self, directions_str):
        """Ensures the multi-selection listbox for history plot columns is populated with available columns."""

        # ✅ Use cached spread_df if available
        cache_key = (self.current_sheet, directions_str)
        spread_df = self.spread_cache.get(cache_key, pd.DataFrame())

        # ✅ Extract columns
        available_columns = list(spread_df.columns) if not spread_df.empty else []

        # ✅ Ensure listbox exists before updating
        if "column_listbox" in self.plots[directions_str]:
            self.plots[directions_str]["column_listbox"].delete(0, tk.END)

            for col in available_columns:
                self.plots[directions_str]["column_listbox"].insert(tk.END, col)

            # ✅ Automatically select all contracts when first plotting history
            if not self.plots[directions_str].get("history_initialized", False):
                for i in range(len(available_columns)):
                    self.plots[directions_str]["column_listbox"].selection_set(i)
                self.plots[directions_str]["history_initialized"] = True  # ✅ Prevent resetting selection every time

    def plot_chart(self, chart_type="main", history=False, mean_var=None, directions_str=None, first_plot=False):
        """Retrieve selections from all legs and plot the resulting data inside the respective chart using caching."""
        if self.current_sheet not in self.sheets:
            print("Error: No active sheet to plot on.")
            return

        sheet_name = self.current_sheet
        sheet_plots = self.sheets[sheet_name]["plots"]

        if directions_str is None:
            directions_str = {
                "main": "row_0_col_0",
                "secondary": "row_1_col_0",
                "statistics": "row_0_col_1",
                "correlations": "row_1_col_1"
            }.get(chart_type, "row_0_col_0")

        chart_directions = {
            "row_0_col_0": [0, 0],
            "row_0_col_1": [0, 1],
            "row_1_col_0": [1, 0],
            "row_1_col_1": [1, 1]
        }.get(directions_str, [0, 0])

        if directions_str not in self.plots or "frame" not in self.plots[directions_str]:
            print(f"Creating missing chart frame for {directions_str} in {sheet_name} with history={history}.")
            self.create_chart_frame(chart_directions, directions_str, history=history)

        if mean_var is None:
            mean_var = self.sheets[sheet_name]["plots"].get(directions_str, {}).get("mean_var", tk.IntVar(value=0))

        self.sheets[sheet_name]["plots"][directions_str]["history"] = history

        print(f"Plotting {chart_type.capitalize()} chart at {directions_str} (history={history}, first_plot={first_plot})")

        # ✅ Determine which legs to use
        legs = self.sheets[sheet_name]["legs"].get("main" if history else chart_type, {})

        contracts, weights = [], []

        for dropdown_group in legs.values():
            contract = self.create_contract(dropdown_group)
            weight = self.collect_weights(dropdown_group)
            contracts.append(contract)
            weights.extend(weight)

        print(f"All Plotted Contracts for {chart_type.capitalize()} at {directions_str} (history={history}): {contracts}")
        print(f"Weights: {weights}")

        # ✅ Use cached `spread_df` if available
        cache_key = (sheet_name, directions_str)
        if cache_key in self.spread_cache:
            spread_df = self.spread_cache[cache_key]
            print(f"✅ Using cached spread_df for {chart_type} at {directions_str}")
        else:
            # ✅ Ensure there are contracts before calling get_spread()
            if not contracts:
                print(f"⚠ Warning: No contracts found for {chart_type.capitalize()} at {directions_str}. Skipping plot update.")
                return  

            # ✅ Compute spread_df since it's not cached
            spread_df = self.ta_inst.get_spread(spread_legs=contracts, leg_weights=weights) if not history else \
                        self.ta_inst.get_history_spread(spread_legs=contracts, leg_weights=weights)

            if spread_df is None or spread_df.empty:
                print(f"⚠ Warning: No data available for {chart_type.capitalize()} at {directions_str}.")
                return

            # ✅ Cache spread_df
            self.spread_cache[cache_key] = spread_df

        # ✅ Ensure date dropdowns exist and are updated
        available_dates = list(spread_df.index.strftime("%Y-%m-%d"))

        if available_dates:
            first_date, last_date = available_dates[0], available_dates[-1]

            if self.plots[directions_str]["start_date_var"].get() == "Select Date":
                self.plots[directions_str]["start_date_var"].set(first_date)

            if self.plots[directions_str]["end_date_var"].get() == "Select Date":
                self.plots[directions_str]["end_date_var"].set(last_date)

            self.plots[directions_str]["start_date_dropdown"]["values"] = available_dates
            self.plots[directions_str]["end_date_dropdown"]["values"] = available_dates

        # ✅ Apply selected date range filtering
        start_date = self.plots[directions_str]["start_date_var"].get()
        end_date = self.plots[directions_str]["end_date_var"].get()

        if start_date in available_dates and end_date in available_dates:
            start_date, end_date = pd.to_datetime(start_date), pd.to_datetime(end_date)
            spread_df = spread_df.loc[(spread_df.index >= start_date) & (spread_df.index <= end_date)]

        # ✅ Apply contract selection filtering in history mode
        if history and "column_listbox" in self.plots[directions_str]:
            # ✅ Ensure history contracts are selected the first time
            if not self.plots[directions_str].get("history_initialized", False):
                self.update_column_options(directions_str)

            selected_indices = self.plots[directions_str]["column_listbox"].curselection()
            selected_columns = [self.plots[directions_str]["column_listbox"].get(i) for i in selected_indices]

            if selected_columns:
                print(f"Filtering history plot to only include: {selected_columns}")
                spread_df = spread_df[selected_columns]

            # ✅ Ensure the listbox updates every time a history plot is generated
            self.update_column_options(directions_str)

        # ✅ Apply Moving Average if Needed
        if mean_var.get() == 1:
            print(f"Applying moving average for {sheet_name} at {directions_str}...")  
            stats_instance = TechAnalysisStats(spread_df)
            moving_avg_df = stats_instance.get_moving_average(window=20, type='exp')

            if isinstance(moving_avg_df, pd.DataFrame) and "mean" in moving_avg_df.columns:
                spread_df['mean'] = moving_avg_df['mean']
            else:
                print("Warning: Moving average returned unexpected structure.")

        # ✅ Ensure figure and axes exist
        if "canvas" in self.plots[directions_str]:  
            fig = self.plots[directions_str]["canvas"].figure  
            ax = fig.axes[0]
            ax.clear()  
        else:
            fig, ax = plt.subplots(figsize=(7, 4))

        # ✅ Plot Data Properly for Main vs. History
        for col in spread_df.columns:
            ax.plot(spread_df.index, spread_df[col], label=col)

        if mean_var.get() == 1 and "mean" in spread_df.columns:
            ax.plot(spread_df.index, spread_df["mean"], label="Moving Average", linestyle="dashed", color="orange")

        ax.set_xlabel("Date")
        ax.set_ylabel("Spread Value")
        ax.set_title(f"Spread Analysis - {chart_type.capitalize()} Chart ({directions_str}) (History={history})")
        ax.legend()
        ax.grid(True)

        # ✅ Ensure Matplotlib canvas is attached to the correct frame
        if "canvas" not in self.plots[directions_str]:
            print(f"🔄 Creating new canvas for {directions_str}")
            self.plots[directions_str]["canvas"] = FigureCanvasTkAgg(fig, master=self.plots[directions_str]["frame"])
            self.plots[directions_str]["canvas"].get_tk_widget().pack(fill="both", expand=True)

        # ✅ Redraw the canvas
        self.plots[directions_str]["canvas"].draw_idle()



if __name__ == "__main__":
    root = tk.Tk()
    app = TechAnalysisPlot(root)
    root.mainloop()
