import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PlotManager:
    def __init__(self, app):
        self.app = app
        self.main_plot_canvas = None
        self.comparison_plot_canvas = None

    def plot(self, df, frame, title, plot_height):
        """Generalized plotting logic."""
        if df.empty:
            print(f"Warning: No data to plot for {title}")
            return None

        plt.close('all')
        fig, ax = plt.subplots(figsize=(8, plot_height))

        for column in df.columns:
            df[column].plot(ax=ax, label=column)
            last_index = df.index[-1]
            last_value = df[column].iloc[-1]
            ax.text(
                last_index,
                last_value,
                f"{last_value:.2f}",
                color=ax.lines[-1].get_color(),
                fontsize=10,
                ha="right",
                va="center",
            )

        ax.set_title(title, fontsize=14)
        ax.grid(True)
        ax.legend()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return canvas

    def plot_main(self, df, title):
        """Plot the main DataFrame."""
        if self.main_plot_canvas:
            self.main_plot_canvas.get_tk_widget().destroy()
        self.main_plot_canvas = self.plot(df, self.app.main_plot_frame, title, plot_height=4)

    def plot_comparison(self, df, title):
        """Plot the comparison DataFrame."""
        if self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
        self.comparison_plot_canvas = self.plot(df, self.app.comparison_plot_frame, title, plot_height=2)

    def clear_plots(self):
        """Clear both main and comparison plots."""
        if self.main_plot_canvas:
            self.main_plot_canvas.get_tk_widget().destroy()
            self.main_plot_canvas = None
        if self.comparison_plot_canvas:
            self.comparison_plot_canvas.get_tk_widget().destroy()
            self.comparison_plot_canvas = None
