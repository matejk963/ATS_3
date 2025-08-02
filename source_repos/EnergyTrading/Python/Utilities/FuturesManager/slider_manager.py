import pandas as pd
import tkinter as tk


class SliderManager:
    def __init__(self, app):
        self.app = app
        self.slider_frame = None
        self.start_slider = None
        self.end_slider = None
        self.start_date_var = tk.StringVar(value="")
        self.end_date_var = tk.StringVar(value="")

    def add_date_range_slider(self, df):
        """Add sliders for filtering data by date range."""
        if self.slider_frame:
            self.slider_frame.destroy()

        self.slider_frame = tk.Frame(self.app.main_frame)
        self.slider_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        df = df.sort_index()
        index_values = df.index

        # Start slider
        tk.Label(self.slider_frame, text="Start Date:").pack(side=tk.LEFT, padx=5)
        self.start_slider = tk.Scale(
            self.slider_frame,
            from_=0,
            to=len(index_values) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            command=lambda value: self.update_start_date(index_values, int(value)),
        )
        self.start_slider.pack(side=tk.LEFT, padx=5)
        self.start_slider.set(0)
        self.start_date_var.set(str(index_values[0]))
        tk.Label(self.slider_frame, textvariable=self.start_date_var).pack(side=tk.LEFT, padx=5)

        # End slider
        tk.Label(self.slider_frame, text="End Date:").pack(side=tk.LEFT, padx=5)
        self.end_slider = tk.Scale(
            self.slider_frame,
            from_=0,
            to=len(index_values) - 1,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=300,
            command=lambda value: self.update_end_date(index_values, int(value)),
        )
        self.end_slider.pack(side=tk.LEFT, padx=5)
        self.end_slider.set(len(index_values) - 1)
        self.end_date_var.set(str(index_values[-1]))
        tk.Label(self.slider_frame, textvariable=self.end_date_var).pack(side=tk.LEFT, padx=5)

        self.update_plots_with_slider(index_values)

    def update_start_date(self, index_values, slider_value):
        """Update the start date from the slider."""
        self.start_date_var.set(str(index_values[slider_value]))
        self.update_plots_with_slider(index_values)

    def update_end_date(self, index_values, slider_value):
        """Update the end date from the slider."""
        self.end_date_var.set(str(index_values[slider_value]))
        self.update_plots_with_slider(index_values)

    def update_plots_with_slider(self, index_values):
        """Filter data and update plots based on slider values."""
        start_date = index_values[self.start_slider.get()]
        end_date = index_values[self.end_slider.get()]

        main_df = self.app.data_manager.current_filtered_df.loc[start_date:end_date]
        comparison_df = (
            self.app.data_manager.comparison_filtered_df.loc[start_date:end_date]
            if self.app.data_manager.comparison_filtered_df is not None
            else None
        )

        self.app.plot_manager.plot_main(main_df, "Main Plot")
        if comparison_df is not None:
            self.app.plot_manager.plot_comparison(comparison_df, "Comparison Plot")
