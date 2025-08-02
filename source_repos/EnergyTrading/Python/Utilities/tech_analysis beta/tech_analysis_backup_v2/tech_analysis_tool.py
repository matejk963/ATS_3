#%%

import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from datetime import datetime
import sys
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager
# 'DE', 'FR', 'HU', 'IT', 'CZ', 'SK', 'EUA', 'ES'
class TechAnalysisTool:
    def __init__(self, root):
        self.ta_inst = TechAnalysis_manager(markets=['TTF','DE', 'FR', 'HU', 'AT',
                                                     'IT', 'CZ', 'SK', 'EUA', 'ES', "NL"])
        self.ta_inst.load_data()

        self.root = root
        self.root.title("Tech Analysis Tool")
        self.root.geometry("1000x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.sheets = {}  # Stores sheets and their UI elements
        self.current_sheet = None  # Active sheet tracker

        # ✅ Initialize the spread cache to store spread_df for faster replotting
        self.spread_cache = {}

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
        """Creates a new sheet and switches to it."""
        sheet_number = len(self.sheets) + 1
        sheet_name = f"Sheet {sheet_number}"
        self.current_sheet = sheet_name  # ✅ Set current sheet

        # ✅ Ensure each sheet has its own attributes
        self.sheets[sheet_name] = {
            "legs": {"main": {}, "secondary": {}},
            "leg_count": {"main": 0, "secondary": 0},  # ✅ Initialize leg_count here
            "ui": {},
            "plots": {}  # ✅ Store plots for this sheet separately
        }

        self.sheet_dropdown["values"] = list(self.sheets.keys())
        self.sheet_var.set(sheet_name)
        self.sheet_dropdown.bind("<<ComboboxSelected>>", self.switch_sheet)

        self.setup_ui_for_sheet(sheet_name)

    def switch_sheet(self, event=None):
        """Switch to a different sheet, ensuring correct UI and plots are loaded."""
        selected_sheet = self.sheet_var.get()
        if selected_sheet in self.sheets:
            self.current_sheet = selected_sheet  # ✅ Set the active sheet

            # ✅ Ensure plots dictionary exists for this sheet
            if "plots" not in self.sheets[selected_sheet]:
                self.sheets[selected_sheet]["plots"] = {}

            # ✅ Restore self.plots reference for the selected sheet
            self.plots = self.sheets[selected_sheet]["plots"]  

            # ✅ Recreate UI components for the new sheet
            self.setup_ui_for_sheet(selected_sheet)

            # ✅ Restore all plots across all chart sections
            for directions_str, latest_plot in self.sheets[selected_sheet]["plots"].items():
                print(f"Restoring plot for {selected_sheet} at {directions_str}...")

                # ✅ Ensure the frame exists before re-plotting
                chart_directions = {
                    "row_0_col_0": [0, 0],
                    "row_0_col_1": [0, 1],
                    "row_1_col_0": [1, 0],
                    "row_1_col_1": [1, 1]
                }.get(directions_str, [0, 0])  

                self.create_chart_frame(chart_directions, directions_str, history=latest_plot.get("history", False))

                # ✅ Ensure the required keys exist to avoid KeyError
                chart_type = latest_plot.get("chart_type", "main")  # Default to "main" if missing
                history = latest_plot.get("history", False)

                # ✅ Retrieve the last stored mean_var from `latest_plot`
                mean_var = latest_plot.get("mean_var", tk.IntVar(value=0))
                self.sheets[selected_sheet]["plots"][directions_str]["mean_var"] = mean_var  # ✅ Store it back

                # ✅ Create the checkbox using the stored `mean_var`
                self.create_checkbox(directions_str)

                # ✅ Restore the listbox for history plots
                if history and "column_listbox" in latest_plot:
                    self.update_column_options(directions_str, latest_plot["spread_df"].columns)

                # ✅ Plot the stored data
                self.plot_chart(
                    chart_type=chart_type,
                    history=history,
                    mean_var=self.sheets[selected_sheet]["plots"][directions_str]["mean_var"],  # ✅ Always retrieve latest stored reference
                    directions_str=directions_str
                )



    def setup_ui_for_sheet(self, sheet_name):
        """Sets up the UI components for a given sheet, ensuring correct plots are retained."""

        # ✅ Remove old visual section completely before switching sheets
        if hasattr(self, "visual_section"):
            self.visual_section.destroy()

        # ✅ Create Right Panel: Visual Section
        self.visual_section = ttk.Frame(self.main_pane)
        self.main_pane.add(self.visual_section)

        # ✅ Create 2x2 Grid Frame for charts
        self.plot_grid = ttk.Frame(self.visual_section)
        self.plot_grid.pack(fill="both", expand=True)

        # ✅ Configure grid layout (2 rows, 2 columns)
        for i in range(2):
            self.plot_grid.grid_rowconfigure(i, weight=1)
            self.plot_grid.grid_columnconfigure(i, weight=1)

        # ✅ Restore stored UI components for this sheet
        self.sheets[sheet_name]["ui"] = {
            "visual_section": self.visual_section,
            "plot_grid": self.plot_grid,
            "sections": {
                "main_chart": self.create_plot_section("Main Chart", self.plot_grid, 0, 0),
                "statistics": self.create_plot_section("Statistics", self.plot_grid, 0, 1),
                "secondary_chart": self.create_plot_section("Secondary Chart", self.plot_grid, 1, 0),
                "correlations": self.create_plot_section("Correlations", self.plot_grid, 1, 1),
            }
        }

        # ✅ Ensure stored plots are restored
        if "plots" in self.sheets[sheet_name]:
            self.plots = self.sheets[sheet_name]["plots"]  # ✅ Load plots for this sheet
        else:
            self.plots = {}  # ✅ Reset if no plots exist yet

        # ✅ Update the control panel
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

        # ✅ Store the leg frame in the sheet UI dictionary
        self.sheets[sheet_name]["ui"]["legs_frame_main"] = legs_frame_main

        main_chart_buttons = ttk.Frame(main_chart_section)
        main_chart_buttons.pack(fill="x", padx=5, pady=5)

        btn_add_leg_main = ttk.Button(main_chart_buttons, text="Add Leg", command=lambda: self.open_leg_popup(sheet_name, "main"))
        btn_add_leg_main.pack(fill="x", padx=5, pady=5)

        btn_plot_main = ttk.Button(main_chart_buttons, text="Plot", command=self.plot_chart)
        btn_plot_main.pack(fill="x", padx=5, pady=5)

        # ✅ Restore stored legs for Main Chart
        for leg_number, selections in self.sheets[sheet_name]["legs"]["main"].items():
            self.display_leg(legs_frame_main, selections, leg_number, sheet_name, "main")

        # ✅ Controls: Secondary Chart
        secondary_chart_section = ttk.LabelFrame(self.controls_section, text="Secondary Chart", padding=5)
        secondary_chart_section.pack(fill="both", expand=True, padx=5, pady=5)

        legs_frame_secondary = ttk.Frame(secondary_chart_section)
        legs_frame_secondary.pack(fill="both", expand=True)

        # ✅ Store the leg frame in the sheet UI dictionary
        self.sheets[sheet_name]["ui"]["legs_frame_secondary"] = legs_frame_secondary

        secondary_chart_buttons = ttk.Frame(secondary_chart_section)
        secondary_chart_buttons.pack(fill="x", padx=5, pady=5)

        btn_add_leg_secondary = ttk.Button(secondary_chart_buttons, text="Add Leg", command=lambda: self.open_leg_popup(sheet_name, "secondary"))
        btn_add_leg_secondary.pack(fill="x", padx=5, pady=5)

        btn_plot_secondary = ttk.Button(secondary_chart_buttons, text="Plot", command=lambda: self.plot_chart(chart_type='secondary'))
        btn_plot_secondary.pack(fill="x", padx=5, pady=5)

        btn_history = ttk.Button(secondary_chart_buttons, text="History", command=lambda: self.plot_chart(chart_type='secondary', history=True))
        btn_history.pack(fill="x", padx=5, pady=5)

        # ✅ Restore stored legs for Secondary Chart
        for leg_number, selections in self.sheets[sheet_name]["legs"]["secondary"].items():
            self.display_leg(legs_frame_secondary, selections, leg_number, sheet_name, "secondary")

        # ✅ Controls: Statistics
        statistics_section = ttk.LabelFrame(self.controls_section, text="Statistics", padding=5)
        statistics_section.pack(fill="both", expand=True, padx=5, pady=5)

        statistics_var = tk.StringVar(value="Select Statistics")
        statistics_dropdown = ttk.Combobox(statistics_section, textvariable=statistics_var,
                                        values=["Mean", "Median", "Standard Deviation", "Variance"], state="readonly")
        statistics_dropdown.pack(fill="x", padx=5, pady=5)

        self.sheets[sheet_name]["ui"]["statistics_dropdown"] = statistics_dropdown

        # ✅ Controls: Correlations
        correlations_section = ttk.LabelFrame(self.controls_section, text="Correlations", padding=5)
        correlations_section.pack(fill="both", expand=True, padx=5, pady=5)

        correlations_var = tk.StringVar(value="Select Correlation Type")
        correlations_dropdown = ttk.Combobox(correlations_section, textvariable=correlations_var,
                                            values=["Pearson", "Spearman", "Kendall"], state="readonly")
        correlations_dropdown.pack(fill="x", padx=5, pady=5)

        self.sheets[sheet_name]["ui"]["correlations_dropdown"] = correlations_dropdown



    def create_plot_section(self, title, parent_frame, row, column):
        """Creates a resizable plot section inside a grid layout."""
        frame = ttk.Frame(parent_frame, padding=5, relief="solid", borderwidth=1)
        frame.grid(row=row, column=column, sticky="nsew")  # ✅ Ensure proper placement

        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([1, 2, 3], [5, 7, 3], label="Dummy Data")
        ax.set_title(title)
        ax.legend()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)

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

    def open_leg_popup(self, sheet_name, chart_type="main"):
        """Opens a pop-up window with dropdowns for leg selection for the given sheet and chart type."""
        popup = tk.Toplevel(self.root)
        popup.title(f"Select Leg Parameters ({chart_type.capitalize()} Chart - {sheet_name})")
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

        for key, values in dropdown_data.items():
            ttk.Label(popup, text=key).pack(pady=2)
            var = tk.StringVar()
            dropdown = ttk.Combobox(popup, textvariable=var, values=values, state="readonly")
            dropdown.pack(pady=2, fill="x")

            selected_values[key] = var
            dropdown_widgets[key] = dropdown  # Store reference to dropdowns

        period_dropdown = dropdown_widgets["Period"]

        def on_product_change(event):
            """Updates the 'Period' dropdown dynamically based on 'Product' selection."""
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
            selected_values["Period"].set("")  # Clear previous selection

        dropdown_widgets["Product"].bind("<<ComboboxSelected>>", on_product_change)

        ttk.Label(popup, text="Weight").pack(pady=2)
        selected_values["Weight"] = tk.StringVar()
        weight_entry = ttk.Entry(popup, textvariable=selected_values["Weight"])
        weight_entry.pack(pady=2, fill="x")

        # ✅ Ensure sheet and leg_count exist
        if sheet_name not in self.sheets:
            self.sheets[sheet_name] = {"legs": {"main": {}, "secondary": {}}, "leg_count": {"main": 0, "secondary": 0}}

        selected_values["Weight"].set("1" if self.sheets[sheet_name]["leg_count"][chart_type] % 2 == 0 else "-1")

        # ✅ Fix: Correctly pass `popup` and `selected_values` to confirm_selection
        ttk.Button(
            popup, text="Confirm", 
            command=lambda: self.confirm_selection(sheet_name, chart_type, popup, selected_values)
        ).pack(pady=10)

    def confirm_selection(self, sheet_name, chart_type, popup, selected_values):
        """Handles leg selection confirmation and invalidates spread cache for replotting."""
        
        # Retrieve selected values
        selections = {k: v.get() for k, v in selected_values.items()}
        contract = self.create_contract(selections)
        display_text = f"{contract} x {selections['Weight']}"

        # Identify leg number
        leg_number = self.sheets[sheet_name]["leg_count"][chart_type]

        # Ensure UI components are initialized
        if "ui" not in self.sheets[sheet_name]:
            self.sheets[sheet_name]["ui"] = {}

        # Get directions string for the plot (main or secondary)
        directions_str = "row_0_col_0" if chart_type == "main" else "row_1_col_0"

        # ✅ Invalidate cached spread_df when a new leg is added
        self.invalidate_spread_cache(sheet_name, directions_str)

        # ✅ Handle UI Update for Main Chart
        if chart_type == "main":
            leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_main", None)
            if not leg_frame:
                print(f"Warning: 'legs_frame_main' is missing for sheet {sheet_name}")
                return

            leg_label = ttk.Label(leg_frame, text=f"Leg {leg_number + 1}")
            leg_label.pack(fill="x", pady=(10, 2))

            contract_var = tk.StringVar(value=display_text)
            leg_entry = ttk.Entry(leg_frame, textvariable=contract_var, state="readonly")
            leg_entry.pack(fill="x", pady=2)

            def open_edit_popup(event):
                self.open_leg_popup_for_editing(contract_var, sheet_name, chart_type)

            leg_entry.bind("<Button-1>", open_edit_popup)

            self.sheets[sheet_name]["legs"]["main"][leg_number] = selections

        # ✅ Handle UI Update for Secondary Chart
        elif chart_type == "secondary":
            leg_frame = self.sheets[sheet_name]["ui"].get("legs_frame_secondary", None)
            if not leg_frame:
                print(f"Warning: 'legs_frame_secondary' is missing for sheet {sheet_name}")
                return

            leg_label = ttk.Label(leg_frame, text=f"Leg {leg_number + 1}")
            leg_label.pack(fill="x", pady=(10, 2))

            contract_var = tk.StringVar(value=display_text)
            leg_entry = ttk.Entry(leg_frame, textvariable=contract_var, state="readonly")
            leg_entry.pack(fill="x", pady=2)

            def open_edit_popup(event):
                self.open_leg_popup_for_editing(contract_var, sheet_name, chart_type)

            leg_entry.bind("<Button-1>", open_edit_popup)

            self.sheets[sheet_name]["legs"]["secondary"][leg_number] = selections

        # ✅ Increment leg count per sheet & chart
        self.sheets[sheet_name]["leg_count"][chart_type] += 1

        # ✅ Automatically trigger replot after modifying legs
        self.plot_chart(chart_type=chart_type, directions_str=directions_str)

        # Close the pop-up after confirming
        popup.destroy()

    def open_leg_popup_for_editing(self, contract_var, sheet_name, chart_type):
        """Opens a pop-up to edit an existing contract selection."""
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

        # ✅ Identify the leg being edited
        leg_number = None
        for num, stored_selections in self.sheets[sheet_name]["legs"][chart_type].items():
            if f"{self.create_contract(stored_selections)} x {stored_selections['Weight']}" == contract_var.get():
                leg_number = num
                break

        if leg_number is None:
            print("Error: Could not identify the leg being edited.")
            popup.destroy()
            return

        # ✅ Pre-fill dropdowns with existing values
        for key, values in dropdown_data.items():
            ttk.Label(popup, text=key).pack(pady=2)
            var = tk.StringVar(value=self.sheets[sheet_name]["legs"][chart_type][leg_number].get(key, ""))
            dropdown = ttk.Combobox(popup, textvariable=var, values=values, state="readonly")
            dropdown.pack(pady=2, fill="x")

            selected_values[key] = var
            dropdown_widgets[key] = dropdown  

        period_dropdown = dropdown_widgets["Period"]

        def on_product_change(event):
            """Updates the 'Period' dropdown dynamically based on 'Product' selection."""
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
            selected_values["Period"].set("")  # Clear previous selection

        dropdown_widgets["Product"].bind("<<ComboboxSelected>>", on_product_change)

        # ✅ Weight Field
        ttk.Label(popup, text="Weight").pack(pady=2)
        selected_values["Weight"] = tk.StringVar(value=self.sheets[sheet_name]["legs"][chart_type][leg_number]["Weight"])
        weight_entry = ttk.Entry(popup, textvariable=selected_values["Weight"])
        weight_entry.pack(pady=2, fill="x")

        def confirm_edit():
            """Update the contract and selections upon confirming."""
            new_selections = {k: v.get() for k, v in selected_values.items()}
            new_contract = self.create_contract(new_selections)

            # ✅ Update UI display
            contract_var.set(f"{new_contract} x {new_selections['Weight']}")  

            # ✅ Update the stored selections in `self.sheets`
            self.sheets[sheet_name]["legs"][chart_type][leg_number] = new_selections

            popup.destroy()

        ttk.Button(popup, text="Confirm", command=confirm_edit).pack(pady=10)




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
        return [float(v) for k, v in selections.items() if k == 'Weight']


    def plot_chart(self):
        """Placeholder function for plotting."""
        print("Plotting data...")
    def show_history(sefl):
        """Placeholder for history ploting chart"""
        pass


    def on_closing(self):
        """Ensure the app fully closes only when the window is actually closed."""
        print("Closing application...")

        # ✅ Ask for confirmation before closing (optional)
        if not tk.messagebox.askokcancel("Quit", "Do you really want to exit?"):
            return  # Cancels the close event

        # ✅ Destroy all child windows (pop-ups) first
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel):  
                widget.destroy()

        # ✅ Stop the Tkinter main loop properly
        self.root.quit()
        self.root.destroy()

        # ✅ Fully terminate Python process
        sys.exit(0)  





    
    def add_leg(self):
        print("Adding new leg (dropdown logic to be implemented)")
    


if __name__ == "__main__":
    root = tk.Tk()
    app = TechAnalysisTool(root)
    root.mainloop()
