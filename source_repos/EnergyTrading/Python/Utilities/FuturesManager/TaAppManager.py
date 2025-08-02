import tkinter as tk
from dropdown_manager import DropdownManager
from plot_manager import PlotManager
from slider_manager import SliderManager
from checkbox_manager import CheckboxManager
from data_manager import DataManager

class AppManager:
    def __init__(self, root, data):
        self.root = root
        self.data_manager = DataManager(data)
        self.dropdown_manager = DropdownManager(self)
        self.plot_manager = PlotManager(self)
        self.slider_manager = SliderManager(self)
        self.checkbox_manager = CheckboxManager(self)

        # Layout
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.dropdown_frame = tk.Frame(self.main_frame)
        self.dropdown_frame.pack(side=tk.TOP, padx=5, pady=5)

        self.main_checkbox_frame = tk.Frame(self.main_frame, width=200)
        self.main_checkbox_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.main_plot_frame = tk.Frame(self.main_frame)
        self.main_plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.comparison_checkbox_frame = tk.Frame(self.main_frame, width=200)
        self.comparison_checkbox_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.comparison_plot_frame = tk.Frame(self.main_frame)
        self.comparison_plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.dropdown_manager.create_new_dropdown(data, self.dropdown_frame)


    def add_comparison_dropdown(self):
        """Delegate creation of comparison dropdown."""
        self.dropdown_manager.create_new_dropdown(self.data, self.comparison_dropdown_frame, comparison=True)

    def on_closing(self):
        """Cleanup resources and exit."""
        self.plot_manager.clear_all_plots()
        self.root.quit()
        self.root.destroy()
        
    @staticmethod
    def calculate_dropdown_width(values):
        """
        Calculate the width for the dropdown based on the longest string in values.
        :param values: List of dropdown options.
        :return: Width of the dropdown.
        """
        if not values:
            return 10  # Default width if no values
        longest_value = max(values, key=len)
        return len(longest_value) + 2  # Add padding for better display


# Entry point for the application
if __name__ == "__main__":
    import pickle

    file_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\temp\data_dict2.pkl'
    with open(file_path, "rb") as f:
        data_dict = pickle.load(f)

    root = tk.Tk()
    root.title("Dictionary Explorer")
    app = AppManager(root, data_dict)
    root.mainloop()

