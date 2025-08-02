#%%
import pandas as pd
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from datetime import datetime
import sys
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager
# 'TTF','DE', 'FR', 'HU', 'AT',
# 'IT', 'CZ', 'SK', 'EUA', 'ES'
class TechAnalysisTool:
    def __init__(self, root):
        self.ta_inst = TechAnalysis_manager(markets=['TTF','DE', 'IT', 'CZ', 'SK', 'EUA', 'ES',
                                                     'FR', 'HU', 'AT'])
        self.ta_inst.load_data()

        self.root = root
        self.root.title("Tech Analysis Tool")
        self.root.geometry("1000x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.sheets = {}
        self.current_sheet = None
        self.sheets[self.current_sheet] = {
            "legs": {"main": {}, "secondary": {}}, # Removed "statistics" and "correlations"
            "leg_count": {"main": 0, "secondary": 0}, # Removed "statistics" and "correlations"
            "plots": {},
            "ui": {}
        }

        # ✅ Initialize the spread cache to store spread_df for faster replotting
        self.spread_cache = {}
        self.plots = {}

        # ✅ Main Paned Window: Controls Section (Left) & Visual Section (Right)
        self.main_pane = tk.PanedWindow(root, orient="horizontal")
        self.main_pane.pack(fill="both", expand=True)

        # ✅ Left Panel: Controls Section
        self.controls_section = ttk.Frame(self.main_pane, padding=5, relief="solid", borderwidth=1, width=250)
        self.main_pane.add(self.controls_section)

        # ✅ Sheet Controls (Dropdown + New Sheet Button)
        self.sheet_controls = ttk.Frame(self.controls_section)
        self.sheet_controls.pack(fill="x", padx=5, pady=5)

        self.sheet_var = tk.StringVar()
        self.sheet_dropdown = ttk.Combobox(self.sheet_controls, textvariable=self.sheet_var, state="readonly")
        self.sheet_dropdown.pack(fill="x", pady=2)

        self.btn_new_sheet = ttk.Button(self.sheet_controls, text="New Sheet", command=self.create_new_sheet)
        self.btn_new_sheet.pack(fill="x", pady=2)

        # ✅ Create the first sheet
        self.create_new_sheet()


    def create_new_sheet(self):
        """Creates a new sheet with a placeholder name, to be updated by legs."""
        sheet_number = len(self.sheets) + 1
        sheet_name = f"Sheet {sheet_number}"  # Initial placeholder
        self.current_sheet = sheet_name

        # Initialize sheet attributes
        self.sheets[sheet_name] = {
            "legs": {"main": {}, "secondary": {}}, # Removed "statistics" and "correlations"
            "leg_count": {"main": 0, "secondary": 0}, # Removed "statistics" and "correlations"
            "ui": {},
            "plots": {}
        }

        self.sheet_dropdown["values"] = list(self.sheets.keys())
        self.sheet_var.set(sheet_name)
        self.sheet_dropdown.bind("<<ComboboxSelected>>", self.switch_sheet)

        self.setup_ui_for_sheet(sheet_name)

    def compute_sheet_name(self, sheet_name):
        """Generate a sheet name from the selected legs, joined with '/'."""
        legs = {**self.sheets[sheet_name]["legs"]["main"], **self.sheets[sheet_name]["legs"]["secondary"]}
        if not legs:
            return sheet_name  # Keep placeholder if no legs

        contracts = [self.create_contract(selections) for selections in legs.values()]
        return "/".join(contracts) or sheet_name  # Fallback to original if empty
    
    def save_plot_state(self):
        """Saves the current state of all plots into self.sheets before switching sheets."""
        if self.current_sheet and hasattr(self, 'plots'):
            # Ensure self.sheets[self.current_sheet]["plots"] exists before updating
            if "plots" not in self.sheets[self.current_sheet]:
                self.sheets[self.current_sheet]["plots"] = {}

            # Save entire self.plots state, filtering for dictionaries only
            self.sheets[self.current_sheet]["plots"] = {key: val.copy() for key, val in self.plots.items() if isinstance(val, dict)}

            # Save selected start & end dates, history flag, and last selected columns for each chart
            for directions_str in self.plots:
                if "start_date_var" in self.plots[directions_str]:
                    # Check if the object has a 'get' attribute (i.e. is a Tkinter variable)
                    start_val = (
                        self.plots[directions_str]["start_date_var"].get()
                        if hasattr(self.plots[directions_str]["start_date_var"], "get")
                        else self.plots[directions_str]["start_date_var"]
                    )
                    end_val = (
                        self.plots[directions_str]["end_date_var"].get()
                        if hasattr(self.plots[directions_str]["end_date_var"], "get")
                        else self.plots[directions_str]["end_date_var"]
                    )
                self.sheets[self.current_sheet]["plots"][directions_str]["start_date_var"] = start_val
                self.sheets[self.current_sheet]["plots"][directions_str]["end_date_var"] = end_val
                if 'start_date_dropdown' in self.plots[directions_str]:
                    dropdown = self.plots[directions_str]["start_date_dropdown"]
                    if hasattr(dropdown, 'winfo_exists') and dropdown.winfo_exists():
                        self.sheets[self.current_sheet]["plots"][directions_str]["start_date_dropdown_values"] = dropdown["values"]
                        
                if 'end_date_dropdown' in self.plots[directions_str]:
                    dropdown = self.plots[directions_str]["end_date_dropdown"]
                    if hasattr(dropdown, 'winfo_exists') and dropdown.winfo_exists():
                        self.sheets[self.current_sheet]["plots"][directions_str]["end_date_dropdown_values"] = dropdown["values"]
                
                # Save listbox selection for history plots
                if "last_selected" in self.plots[directions_str]:
                    self.sheets[self.current_sheet]["plots"][directions_str]["last_selected"] = self.plots[directions_str]["last_selected"]

                if "history_flag" in self.plots[directions_str]:
                    self.sheets[self.current_sheet]["plots"][directions_str]["history_flag"] = self.plots[directions_str]["history_flag"]
                if "last_selected" in self.plots[directions_str]:
                    self.sheets[self.current_sheet]["plots"][directions_str]["last_selected"] = self.plots[directions_str]["last_selected"]

            print(f"✅ Saved plots for sheet: {self.current_sheet}")




    def restore_plot_state(self):
        """Restores the plots from self.sheets when switching back to a sheet."""
        if not self.current_sheet or "plots" not in self.sheets[self.current_sheet]:
            print("⚠️ No plots found to restore.")
            return

        print(f"🔄 Restoring plots for sheet: {self.current_sheet}")

        # Restore self.plots dictionary from self.sheets
        self.plots = self.sheets[self.current_sheet]["plots"].copy()

        # Validate UI and ensure plot grid exists
        plot_grid = self.sheets[self.current_sheet]["ui"].get("plot_grid")
        if not plot_grid or not plot_grid.winfo_exists():
            print(f"⚠️ UI rebuild required for {self.current_sheet}")
            self.setup_ui_for_sheet(self.current_sheet)
            plot_grid = self.sheets[self.current_sheet]["ui"]["plot_grid"]

        for directions_str, plot_info in self.sheets[self.current_sheet]["plots"].items():
            # Determine where to place the chart
            chart_directions = {
                "row_0_col_0": [0, 0],
                "row_1_col_0": [1, 0],
                "row_1_col_1": [1, 1]
            }.get(directions_str, [0, 0])

            # Restore dropdown values (if they exist)
            prev_start_dates = plot_info.get("start_date_dropdown_values", ["Select Date"])
            prev_end_dates = plot_info.get("end_date_dropdown_values", ["Select Date"])

            # Patch for dropdowns in chart frame
            if directions_str not in self.plots:
                self.plots[directions_str] = {}

            self.plots[directions_str]["start_date_dropdown_values"] = prev_start_dates
            self.plots[directions_str]["end_date_dropdown_values"] = prev_end_dates

            # Recreate chart frame if needed
            if "frame" not in self.plots[directions_str] or not self.plots[directions_str]["frame"].winfo_exists():
                print(f"⚠️ Missing frame for {directions_str}, recreating chart frame.")
                self.create_chart_frame(chart_directions, directions_str, plot_info.get("history_flag", False))

            saved_start_date = plot_info.get("start_date_var", "Select Date")
            saved_end_date = plot_info.get("end_date_var", "Select Date")

            self.plots[directions_str]["start_date_var"] = tk.StringVar(value=saved_start_date)
            self.plots[directions_str]["end_date_var"] = tk.StringVar(value=saved_end_date)


            # Replot if dates are valid
            if saved_start_date != "Select Date" and saved_end_date != "Select Date":
                chart_type = "main" if directions_str == "row_0_col_0" else "secondary"
                history = plot_info.get("history_flag", False)
                selected_columns = plot_info.get("last_selected", [])
                mean_var = plot_info.get("mean_var", tk.IntVar(value=0))

                print(f"📊 Restoring chart for {directions_str} ({saved_start_date} - {saved_end_date})")

                self.plot_chart(
                    chart_type=chart_type,
                    history=history,
                    mean_var=mean_var,
                    directions_str=directions_str,
                    start_date=saved_start_date,
                    end_date=saved_end_date,
                    selected_columns=selected_columns,
                    first_plot=False
                )

        print(f"✅ Plot restoration complete for sheet: {self.current_sheet}")


    def switch_sheet(self, event=None):
        if self.current_sheet:
            self.save_plot_state()
        
        selected_sheet = self.sheet_var.get()
        if selected_sheet in self.sheets:
            self.current_sheet = selected_sheet
            self.setup_ui_for_sheet(self.current_sheet)
            self.restore_plot_state()

            print(f"🔄 Switched to sheet: {selected_sheet}")


    def setup_ui_for_sheet(self, sheet_name):
        """Sets up the UI components for a given sheet, ensuring correct plots are retained."""
        # Remove old visual section if it exists
        if hasattr(self, "visual_section"):
            self.visual_section.destroy()

        # Create Right Panel: Visual Section
        self.visual_section = ttk.Frame(self.main_pane)
        self.main_pane.add(self.visual_section)

        # Create 2x2 Grid Frame for charts
        self.plot_grid = ttk.Frame(self.visual_section)
        self.plot_grid.pack(fill="both", expand=True)

        # Configure grid layout (2 rows, 1 column for main and secondary only)
        self.plot_grid.grid_rowconfigure(0, weight=1) # Main chart row
        self.plot_grid.grid_rowconfigure(1, weight=1) # Secondary chart row
        self.plot_grid.grid_columnconfigure(0, weight=1) # Single column

        # Store UI components
        self.sheets[sheet_name]["ui"] = {
            "visual_section": self.visual_section,
            "plot_grid": self.plot_grid,
            "sections": {
                "main_chart": self.create_plot_section("Main Chart", self.plot_grid, 0, 0),
                "secondary_chart": self.create_plot_section("Secondary Chart", self.plot_grid, 1, 0),
                # "statistics": self.create_plot_section("Statistics", self.plot_grid, 0, 1), # Removed
                # "correlations": self.create_plot_section("Correlations", self.plot_grid, 1, 1), # Removed
            }
        }

        # Initialize plots for relevant directions
        self.plots = {}
        for directions_str, (row, col) in {
            "row_0_col_0": [0, 0], # Main
            "row_1_col_0": [1, 0]  # Secondary
            # "row_0_col_1": [0, 1], # Removed statistics
            # "row_1_col_1": [1, 1]  # Removed correlations
        }.items():
            print(f"Initializing frame for {directions_str} at [{row}, {col}]")
            self.create_chart_frame([row, col], directions_str, history=False) # Pass history flag
            if directions_str not in self.plots or not isinstance(self.plots[directions_str], dict):
                self.plots[directions_str] = {}

        # Ensure plots are restored
        if "plots" in self.sheets[sheet_name]:
            self.plots.update(self.sheets[sheet_name]["plots"])
        else:
            self.sheets[sheet_name]["plots"] = self.plots

        # Update the control panel
        self.setup_controls_for_sheet(sheet_name)

    def setup_controls_for_sheet(self, sheet_name):
        """Recreates the controls section dynamically when switching sheets."""
        for widget in self.controls_section.winfo_children():
            if widget not in (self.sheet_controls,):
                widget.destroy()

        # ✅ Controls: Main Chart
        main_chart_section = ttk.LabelFrame(self.controls_section, text="Main Chart", padding=5)
        main_chart_section.pack(fill="both", expand=True, padx=5, pady=5)

        legs_frame_main = ttk.Frame(main_chart_section)
        legs_frame_main.pack(fill="both", expand=True)

        self.sheets[sheet_name]["ui"]["legs_frame_main"] = legs_frame_main

        main_chart_buttons = ttk.Frame(main_chart_section)
        main_chart_buttons.pack(fill="x", padx=5, pady=5)

        btn_add_leg_main = ttk.Button(main_chart_buttons, text="Add Leg", 
                                    command=lambda: [print(f"Main Chart Add Leg: chart_type='main'"), 
                                                    self.open_leg_popup(sheet_name, chart_type="main")])
        btn_add_leg_main.pack(fill="x", padx=5, pady=5)

        btn_plot_main = ttk.Button(main_chart_buttons, text="Plot", 
                                command=lambda: self.plot_chart(chart_type="main", directions_str="row_0_col_0"))
        btn_plot_main.pack(fill="x", padx=5, pady=5)

        for leg_number, selections in self.sheets[sheet_name]["legs"]["main"].items():
            self.display_leg(legs_frame_main, selections, leg_number, sheet_name, "main")

        # ✅ Controls: Secondary Chart
        secondary_chart_section = ttk.LabelFrame(self.controls_section, text="Secondary Chart", padding=5)
        secondary_chart_section.pack(fill="both", expand=True, padx=5, pady=5)

        legs_frame_secondary = ttk.Frame(secondary_chart_section)
        legs_frame_secondary.pack(fill="both", expand=True)

        self.sheets[sheet_name]["ui"]["legs_frame_secondary"] = legs_frame_secondary

        secondary_chart_buttons = ttk.Frame(secondary_chart_section)
        secondary_chart_buttons.pack(fill="x", padx=5, pady=5)

        btn_add_leg_secondary = ttk.Button(secondary_chart_buttons, text="Add Leg", 
                                        command=lambda: [print(f"Secondary Chart Add Leg: chart_type='secondary'"), 
                                                        self.open_leg_popup(sheet_name, chart_type="secondary")])
        btn_add_leg_secondary.pack(fill="x", padx=5, pady=5)

        btn_plot_secondary = ttk.Button(secondary_chart_buttons, text="Plot", 
                                        command=lambda: self.plot_chart(chart_type="secondary", directions_str="row_1_col_0"))
        btn_plot_secondary.pack(fill="x", padx=5, pady=5)

        for leg_number, selections in self.sheets[sheet_name]["legs"]["secondary"].items():
            self.display_leg(legs_frame_secondary, selections, leg_number, sheet_name, "secondary")

        # ✅ History Button for Secondary Chart
        def toggle_history(current_history=True):
            """Toggles history view for the secondary chart and ensures proper chart placement."""

            directions_str_main = "row_0_col_0"  # Main Chart
            directions_str_secondary = "row_1_col_0"  # Secondary Chart (History Chart)
            sheet_name = self.current_sheet

            # ✅ Validate and initialize plot_grid if necessary
            if "ui" not in self.sheets[sheet_name] or not self.sheets[sheet_name]["ui"].get("plot_grid", None) or not self.sheets[sheet_name]["ui"]["plot_grid"].winfo_exists():
                print(f"Error: plot_grid not initialized for {sheet_name}. Reinitializing UI.")
                self.setup_ui_for_sheet(sheet_name)

            # ✅ Ensure self.plots entries exist for both main and secondary charts
            for ds in [directions_str_main, directions_str_secondary]:
                if ds not in self.plots or not isinstance(self.plots.get(ds, {}), dict):
                    print(f"Initializing self.plots for {ds}")
                    self.plots[ds] = {
                        "history_flag": False,
                        "frame": None,
                        "canvas": None,
                        "column_listbox": None,
                        "history_initialized": False
                    }
                    chart_directions = [0, 0] if ds == "row_0_col_0" else [1, 0]
                    self.create_chart_frame(chart_directions, ds, history=False)

            # ✅ Preserve history flag before invalidating cache
            previous_history_flag = self.plots[directions_str_secondary].get("history_flag", False)

            # ✅ Sync secondary chart legs with main chart legs
            print("Syncing secondary chart legs with main chart legs.")
            main_legs = self.sheets[sheet_name]["legs"].get("main", {})
            if main_legs:
                self.sheets[sheet_name]["legs"]["secondary"] = main_legs.copy()
                self.sheets[sheet_name]["leg_count"]["secondary"] = self.sheets[sheet_name]["leg_count"]["main"]
                print(f"Copied {len(main_legs)} legs from Main Chart to Secondary Chart.")

                # ✅ Update the UI to reflect the copied legs
                leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_secondary")
                if not leg_frame or not leg_frame.winfo_exists():
                    print(f"Warning: 'legs_frame_secondary' missing or invalid. Reinitializing UI for {sheet_name}.")
                    self.setup_controls_for_sheet(sheet_name)
                    leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_secondary")

                if leg_frame:
                    # Clear existing legs in the UI
                    for widget in leg_frame.winfo_children():
                        widget.destroy()

                    # Re-display all copied legs
                    for leg_number, selections in self.sheets[sheet_name]["legs"]["secondary"].items():
                        contract = self.create_contract(selections)
                        display_text = f"{contract} x {selections['Weight']}"
                        leg_label = ttk.Label(leg_frame, text=f"Leg {leg_number + 1}")
                        leg_label.pack(fill="x", pady=(10, 2))

                        contract_var = tk.StringVar(value=display_text)
                        leg_entry = ttk.Entry(leg_frame, textvariable=contract_var, state="readonly")
                        leg_entry.pack(fill="x", pady=2)

                        def open_edit_popup(event, sn=sheet_name, ct="secondary", cv=contract_var):
                            self.open_leg_popup_for_editing(cv, sn, ct)

                        leg_entry.bind("<Button-1>", open_edit_popup)
                else:
                    print(f"Error: Failed to initialize 'legs_frame_secondary' for {sheet_name}.")

                # ✅ Update sheet name if needed
                new_sheet_name = self.compute_sheet_name(sheet_name)
                if new_sheet_name != sheet_name:
                    self.sheets[new_sheet_name] = self.sheets.pop(sheet_name)
                    self.current_sheet = new_sheet_name
                    self.sheet_dropdown["values"] = list(self.sheets.keys())
                    self.sheet_var.set(new_sheet_name)
                    sheet_name = new_sheet_name  # Update local reference

            # ✅ Invalidate cache every time history is toggled to force recalculation
            print(f"🚀 Invalidating cache for {sheet_name} at {directions_str_secondary} before replotting history.")
            self.invalidate_spread_cache(sheet_name, directions_str_secondary)

            # ✅ Restore the correct history flag
            new_history = previous_history_flag if previous_history_flag else current_history
            self.plots[directions_str_secondary]["history_flag"] = new_history
            self.sheets[sheet_name]["plots"].setdefault(directions_str_secondary, {})["history"] = new_history

            # ✅ Force new plot by resetting canvas (IMPORTANT FIX!)
            self.plots[directions_str_secondary]["canvas"] = None  # Ensure history chart is re-created from scratch

            # ✅ Ensure correct chart frame exists for the secondary history chart
            print(f"🔄 Ensuring correct chart frame exists for {directions_str_secondary}.")
            self.create_chart_frame(chart_directions=[1, 0], directions_str=directions_str_secondary, history=new_history)

            # ✅ Replot the history chart on the **correct secondary chart (row_1_col_0)**
            # Replot the history chart on the correct secondary chart (row_1_col_0)
            print(f"🔄 Recalculating and re-plotting history for {directions_str_secondary}.")
            self.plot_chart(chart_type="secondary", history=new_history, directions_str=directions_str_secondary)

            # No need to call update_column_options since create_chart_frame handles it
            print(f"✅ History chart updated for {directions_str_secondary}")

            # ✅ Ensure the listbox is populated with all columns after history plot
            spread_df = self.spread_cache.get((tuple(self.current_sheet.split('/')), directions_str_secondary), pd.DataFrame())

            if not spread_df.empty:
                available_columns = list(spread_df.columns)
                self.update_column_options(directions_str_secondary, available_columns)
                print(f"✅ Updated listbox with columns: {available_columns}")
            else:
                print("⚠️ No historical spread data available to populate listbox.")



        btn_history = ttk.Button(self.controls_section, text="History", command=toggle_history)
        btn_history.pack(fill="x", padx=5, pady=5)

        # ✅ Controls: Statistics (Disabled until plotted)
        # statistics_section = ttk.LabelFrame(self.controls_section, text="Statistics", padding=5) # Removed
        # statistics_section.pack(fill="both", expand=True, padx=5, pady=5) # Removed

        # statistics_var = tk.StringVar(value="Select Statistics") # Removed
        # statistics_dropdown = ttk.Combobox(statistics_section, textvariable=statistics_var, # Removed
        # values=["Mean", "Median", "Standard Deviation", "Variance"], state="readonly") # Removed
        # statistics_dropdown.pack(fill="x", padx=5, pady=5) # Removed

        # self.sheets[sheet_name]["ui"]["statistics_dropdown"] = statistics_dropdown # Removed

        # btn_plot_statistics = ttk.Button(statistics_section, text="Plot", # Removed
        # command=lambda: self.plot_statistics(chart_type="statistics", directions_str="row_0_col_1", stat_type=statistics_var.get()) if self.sheets[sheet_name]["legs"].get("statistics", {}) else print("No legs defined for Statistics. Add legs to Main or Secondary chart first.")) # Removed
        # btn_plot_statistics.pack(fill="x", padx=5, pady=5) # Removed

        # ✅ Controls: Correlations (Disabled until plotted)
        # correlations_section = ttk.LabelFrame(self.controls_section, text="Correlations", padding=5) # Removed
        # correlations_section.pack(fill="both", expand=True, padx=5, pady=5) # Removed

        # correlations_var = tk.StringVar(value="Select Correlation Type") # Removed
        # correlations_dropdown = ttk.Combobox(correlations_section, textvariable=correlations_var, # Removed
        # values=["Pearson", "Spearman", "Kendall"], state="readonly") # Removed
        # correlations_dropdown.pack(fill="x", padx=5, pady=5) # Removed

        # self.sheets[sheet_name]["ui"]["correlations_dropdown"] = correlations_dropdown # Removed

        # btn_plot_correlations = ttk.Button(correlations_section, text="Plot", # Removed
        # command=lambda: self.plot_correlations(chart_type="correlations", directions_str="row_1_col_1", corr_type=correlations_var.get()) if self.sheets[sheet_name]["legs"].get("correlations", {}) else print("No legs defined for Correlations. Add legs to Main or Secondary chart first.")) # Removed
        # btn_plot_correlations.pack(fill="x", padx=5, pady=5) # Removed

        # Add the history button after the secondary chart's controls
        btn_history = ttk.Button(self.controls_section, text="History", command=toggle_history)
        btn_history.pack(fill="x", padx=5, pady=5)

    def create_plot_section(self, title, parent_frame, row, column):
        frame = ttk.Frame(parent_frame, padding=5, relief="solid", borderwidth=1)
        frame.grid(row=row, column=column, sticky="nsew")
        return frame

    
    def display_leg(self, parent_frame, selections, leg_number, sheet_name, chart_type):
        """Restores a previously created leg in the UI."""
        display_text = f"{self.create_contract(selections)} x {selections['Weight']}"

        leg_label = ttk.Label(parent_frame, text=f"Leg {leg_number + 1}")
        leg_label.pack(fill="x", pady=(10, 2))

        contract_var = tk.StringVar(value=display_text)
        leg_entry = ttk.Entry(parent_frame, textvariable=contract_var, state="readonly")
        leg_entry.pack(fill="x", pady=2)

        def open_edit_popup(event):
            self.open_leg_popup_for_editing(contract_var, sheet_name, chart_type)

        leg_entry.bind("<Button-1>", open_edit_popup)

    def invalidate_spread_cache(self, sheet_name, directions_str):
        """Invalidate cached spread_df for a given sheet and plot."""
        cache_key = (sheet_name, directions_str)
        if cache_key in self.spread_cache:
            del self.spread_cache[cache_key]
            print(f"🚀 Invalidated spread_df cache for {sheet_name} at {directions_str}")


    def sync_horizontal_resize(self, sheet_name, visual_section):
        """Ensures the horizontal divider moves both top and bottom charts together."""
        try:
            sash_position = visual_section.sash_coord(0)[1]
            visual_section.sash_place(0, 0, sash_position)
        except Exception as e:
            print(f"Error in sync_horizontal_resize: {e}")

    def open_leg_popup(self, sheet_name, chart_type):
        """Opens a pop-up window for selecting leg parameters, ensuring the correct updated sheet name is used."""
        print(f"Opening leg popup for sheet {sheet_name} with chart_type {chart_type}")

        # ✅ Determine the latest updated sheet name
        updated_sheet_name = self.compute_sheet_name(self.current_sheet)  # Use self.current_sheet instead of argument
        
        # ✅ If the sheet has been renamed, update self.current_sheet
        if updated_sheet_name != self.current_sheet:
            print(f"⚠️ Sheet {self.current_sheet} was renamed to {updated_sheet_name}. Updating reference.")
            self.sheets[updated_sheet_name] = self.sheets.pop(self.current_sheet)  # Rename in self.sheets
            self.current_sheet = updated_sheet_name  # Update active sheet
            self.sheet_dropdown["values"] = list(self.sheets.keys())  # Refresh dropdown
            self.sheet_var.set(updated_sheet_name)  # Set dropdown to new name
        
        # ✅ Use the latest updated sheet name for all actions
        sheet_name = self.current_sheet

        # ✅ Ensure sheet exists in self.sheets
        if sheet_name not in self.sheets:
            print(f"⚠️ Warning: {sheet_name} was missing in self.sheets. Initializing...")
            self.sheets[sheet_name] = {
                "legs": {"main": {}, "secondary": {}}, # Removed "statistics", "correlations"
                "leg_count": {"main": 0, "secondary": 0}, # Removed "statistics", "correlations"
                "ui": {},
                "plots": {}
            }

        # ✅ Ensure "leg_count" exists in the sheet
        if "leg_count" not in self.sheets[sheet_name]:
            print(f"⚠️ Warning: 'leg_count' missing for {sheet_name}. Initializing...")
            self.sheets[sheet_name]["leg_count"] = {"main": 0, "secondary": 0} # Removed "statistics", "correlations"

        # ✅ Ensure "legs" exists to avoid KeyError
        if "legs" not in self.sheets[sheet_name]:
            self.sheets[sheet_name]["legs"] = {"main": {}, "secondary": {}} # Removed "statistics", "correlations"

        popup = tk.Toplevel(self.root)
        popup.title(f"Select Leg Parameters ({chart_type.capitalize()} Chart - {sheet_name})")
        popup.geometry("300x450")
        popup.transient(self.root)

        current_year = datetime.now().year
        year_range = [str(y) for y in range(2020, current_year + 6)]

        dropdown_data = {
            "Market": sorted([a for a in self.ta_inst.markets if a not in ['TTF', 'EUA']] + 
                            [a for a in self.ta_inst.markets if a in ['TTF', 'EUA']]),
            "Delivery": ["Base", "Peak"],
            "Product": ["Month", "Quarter", "Year", "Week", "Weekend", "Day"],
            "Period": [],
            "Year": year_range
        }

        selected_values = {}
        dropdown_widgets = {}
        row = 0

        for key, values in dropdown_data.items():
            ttk.Label(popup, text=key).grid(row=row, column=0, padx=5, pady=2, sticky="e")
            var = tk.StringVar()
            dropdown = ttk.Combobox(popup, textvariable=var, values=values, state="readonly")
            dropdown.grid(row=row, column=1, padx=5, pady=2, sticky="w")
            selected_values[key] = var
            dropdown_widgets[key] = dropdown
            row += 1

        period_dropdown = dropdown_widgets["Period"]

        def on_product_change(event):
            product = selected_values["Product"].get()
            period_mapping = {
                "Month": [str(i) for i in range(1, 13)],
                "Quarter": [str(i) for i in range(1, 5)],
                "Year": ["1"],
                "Week": ["1", "2", "3", "4"],
                "Weekend": ["Sat-Sun", "Fri-Sun"],
                "Day": [str(i) for i in range(1, 32)]
            }
            new_options = period_mapping.get(product, [])
            period_dropdown["values"] = new_options
            selected_values["Period"].set("")

        dropdown_widgets["Product"].bind("<<ComboboxSelected>>", on_product_change)

        # ✅ Weight entry (editable)
        ttk.Label(popup, text="Weight").grid(row=row, column=0, padx=5, pady=2, sticky="e")
        selected_values["Weight"] = tk.StringVar()
        weight_entry = ttk.Entry(popup, textvariable=selected_values["Weight"])
        weight_entry.grid(row=row, column=1, padx=5, pady=2, sticky="w")

        # ✅ Get correct leg count using updated sheet name
        leg_count = self.sheets[sheet_name]["leg_count"][chart_type]

        # ✅ Set default weight based on leg count
        if leg_count == 0:
            default_weight = 1  # First leg always gets weight 1
        else:
            last_leg_weight = float(self.sheets[sheet_name]["legs"][chart_type][leg_count - 1]["Weight"])
            default_weight = -last_leg_weight # Alternate sign from last leg

        selected_values["Weight"].set(default_weight)  # ✅ No duplicate entry

        row += 1

        # ✅ Confirm button (Ensures user can submit selections)
        def confirm_leg():
            self.confirm_selection(sheet_name, chart_type, popup, selected_values)

        ttk.Button(popup, text="Confirm", command=confirm_leg).grid(row=row, column=0, columnspan=2, pady=10)

        # ✅ Prevent closing without confirmation
        popup.protocol("WM_DELETE_WINDOW", lambda: self.close_popup(popup))

    def close_popup(self, popup):
        """Handles proper closing of the popup when 'X' is clicked."""
        print("Popup closed without selection.")
        popup.destroy()

    def confirm_selection(self, sheet_name, chart_type, popup, selected_values):
        print(f"Confirming selection for sheet {sheet_name}, chart_type {chart_type}")
        
        # Retrieve selected values
        selections = {k: v.get() for k, v in selected_values.items()}
        contract = self.create_contract(selections)

        # Automatically set weight based on leg number (1, -1, 1, -1, ...)
        leg_number = self.sheets[sheet_name]["leg_count"][chart_type]
        # default_weight = 1 if leg_number % 2 == 0 else -1  # Even leg: 1, Odd leg: -1
        # selections["Weight"] = default_weight  # Override the dropdown selection with the calculated weight
        display_text = f"{contract} x {selections['Weight']}"

        print(f"Leg number {leg_number} for {chart_type} chart ")

        # Ensure UI components are initialized
        if "ui" not in self.sheets[sheet_name]:
            self.sheets[sheet_name]["ui"] = {}
            self.setup_ui_for_sheet(sheet_name)

        # Get directions string for the plot
        directions_str = "row_0_col_0" if chart_type == "main" else "row_1_col_0"
        print(f"Assigned directions_str {directions_str} for chart_type {chart_type}")

        # Invalidate cache
        # ✅ Invalidate cache since a leg was added
        self.invalidate_spread_cache(sheet_name, directions_str)

        # ✅ Replot only main/secondary
        print(f"Calling plot_chart with chart_type {chart_type}, directions_str {directions_str}")
        self.plot_chart(chart_type=chart_type, directions_str=directions_str, first_plot=True)

        # ✅ If history is enabled, trigger history chart plot
        if self.plots.get("row_1_col_0", {}).get("history_flag", False):
            print(f"Replotting history chart since it was enabled for {chart_type}")
            self.plot_chart(chart_type="secondary", history=True, directions_str="row_1_col_0")


        # Handle UI Update for Main Chart
        if chart_type == "main":
            leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_main")
            if not leg_frame:
                print(f"Warning: 'legs_frame_main' missing. Reinitializing UI for {sheet_name}")
                self.setup_controls_for_sheet(sheet_name)
                leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_main")

            if leg_frame:
                leg_label = ttk.Label(leg_frame, text=f"Leg {leg_number + 1}")
                leg_label.pack(fill="x", pady=(10, 2))

                contract_var = tk.StringVar(value=display_text)
                leg_entry = ttk.Entry(leg_frame, textvariable=contract_var, state="readonly")
                leg_entry.pack(fill="x", pady=2)

                def open_edit_popup(event):
                    self.open_leg_popup_for_editing(contract_var, sheet_name, chart_type)

                leg_entry.bind("<Button-1>", open_edit_popup)

                self.sheets[sheet_name]["legs"]["main"][leg_number] = selections
                print(f"Added leg {contract} to Main Chart (leg number {leg_number}) with weight {selections['Weight']}")
            else:
                print(f"Error: Failed to initialize 'legs_frame_main' for {sheet_name}")

        # Handle UI Update for Secondary Chart
        elif chart_type == "secondary":
            leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_secondary")
            if not leg_frame:
                print(f"Warning: 'legs_frame_secondary' missing. Reinitializing UI for {sheet_name}")
                self.setup_controls_for_sheet(sheet_name)
                leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_secondary")

            if leg_frame:
                leg_label = ttk.Label(leg_frame, text=f"Leg {leg_number + 1}")
                leg_label.pack(fill="x", pady=(10, 2))

                contract_var = tk.StringVar(value=display_text)
                leg_entry = ttk.Entry(leg_frame, textvariable=contract_var, state="readonly")
                leg_entry.pack(fill="x", pady=2)

                def open_edit_popup(event):
                    self.open_leg_popup_for_editing(contract_var, sheet_name, chart_type)

                leg_entry.bind("<Button-1>", open_edit_popup)

                self.sheets[sheet_name]["legs"]["secondary"][leg_number] = selections
                print(f"Added leg {contract} to Secondary Chart (leg number {leg_number}) with weight {selections['Weight']}")
            else:
                print(f"Error: Failed to initialize 'legs_frame_secondary' for {sheet_name}")

        # Debug: Inspect the sheets structure
        print(f"Current sheets structure: {self.sheets[sheet_name]['legs']}")

        # Increment leg count for the specific chart type
        self.sheets[sheet_name]["leg_count"][chart_type] += 1

        # Ensure new_sheet_name is correctly assigned and validated
        new_sheet_name = self.compute_sheet_name(sheet_name)

        if not new_sheet_name:
            print(f"⚠️ Warning: Computed new_sheet_name is empty or None. Keeping original sheet_name: {sheet_name}")
            new_sheet_name = sheet_name  # Prevent issues with empty names

        # Ensure old sheet_name exists before renaming
        if sheet_name in self.sheets and new_sheet_name != sheet_name:
            self.sheets[new_sheet_name] = self.sheets.pop(sheet_name)

            # Ensure necessary sub-keys exist to prevent KeyErrors
            self.sheets[new_sheet_name].setdefault("legs", {"main": {}, "secondary": {}}) # Removed "statistics", "correlations"
            self.sheets[new_sheet_name].setdefault("leg_count", {"main": 0, "secondary": 0}) # Removed "statistics", "correlations"
            self.sheets[new_sheet_name].setdefault("plots", {})
            self.sheets[new_sheet_name].setdefault("ui", {})

            # Update active sheet reference
            self.current_sheet = new_sheet_name
            self.sheet_dropdown["values"] = list(self.sheets.keys())
            self.sheet_var.set(new_sheet_name)
            sheet_name = new_sheet_name  # Ensure references are updated

        print(f"✅ Updated sheet name to: {new_sheet_name}")




        # Update self.plots for the current directions_str only if it's main or secondary
        if chart_type in ["main", "secondary"]:
            chart_directions = {
                "row_0_col_0": [0, 0],
                "row_1_col_0": [1, 0]
            }.get(directions_str, [0, 0])
            print(f"Recreating frame for {directions_str} at {chart_directions}")
            if "ui" not in self.sheets[sheet_name] or not self.sheets[sheet_name]["ui"].get("plot_grid", None) or \
            not self.sheets[sheet_name]["ui"]["plot_grid"].winfo_exists():
                print(f"Error: plot_grid does not exist. Reinitializing UI.")
                self.setup_ui_for_sheet(sheet_name)
            self.create_chart_frame(chart_directions, directions_str, history=False)

        # Trigger replot only for main or secondary
        if chart_type in ["main", "secondary"]:
            print(f"Calling plot_chart with chart_type {chart_type}, directions_str {directions_str}")
            self.plot_chart(chart_type=chart_type, directions_str=directions_str, first_plot=True)

        # Close the pop-up
        popup.destroy()

    def open_leg_popup_for_editing(self, contract_var, sheet_name, chart_type):
        # Use the updated current sheet name
        sheet_name = self.current_sheet
        """Opens a pop-up to edit an existing contract selection and updates sheet name."""
        popup = tk.Toplevel(self.root)
        popup.title(f"Edit Contract ({chart_type.capitalize()} Chart - {sheet_name})")
        popup.geometry("300x400")
        popup.transient(self.root)

        current_year = datetime.now().year
        year_range = [str(y) for y in range(2020, current_year + 6)]

        dropdown_data = {
            "Market": sorted([a for a in self.ta_inst.markets if a not in ['TTF', 'EUA']] + 
                            [a for a in self.ta_inst.markets if a in ['TTF', 'EUA']]),
            "Delivery": ["Base", "Peak"],
            "Product": ["Month", "Quarter", "Year", "Week", "Weekend", "Day"],
            "Period": [],
            "Year": year_range
        }

        selected_values = {}
        dropdown_widgets = {}

        # Identify the leg being edited
        leg_number = None
        for num, stored_selections in self.sheets[sheet_name]["legs"][chart_type].items():
            if f"{self.create_contract(stored_selections)} x {stored_selections['Weight']}" == contract_var.get():
                leg_number = num
                break

        if leg_number is None:
            print("Error: Could not identify the leg being edited.")
            popup.destroy()
            return

        # Pre-fill dropdowns with existing values
        for key, values in dropdown_data.items():
            ttk.Label(popup, text=key).pack(pady=2)
            var = tk.StringVar(value=self.sheets[sheet_name]["legs"][chart_type][leg_number].get(key, ""))
            dropdown = ttk.Combobox(popup, textvariable=var, values=values, state="readonly")
            dropdown.pack(pady=2, fill="x")

            selected_values[key] = var
            dropdown_widgets[key] = dropdown  

        period_dropdown = dropdown_widgets["Period"]

        def on_product_change(event):
            product = selected_values["Product"].get()
            period_mapping = {
                "Month": [str(i) for i in range(1, 13)],
                "Quarter": [str(i) for i in range(1, 5)],
                "Year": ["1"],
                "Week": ["1", "2", "3", "4"],
                "Weekend": ["Sat-Sun", "Fri-Sun"],
                "Day": [str(i) for i in range(1, 32)]
            }
            new_options = period_mapping.get(product, [])
            period_dropdown["values"] = new_options
            selected_values["Period"].set("")

        dropdown_widgets["Product"].bind("<<ComboboxSelected>>", on_product_change)

        # Weight Field
        ttk.Label(popup, text="Weight").pack(pady=2)
        selected_values["Weight"] = tk.StringVar(value=self.sheets[sheet_name]["legs"][chart_type][leg_number]["Weight"])
        weight_entry = ttk.Entry(popup, textvariable=selected_values["Weight"])
        weight_entry.pack(pady=2, fill="x")

        def confirm_edit():
            """Update the contract, selections, and sheet name upon confirming."""
            nonlocal sheet_name  # Ensure `sheet_name` from `open_leg_popup_for_editing()` is used
            
            # Retrieve selected values
            new_selections = {k: v.get() for k, v in selected_values.items()}
            new_contract = self.create_contract(new_selections)

            # Update UI display
            contract_var.set(f"{new_contract} x {new_selections['Weight']}")

            # Ensure `sheet_name` exists before modifying self.sheets
            if sheet_name not in self.sheets:
                print(f"⚠️ Warning: Sheet '{sheet_name}' not found! Reinitializing it.")
                self.sheets[sheet_name] = {
                    "legs": {"main": {}, "secondary": {}}, # Removed "statistics", "correlations"
                    "leg_count": {"main": 0, "secondary": 0}, # Removed "statistics", "correlations"
                    "ui": {},
                    "plots": {},
                }

            # Ensure the leg number exists before updating
            if leg_number not in self.sheets[sheet_name]["legs"][chart_type]:
                print(f"⚠️ Warning: Leg {leg_number} not found in {chart_type}! Skipping update.")
                return  

            # ✅ Now we can safely update
            self.sheets[sheet_name]["legs"][chart_type][leg_number] = new_selections

            # ✅ Invalidate cache since leg changed
            directions_str = "row_0_col_0" if chart_type == "main" else "row_1_col_0"
            self.invalidate_spread_cache(sheet_name, directions_str)

            # ✅ Update sheet name if necessary
            new_sheet_name = self.compute_sheet_name(sheet_name)
            if new_sheet_name != sheet_name:
                self.sheets[new_sheet_name] = self.sheets.pop(sheet_name)
                self.current_sheet = new_sheet_name
                self.sheet_dropdown["values"] = list(self.sheets.keys())
                self.sheet_var.set(new_sheet_name)
                sheet_name = new_sheet_name  # Update local reference

            # ✅ Trigger replot
            self.plot_chart(chart_type=chart_type, directions_str=directions_str)

            popup.destroy()

        
        ttk.Button(popup, text="Confirm", command=confirm_edit).pack(pady=10)
        
        # Prevent closing without confirmation
        popup.protocol("WM_DELETE_WINDOW", lambda: self.close_popup(popup))



    @staticmethod
    def create_contract(selections):
        """Formats contract string from dropdown selections."""
        contract = "_".join(
            v if k == "Market" else
            {"Base": "B", "Peak": "P"}.get(v, v) if k == "Delivery" else
            {"Month": "M", "Quarter": "Q", "Year": "Y",
             "Week": "W", "Weekend": "Wknd", "Day": "D"}.get(v, v) if k == "Product" else
            str(v) if k == "Period" else
            str(v)[2:] if k == "Year" else None
            for k, v in selections.items() if k in {"Market", "Delivery", "Product", "Period", "Year"} and v
        )
        return contract
    
    @staticmethod
    def collect_weights(selections):
        """Extracts valid weights as a list of floats from selections"""
        weights = [float(v) for k, v in selections.items() if k == 'Weight' and v not in [None, "", 0]]
        
        if not weights:  # Ensure at least one valid weight is returned
            print("⚠️ Warning: No valid weights found in selections:", selections)
        
        return weights



    def plot_chart(self, chart_type="main", history=False, mean_var=None, directions_str=None):
        """Base implementation for plotting, delegating to subclass or providing a fallback."""
        if not self.current_sheet:
            print("Error: No active sheet to plot on.")
            return

        sheet_name = self.current_sheet
        directions_str = directions_str or ("row_0_col_0" if chart_type == "main" else "row_1_col_0")
        
        # Ensure plots dictionary exists
        if directions_str not in self.sheets[sheet_name]["plots"]:
            self.sheets[sheet_name]["plots"][directions_str] = {}
        
        legs = self.sheets[sheet_name]["legs"].get(chart_type, {})
        if not legs:
            print(f"No legs defined for {chart_type} chart.")
            return
        
        # Placeholder for subclass override
        print(f"Base plot_chart called for {chart_type} at {directions_str} (history={history})")
    def show_history(sefl):
        """Placeholder for history ploting chart"""
        pass


    def on_closing(self):
        """Ensure the app fully closes only when the window is actually closed."""
        print("Closing application...")

        # Ask for confirmation before closing (optional)
        if not tk.messagebox.askokcancel("Quit", "Do you really want to exit?"):
            return  # Cancels the close event

        # Destroy all child windows (pop-ups) first
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel):  
                widget.destroy()

        # Stop the Tkinter main loop properly
        self.root.quit()
        self.root.destroy()

        # Fully terminate Python process
        sys.exit(0)




    
    def add_leg(self):
        print("Adding new leg (dropdown logic to be implemented)")
    


if __name__ == "__main__":
    root = tk.Tk()
    app = TechAnalysisTool(root)
    root.mainloop()
