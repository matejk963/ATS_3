import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import tkinter as tk
import pandas as pd
from tkinter import ttk
from Utilities.tech_analysis.tech_analysis_tool import TechAnalysisTool
from Utilities.tech_analysis.tech_analysis_stats import TechAnalysisStats
from Utilities.tech_analysis.tech_analysis_stats import TechAnalysisStats     

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
        # Destroy existing frame if it exists and is valid
        if directions_str in self.plots and "frame" in self.plots[directions_str]:
            if self.plots[directions_str]["frame"]:
                frame = self.plots.get(directions_str, {}).get("frame")
                if frame and frame.winfo_exists():
                # Destroy all children of the frame to ensure no widgets (like listboxes) are left behind
                    for widget in frame.winfo_children():
                        widget.destroy()
                    self.plots[directions_str]["frame"].destroy()
            self.plots[directions_str]["frame"] = None  # Ensure the reference is cleared
            
        """Create the frame for the chart, including dual date input and optional history listbox."""
        print(f"Creating chart frame for {directions_str} at position {chart_directions}")

        # ✅ Ensure 'plots' exists in the sheet dictionary
        if "plots" not in self.sheets[self.current_sheet]:
            self.sheets[self.current_sheet]["plots"] = {}

        # ✅ Ensure 'directions_str' (e.g., "row_0_col_0") exists inside 'plots'
        if directions_str not in self.sheets[self.current_sheet]["plots"]:
            self.sheets[self.current_sheet]["plots"][directions_str] = {
                "start_date_var": tk.StringVar(value="Select Date"),
                "end_date_var": tk.StringVar(value="Select Date"),
                "history_flag": history
            }

        # ✅ Now it's safe to retrieve values
        stored_start = self.sheets[self.current_sheet]["plots"][directions_str]["start_date_var"]
        prev_start_date = stored_start.get() if isinstance(stored_start, tk.StringVar) else stored_start
        stored_end = self.sheets[self.current_sheet]["plots"][directions_str]["end_date_var"]
        prev_end_date = stored_end.get() if isinstance(stored_end, tk.StringVar) else stored_end

        # ✅ Preserve the available values in dropdowns before re-creating them
        prev_dates = []
        if directions_str in self.plots and "start_date_dropdown" in self.plots[directions_str] and isinstance(self.plots[directions_str]["start_date_dropdown"], ttk.Combobox):
            if self.plots[directions_str]["start_date_dropdown"].winfo_exists():
                prev_dates = self.plots[directions_str]["start_date_dropdown"]["values"]
            else:
                print(f"Warning: Previous start_date_dropdown for {directions_str} no longer exists. Reinitializing.")

        # ✅ Ensure plot storage exists
        if directions_str not in self.sheets[self.current_sheet]["plots"]:
            self.sheets[self.current_sheet]["plots"][directions_str] = {}

        # ✅ Validate and initialize the parent plot_grid
        plot_grid = self.sheets[self.current_sheet]["ui"].get("plot_grid")
        if not plot_grid or not plot_grid.winfo_exists():
            print(f"Error: plot_grid missing or invalid for {self.current_sheet}. Reinitializing UI.")
            self.setup_ui_for_sheet(self.current_sheet)
            plot_grid = self.sheets[self.current_sheet]["ui"]["plot_grid"]

        # ✅ Destroy existing frame if it exists and is valid
        existing_frame = self.plots.get(directions_str, {}).get("frame")
        if existing_frame and existing_frame.winfo_exists():
            existing_frame.destroy()

        # ✅ Create a new Frame for the Plot
        frame = ttk.Frame(plot_grid, padding=0, relief="flat", borderwidth=0)
        frame.grid(row=chart_directions[0], column=chart_directions[1], sticky="nsew", padx=0, pady=0)
        frame.grid_propagate(False)

        # ✅ Ensure grid resizing flexibility
        plot_grid.rowconfigure(chart_directions[0], weight=1)
        plot_grid.columnconfigure(chart_directions[1], weight=1)

        # ✅ Initialize self.plots[directions_str] properly
        self.plots[directions_str] = {
            "frame": frame,
            "canvas": None,
            "history_flag": history,
            "column_listbox": None,
            "history_initialized": False,
            "start_date_var": tk.StringVar(value=prev_start_date),
            "start_date_entry_var": tk.StringVar(value=""),
            "end_date_var": tk.StringVar(value=prev_end_date),
            "end_date_entry_var": tk.StringVar(value=""),
            "last_selected": [],
            "start_date": None,
            "end_date": None
        }

        # ✅ Add Mean Checkbox
        self.create_checkbox(directions_str)

        def sync_date_vars(var1, var2):
            """Syncs two date variables when changed."""
            var2.set(var1.get())

        # ✅ Create Date Range Selection Frame
        date_range_frame = ttk.Frame(frame)
        date_range_frame.pack(side="bottom", fill="x", pady=5)

        # ✅ Start Date (Dropdown + Entry)
        start_frame = ttk.LabelFrame(date_range_frame, text="Start Date", padding=2)
        start_frame.pack(side="left", padx=5)

        start_var = self.plots[directions_str]["start_date_var"]
        start_entry_var = self.plots[directions_str]["start_date_entry_var"]

        # ✅ Create new dropdown with previous values if available
        self.plots[directions_str]["start_date_dropdown"] = ttk.Combobox(
            start_frame, 
            textvariable=start_var, 
            values=prev_dates if prev_dates else ["Select Date"], 
            state="readonly"
        )
        self.plots[directions_str]["start_date_dropdown"].pack(fill="x", pady=2)
        self.plots[directions_str]["start_date_dropdown"].bind(
            "<<ComboboxSelected>>", 
            lambda e: sync_date_vars(start_var, start_entry_var)
        )

        self.plots[directions_str]["start_date_entry"] = ttk.Entry(start_frame, textvariable=start_entry_var)
        self.plots[directions_str]["start_date_entry"].pack(fill="x", pady=2)
        self.plots[directions_str]["start_date_entry"].bind(
            "<FocusOut>", 
            lambda e: sync_date_vars(start_entry_var, start_var)
        )

        # ✅ End Date (Dropdown + Entry)
        end_frame = ttk.LabelFrame(date_range_frame, text="End Date", padding=2)
        end_frame.pack(side="left", padx=5)

        end_var = self.plots[directions_str]["end_date_var"]
        end_entry_var = self.plots[directions_str]["end_date_entry_var"]

        self.plots[directions_str]["end_date_dropdown"] = ttk.Combobox(
            end_frame, 
            textvariable=end_var, 
            values=prev_dates if prev_dates else ["Select Date"], 
            state="readonly"
        )
        self.plots[directions_str]["end_date_dropdown"].pack(fill="x", pady=2)
        self.plots[directions_str]["end_date_dropdown"].bind(
            "<<ComboboxSelected>>", 
            lambda e: sync_date_vars(end_var, end_entry_var)
        )

        self.plots[directions_str]["end_date_entry"] = ttk.Entry(end_frame, textvariable=end_entry_var)
        self.plots[directions_str]["end_date_entry"].pack(fill="x", pady=2)
        self.plots[directions_str]["end_date_entry"].bind(
            "<FocusOut>", 
            lambda e: sync_date_vars(end_entry_var, end_var)
        )

        # ✅ Restore previous start/end date values in dropdowns
        self.plots[directions_str]["start_date_dropdown"].set(prev_start_date)
        self.plots[directions_str]["end_date_dropdown"].set(prev_end_date)

        print(f"✅ Chart frame created for {directions_str} (history={history}), Restored Dates: {prev_start_date} - {prev_end_date}")

        # ✅ Unified "Update" Function for All Charts
        def update_plot():
            # Force idle tasks update (if needed)
            self.root.update_idletasks()
            """Triggers a chart update when the user selects new dates or historical columns."""
            start_date = self.plots[directions_str]["start_date_dropdown"].get()
            end_date = self.plots[directions_str]["end_date_dropdown"].get()

            # Save updated date selections to the persistent sheet structure
            self.sheets[self.current_sheet]["plots"][directions_str]["start_date_var"] = self.plots[directions_str]["start_date_var"].get()
            self.sheets[self.current_sheet]["plots"][directions_str]["end_date_var"] = self.plots[directions_str]["end_date_var"].get()


            # 🔹 Force refresh of the dropdowns to reflect changes
            self.plots[directions_str]["start_date_dropdown"].set(start_date)
            self.plots[directions_str]["end_date_dropdown"].set(end_date)

            if start_date == "Select Date" or end_date == "Select Date":
                print(f"⚠️ Cannot update plot for {directions_str}: Start or End date not selected.")
                return

            print(f"Updating plot for {directions_str} with date range: {start_date} to {end_date}")

            # ✅ If it's a history chart, retrieve selected columns
            selected_columns = []
            if history and "column_listbox" in self.plots[directions_str] and self.plots[directions_str]["column_listbox"]:
                selected_columns = [
                    self.plots[directions_str]["column_listbox"].get(i)
                    for i in self.plots[directions_str]["column_listbox"].curselection()
                ]
                self.plots[directions_str]["last_selected"] = selected_columns

            print(f"Selected columns for history chart: {selected_columns}")

            # ✅ Call `plot_chart`, now passing the selected date range
            current_mean_var = self.plots[directions_str].get("mean_var")
            self.plot_chart(
                chart_type="main" if directions_str == "row_0_col_0" else "secondary",
                history=history,
                mean_var=current_mean_var,
                directions_str=directions_str,
                start_date=start_date,
                end_date=end_date,
                selected_columns=selected_columns,
                first_plot=False
            )


            # 🔹 Update the dropdown selections after plotting
            self.plots[directions_str]["start_date_dropdown"].set(start_date)
            self.plots[directions_str]["end_date_dropdown"].set(end_date)



        # ✅ Add "Update" Button (for ALL charts)
        update_button = ttk.Button(date_range_frame, text="Update", command=update_plot)
        update_button.pack(side="left", padx=5)

        # Set up listbox for historical plots (Only for history charts)
        if history:
            # Double-check that no listbox exists
            if "column_listbox" in self.plots[directions_str] and self.plots[directions_str]["column_listbox"]:
                if self.plots[directions_str]["column_listbox"].winfo_exists():
                    # Destroy the parent listbox_frame if it exists
                    parent = self.plots[directions_str]["column_listbox"].master
                    if parent and parent.winfo_exists():
                        parent.destroy()
                    self.plots[directions_str]["column_listbox"].destroy()
                self.plots[directions_str]["column_listbox"] = None

            # Create a new listbox frame
            listbox_frame = ttk.Frame(frame)
            listbox_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)

            listbox = tk.Listbox(listbox_frame, selectmode="multiple", exportselection=False, height=5)
            listbox.pack(fill="both", expand=True)
            self.plots[directions_str]["column_listbox"] = listbox

            # Populate the listbox with columns from spread_df if available
            cache_key = (self.current_sheet, directions_str)
            spread_df = self.spread_cache.get(cache_key, pd.DataFrame())
            if not spread_df.empty:
                available_columns = list(spread_df.columns)
                for col in available_columns:
                    listbox.insert(tk.END, col)
                # Restore previous selections or select all if first plot
                if self.plots[directions_str].get("history_initialized", False):
                    last_selected = self.sheets[self.current_sheet]["plots"][directions_str].get("last_selected", [])
                    self.plots[directions_str]["last_selected"] = last_selected
                    for i, col in enumerate(available_columns):
                        if col in last_selected:
                            listbox.selection_set(i)
                else:
                    for i in range(len(available_columns)):
                        listbox.selection_set(i)
                    self.plots[directions_str]["history_initialized"] = True
                    print(f"Initialized history plot at {directions_str} with all columns selected: {available_columns}")

            # Store last selected columns when selection changes
            def on_select(event):
                selected_columns = [listbox.get(i) for i in listbox.curselection()]
                self.sheets[self.current_sheet]["plots"][directions_str]["last_selected"] = selected_columns
                print(f"Selection changed to {selected_columns}")

            listbox.bind("<<ListboxSelect>>", on_select)
        else:
            if "column_listbox" in self.plots[directions_str] and self.plots[directions_str]["column_listbox"]:
                if self.plots[directions_str]["column_listbox"].winfo_exists():
                    # Destroy the parent listbox_frame if it exists
                    parent = self.plots[directions_str]["column_listbox"].master
                    if parent and parent.winfo_exists():
                        parent.destroy()
                    self.plots[directions_str]["column_listbox"].destroy()
                self.plots[directions_str]["column_listbox"] = None
            self.plots[directions_str]["history_initialized"] = False


        # ✅ Set up listbox for historical plots (Only for history charts)
        # if history:
        #     listbox_frame = ttk.Frame(frame)
        #     listbox_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)

        #     listbox = tk.Listbox(listbox_frame, selectmode="multiple", exportselection=False, height=5)
        #     listbox.pack(fill="both", expand=True)
        #     self.plots[directions_str]["column_listbox"] = listbox

        #     # ✅ Store last selected columns when selection changes
        #     def on_select(event):
        #         selected_columns = [listbox.get(i) for i in listbox.curselection()]
        #         self.plots[directions_str]["last_selected"] = selected_columns
        #         print(f"Selection changed to {selected_columns}")

        #     listbox.bind("<<ListboxSelect>>", on_select)

        # else:
        #     self.plots[directions_str]["column_listbox"] = None
        #     self.plots[directions_str]["history_initialized"] = False

        # print(f"✅ Chart frame created for {directions_str} (history={history})")


            
    def create_checkbox(self, directions_str):
        """Creates a checkbox for enabling/disabling moving average (if not history)
        or seasonality (if history) for a given plot.
        If history is enabled, the checkbox is forced to be ticked by default.
        """
        if not self.current_sheet:
            print("Error: No current sheet set for creating checkbox.")
            return

        sheet_name = self.current_sheet
        # Determine if this chart is in history mode
        history_flag = self.plots[directions_str].get("history_flag", False)
        # Force checkbox to be ticked (value 1) if history mode is active, otherwise unticked (0)
        default_value = 1 if history_flag else 0

        # Check if the checkbox variable already exists;
        # if so, update its value to match the default based on history mode.
            # Check for an existing mean_var in the current plot state
        checkbox_var = self.plots[directions_str].get("mean_var")
        if checkbox_var is None:
            # No prior variable found, so create it using the default
            checkbox_var = tk.IntVar(value=(1 if history_flag else 0))
            self.plots[directions_str]["mean_var"] = checkbox_var
        # Else: use the existing variable without resetting its value


        # Ensure the frame exists and is valid
        if (directions_str not in self.plots or not isinstance(self.plots[directions_str], dict) or
            "frame" not in self.plots[directions_str] or not self.plots[directions_str]["frame"].winfo_exists()):
            print(f"Error: Frame for {directions_str} does not exist or is invalid. Skipping checkbox creation.")
            return

        # Set label and checkbox key based on whether history is enabled
        if history_flag:
            label = "Seasonality"
            checkbox_key = "seasonality_checkbox"
        else:
            label = "Mean"
            checkbox_key = "mean_checkbox"

        # Destroy any existing checkbox to avoid duplicates
        if checkbox_key in self.plots[directions_str] and self.plots[directions_str][checkbox_key].winfo_exists():
            self.plots[directions_str][checkbox_key].destroy()

        # Create the checkbox with the appropriate label and command
        self.plots[directions_str][checkbox_key] = ttk.Checkbutton(
            self.plots[directions_str]["frame"],
            text=label,
            variable=checkbox_var,
            command=lambda: self.plot_chart(
                chart_type="main" if directions_str == "row_0_col_0" else "secondary",
                history=history_flag,
                mean_var=checkbox_var,
                directions_str=directions_str,
                start_date=self.plots[directions_str]["start_date_var"].get(),
                end_date=self.plots[directions_str]["end_date_var"].get(),
                selected_columns=self.plots[directions_str].get("last_selected", []),
                first_plot=False
            )
        )
        self.plots[directions_str][checkbox_key].pack(side="bottom", anchor="w", padx=5, pady=5)

        print(f"✅ {label} checkbox recreated with value {checkbox_var.get()} for {directions_str} in {sheet_name}")




    def update_column_options(self, directions_str, available_columns=None):
        """Updates the multi-selection listbox for history plot columns while preserving selection."""

        # ✅ Use cached spread_df if available
        cache_key = (self.current_sheet, directions_str)
        spread_df = self.spread_cache.get(cache_key, pd.DataFrame())

        # ✅ Extract columns if not provided
        if available_columns is None:
            available_columns = list(spread_df.columns) if not spread_df.empty else []

        # ✅ Ensure listbox exists
        if "column_listbox" not in self.plots[directions_str]:
            print(f"Warning: No listbox found for {directions_str}")
            return

        # ✅ Store current selection
        current_selection = [self.plots[directions_str]["column_listbox"].get(i) 
                            for i in self.plots[directions_str]["column_listbox"].curselection()]

        # ✅ Update listbox contents
        self.plots[directions_str]["column_listbox"].delete(0, tk.END)
        for col in available_columns:
            self.plots[directions_str]["column_listbox"].insert(tk.END, col)

        # ✅ Restore selection if not first plot, otherwise select all
        if self.plots[directions_str].get("history_initialized", False):
            # Restore previous selection
            for i, col in enumerate(available_columns):
                if col in current_selection:
                    self.plots[directions_str]["column_listbox"].selection_set(i)
        else:
            # First plot: select all columns
            for i in range(len(available_columns)):
                self.plots[directions_str]["column_listbox"].selection_set(i)
            
            self.plots[directions_str]["last_selected"] = available_columns
            self.sheets[self.current_sheet]["plots"][directions_str]["last_selected"] = available_columns
            
            self.plots[directions_str]["history_initialized"] = True
            print(f"Initialized history plot at {directions_str} with all columns selected: {available_columns}")


            
    def plot_chart(self, chart_type="main", history=False, mean_var=None, 
               directions_str=None, start_date=None, end_date=None, 
               selected_columns=None, first_plot=False):
        """
        Plots or restores a chart for the selected sheet and chart type,
        reusing the same Figure/Toolbar to avoid multiple toolbars.
        """
        # --- 1) Validate date inputs ---
        if isinstance(start_date, tk.StringVar):
            start_date = start_date.get()
        if isinstance(end_date, tk.StringVar):
            end_date = end_date.get()

        if start_date == "Select Date" or end_date == "Select Date":
            print(f"⚠️ Cannot update plot: Start or End date not selected ({start_date} - {end_date})")
            return

        # Convert provided dates to Timestamps (will work if valid strings)
        start_date = pd.to_datetime(start_date, errors="coerce")
        end_date = pd.to_datetime(end_date, errors="coerce")


        if not self.current_sheet:
            print("Error: No active sheet to plot on.")
            return
        sheet_name = self.current_sheet

        # --- 2) Determine directions_str & chart positions ---
        chart_positions = {
            "main": "row_0_col_0",
            "secondary": "row_1_col_0",
            "statistics": "row_0_col_1",
            "correlations": "row_1_col_1"
        }
        if directions_str is None:
            directions_str = chart_positions.get(chart_type, "row_0_col_0")
        directions_map = {
            "row_0_col_0": [0, 0],
            "row_0_col_1": [0, 1],
            "row_1_col_0": [1, 0],
            "row_1_col_1": [1, 1]
        }
        chart_directions = directions_map.get(directions_str, [0, 0])

        # --- 3) If the chart frame doesn't exist, create it ---
        if (directions_str not in self.plots or 
            "frame" not in self.plots[directions_str] or 
            not self.plots[directions_str]["frame"].winfo_exists()):
            print(f"Recreating chart frame for {directions_str} at {chart_directions}")
            self.create_chart_frame(chart_directions, directions_str, history=history)

        # --- 4) Gather the user-defined legs & weights ---
        contracts, weights = [], []
        if chart_type in ["main", "secondary"]:
            for dropdown_group in self.sheets[sheet_name]["legs"][chart_type].values():
                contract = self.create_contract(dropdown_group)
                weight = self.collect_weights(dropdown_group)
                if contract and weight:
                    contracts.append(contract)
                    weights.extend(weight)
        else:
            # For "statistics" or "correlations", you might gather differently
            pass

        if not contracts:
            print(f"⚠️ No contracts found for {chart_type} at {directions_str}. Aborting plot.")
            return

        # --- 5) Retrieve or calculate the spread data ---
        if history:
            # Default seasonality to True if mean_var is None, otherwise check its value.
            if mean_var is None:
                seasonality = True
            else:
                seasonality = True if mean_var.get() == 1 else False
            cache_key = (tuple(contracts), directions_str, history, seasonality)
        else:
            cache_key = (tuple(contracts), directions_str, history)

        if cache_key in self.spread_cache:
            spread_df = self.spread_cache[cache_key]
        else:
            if history:
                spread_df = self.ta_inst.get_history_spread(contracts, weights, seasonality=seasonality)
            else:
                spread_df = self.ta_inst.get_spread(contracts, weights)
            if spread_df is None or spread_df.empty:
                print(f"⚠️ No valid price data for {chart_type} at {directions_str}.")
                return
            self.spread_cache[cache_key] = spread_df




        # --- 5.5) Set default start/end date if not already set (for first plotting) ---
        start_dropdown = self.plots[directions_str].get("start_date_dropdown")
        end_dropdown = self.plots[directions_str].get("end_date_dropdown")
        if start_dropdown and end_dropdown and spread_df.index.size > 0:
            dates = list(spread_df.index.strftime("%Y-%m-%d"))
            start_dropdown["values"] = dates
            end_dropdown["values"] = dates
            if start_dropdown.get() == "Select Date":
                start_dropdown.set(dates[0])
                self.plots[directions_str]["start_date_var"].set(dates[0])
                start_date = pd.to_datetime(dates[0])
            if end_dropdown.get() == "Select Date":
                end_dropdown.set(dates[-1])
                self.plots[directions_str]["end_date_var"].set(dates[-1])
                end_date = pd.to_datetime(dates[-1])

        # --- 6) Fallback: If date variables are still not set, use the full range from spread_df ---
        if not start_date or str(start_date) == "NaT":
            start_date = spread_df.index.min()
        if not end_date or str(end_date) == "NaT":
            end_date = spread_df.index.max()

        # --- 7) Filter the spread_df by the selected date range ---
        spread_df_plot = spread_df.loc[(spread_df.index >= start_date) & (spread_df.index <= end_date)]
        if spread_df_plot.empty:
            print(f"⚠️ Data is empty after filtering from {start_date} to {end_date}.")
            return

        # --- 8) Handle history columns selection ---
        if history:
            if not selected_columns:
                listbox = self.plots[directions_str].get("column_listbox")
                if listbox and listbox.winfo_exists():
                    selected_columns = [listbox.get(i) for i in listbox.curselection()]
                if not selected_columns:
                    selected_columns = spread_df_plot.columns.tolist()
            self.plots[directions_str]["last_selected"] = selected_columns
        else:
            selected_columns = ["spread_value"]

        # --- 9) Reuse or create a new Figure/Canvas/Toolbar ---
        existing_canvas = self.plots[directions_str].get("canvas")
        if existing_canvas:
            fig = existing_canvas.figure
            fig.clear()
            ax = fig.add_subplot(111)
        else:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            fig = Figure(figsize=(7, 4))
            ax = fig.add_subplot(111)
            canvas = FigureCanvasTkAgg(fig, master=self.plots[directions_str]["frame"])
            toolbar = NavigationToolbar2Tk(canvas, self.plots[directions_str]["frame"])
            toolbar.update()
            canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.plots[directions_str]["canvas"] = canvas
            self.plots[directions_str]["toolbar"] = toolbar
            existing_canvas = canvas

        # --- 10) Plot the data ---
        if history:
            for col in selected_columns:
                ax.plot(spread_df_plot.index, spread_df_plot[col], label=col.split('_')[-1])
            for col in selected_columns:
                last_val = spread_df_plot[col].iloc[-1]
                last_x = spread_df_plot.index[-1]
                ax.annotate(
                    f"{last_val:.2f}",
                    xy=(last_x, last_val),
                    xytext=(5, 0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=9,
                    color="black",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.7)
                )
                ax.relim()
                ax.autoscale_view()
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
                fig.autofmt_xdate()
                existing_canvas.draw()

        else:
            ax.plot(spread_df_plot.index, spread_df_plot["spread_value"], label="Spread Value", color="blue")
            last_val = spread_df_plot["spread_value"].iloc[-1]
            last_x = spread_df_plot.index[-1]
            ax.annotate(
                f"{last_val:.2f}",
                xy=(last_x, last_val),
                xytext=(5, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=9,
                color="black",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.7)
            )
            ax.relim()
            ax.autoscale_view()
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
            existing_canvas.draw()


        # --- 11) Apply moving average if enabled (only for non-history charts) ---
        if not history:
            if mean_var and mean_var.get() == 1:       
                stats = TechAnalysisStats(spread_df)
                ma_df = stats.get_moving_average(window=20, ma_type="simple")
                ma_df = ma_df.reindex(spread_df_plot.index)
                if "mean" in ma_df.columns:
                    ax.plot(ma_df.index, ma_df["mean"], linestyle="--", label="Moving Average", color="orange")
                    ax.plot(ma_df.index, ma_df["upper_band"], linestyle="--", label="upper_band", color="red")
                    ax.plot(ma_df.index, ma_df["lower_band"], linestyle="--", label="lower_band", color="green")

            # --- 12) Style the axes, legend, and grid ---
            ax.set_title(f"{chart_type.capitalize()} Analysis ({directions_str}) - History={history}")
            ax.grid(True)
            ax.legend(loc="center left", bbox_to_anchor=(1, 0.5))
            fig.subplots_adjust(left=0.05, right=0.9, top=0.9, bottom=0.1)

        # fig.tight_layout(rect=[0, 0, 0.8, 1])

        # --- 13) Optional: hover tooltips with mplcursors ---
        try:
            import mplcursors

            cursor = mplcursors.cursor(ax, hover=True)
            @cursor.connect("add")
            def on_add(sel):
                x, y = sel.target
                if isinstance(x, float):
                    dt = mdates.num2date(x)
                    date_str = pd.to_datetime(dt).strftime("%Y-%m-%d")
                    sel.annotation.set_text(f"{sel.artist.get_label()}\n{date_str}\n{y:.2f}")
                else:
                    sel.annotation.set_text(f"{sel.artist.get_label()}\n{x}\n{y:.2f}")
        except ImportError:
            mplcursors = None
            pass

        # --- 14) Redraw the canvas ---
        existing_canvas.draw()

        # ✅ Handle history column selection
        if history:
            listbox = self.plots[directions_str].get("column_listbox")
            if listbox and listbox.winfo_exists():
                # ✅ Get previously selected columns (from persistent sheet memory)
                prev_selected = self.sheets[self.current_sheet]["plots"][directions_str].get("last_selected", [])

                # ✅ Refill listbox with fresh columns
                listbox.delete(0, tk.END)
                for col in spread_df.columns:
                    listbox.insert(tk.END, col)

                # ✅ Restore previous selection or select all on first plot
                if prev_selected:
                    for col in prev_selected:
                        if col in spread_df.columns:
                            idx = listbox.get(0, tk.END).index(col)
                            listbox.selection_set(idx)
                else:
                    for i in range(len(spread_df.columns)):
                        listbox.selection_set(i)
                    self.plots[directions_str]["history_initialized"] = True
                    print(f"Initialized history plot at {directions_str} with all columns selected.")

                # ✅ Extract the active selection
                selected_columns = [listbox.get(i) for i in listbox.curselection()]
                if not selected_columns:
                    selected_columns = prev_selected if prev_selected else spread_df.columns.tolist()

                # ✅ Save back to both runtime and persistent memory
                self.plots[directions_str]["last_selected"] = selected_columns
                self.sheets[self.current_sheet]["plots"][directions_str]["last_selected"] = selected_columns
            else:
                # Fallback if listbox missing
                selected_columns = self.sheets[self.current_sheet]["plots"][directions_str].get("last_selected", spread_df.columns.tolist())

        # --- 15) Save the plot state for future restoration ---
        self.save_plot_state()
        print(f"✅ Updated {chart_type} chart at {directions_str} with date range {start_date.date()} - {end_date.date()}")

    def plot_statistics(self, chart_type="statistics", directions_str="row_0_col_1", stat_type=None):
        if self.current_sheet not in self.sheets:
            print("Error: No active sheet to plot on.")
            return

        sheet_name = self.current_sheet
        if not self.sheets[sheet_name]["legs"].get(chart_type, {}):
            print(f"No legs defined for {chart_type}. Please add legs to Main or Secondary chart first.")
            return

        # Proceed with plotting logic
        print(f"Plotting {chart_type.capitalize()} at {directions_str} with stat_type {stat_type}")
        # Add your statistics plotting logic here (e.g., calculate mean, median, etc., from Main/Secondary legs)
        contracts, weights = [], []
        for leg_type in ["main", "secondary"]:
            for dropdown_group in self.sheets[sheet_name]["legs"][leg_type].values():
                contract = self.create_contract(dropdown_group)
                weight = self.collect_weights(dropdown_group)
                contracts.append(contract)
                weights.extend(weight)

        if not contracts:
            print(f"No contracts available from Main or Secondary charts for {chart_type} at {directions_str}.")
            return

        # Example: Fetch data and plot (replace with your actual logic)
        spread_df = self.ta_inst.get_spread(spread_legs=contracts, leg_weights=weights)
        if spread_df is None or spread_df.empty:
            print(f"No data available for {chart_type} at {directions_str}.")
            return

        fig, ax = plt.subplots(figsize=(7, 4))
        if stat_type == "Mean":
            ax.plot(spread_df.index, spread_df["spread_value"].mean(), label="Mean")
        # Add other stat types (Median, Std Dev, Variance) as needed
        ax.set_title(f"{stat_type} - {chart_type.capitalize()} ({directions_str})")
        ax.legend()
        ax.grid(True)

        # Embed the plot
        if "canvas" in self.plots[directions_str]:
            self.plots[directions_str]["canvas"].get_tk_widget().pack_forget()
            self.plots[directions_str]["canvas"].draw()

        self.plots[directions_str]["canvas"] = FigureCanvasTkAgg(fig, master=self.plots[directions_str]["frame"])
        self.plots[directions_str]["canvas"].get_tk_widget().pack(fill="both", expand=True)
        self.plots[directions_str]["canvas"].draw()
        print(f"🔄 Created new canvas for {directions_str}")

    def plot_correlations(self, chart_type="correlations", directions_str="row_1_col_1", corr_type=None):
        if self.current_sheet not in self.sheets:
            print("Error: No active sheet to plot on.")
            return

        sheet_name = self.current_sheet
        if not self.sheets[sheet_name]["legs"].get(chart_type, {}):
            print(f"No legs defined for {chart_type}. Please add legs to Main or Secondary chart first.")
            return

        # Proceed with plotting logic
        print(f"Plotting {chart_type.capitalize()} at {directions_str} with corr_type {corr_type}")
        # Add your correlations plotting logic here (e.g., calculate Pearson, Spearman, etc., from Main/Secondary legs)
        contracts, weights = [], []
        for leg_type in ["main", "secondary"]:
            for dropdown_group in self.sheets[sheet_name]["legs"][leg_type].values():
                contract = self.create_contract(dropdown_group)
                weight = self.collect_weights(dropdown_group)
                contracts.append(contract)
                weights.extend(weight)

        if not contracts:
            print(f"No contracts available from Main or Secondary charts for {chart_type} at {directions_str}.")
            return

        # Example: Fetch data and plot (replace with your actual logic)
        spread_df = self.ta_inst.get_spread(spread_legs=contracts, leg_weights=weights)
        if spread_df is None or spread_df.empty:
            print(f"No data available for {chart_type} at {directions_str}.")
            return

        fig, ax = plt.subplots(figsize=(7, 4))
        # Add correlation calculation and plotting (e.g., using pandas.DataFrame.corr())
        ax.set_title(f"{corr_type} Correlation - {chart_type.capitalize()} ({directions_str})")
        ax.grid(True)

        # Embed the plot
        if "canvas" in self.plots[directions_str]:
            self.plots[directions_str]["canvas"].get_tk_widget().pack_forget()
            self.plots[directions_str]["canvas"].draw()

        self.plots[directions_str]["canvas"] = FigureCanvasTkAgg(fig, master=self.plots[directions_str]["frame"])
        self.plots[directions_str]["canvas"].get_tk_widget().pack(fill="both", expand=True)
        self.plots[directions_str]["canvas"].draw()
        print(f"🔄 Created new canvas for {directions_str}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TechAnalysisPlot(root)
    root.mainloop()
