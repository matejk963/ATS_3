from bokeh.plotting import figure, show
from bokeh.palettes import Category10_10 
from bokeh.layouts import gridplot
from screeninfo import get_monitors

def bokehPlot(df_in, col_list=None, sub=1, index=None, scatter=[], title="Plot"):
    df = df_in.copy()
    if col_list is None:
        col_list = [df.columns]
    monitors = get_monitors()
    screen_width = monitors[0].width  # Assuming the first monitor
    screen_height = monitors[0].height-100
    # Assuming df is a DataFrame with appropriate columns
    if index is None:
        df['index'] = df.index  # Create an 'index' column for Bokeh
    else :
        df['index'] = df[index]

    subplots = []
    colors = Category10_10
    for i in range(sub):
        f = figure(width=screen_width, height=screen_height // sub, title=title, x_axis_label="Index", y_axis_label="Value")
        for j,col in enumerate(col_list[i]):
            color = colors[j]
            if col in scatter:
                f.circle('index', col, source=df, legend_label=col, line_color=color)
            else:
                f.line('index', col, source=df, legend_label=col, line_color=color)
        subplots.append(f)

    # Combine the subplots
    # layout = gridplot([[p1], [p2]])
    layout = gridplot([[x] for x in subplots])
    # Show the plot
    show(layout)


# fig = go.Figure()
# fig.add_trace(go.Scatter(x=df_data.index, y=df_data['trd_price']))
# fig.add_trace(go.Scatter(
#     x=df['timestamp'],
#     y=df['price_level'],
#     mode='markers',
#     marker=dict(color=df['position']),  # Using dict() for clarity
#     customdata=[['<BR><b>pb_bid: </b> '+str(df.loc[i, 'pb_bid']),
#                   '<BR><b>pb_ask:</b> '+str(df.loc[i, 'pb_ask'])]
#                  for i in df.index],
#     hovertemplate=
#         '<b>%{x} </b> <br>' +  # Displaying X value
#         '<b>Price Level:</b> %{y:.2f}<br>' +  # Displaying Y value with label
#         '%{customdata}'  # Displaying custom data
# ))

# pio.show(fig)