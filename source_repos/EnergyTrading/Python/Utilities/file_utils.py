

def file_dialog():
    import os
    from IPython.display import display, Javascript

    def select_file_via_terminal():
        display(Javascript('''
        var kernel = Jupyter.notebook.kernel;
        var path = prompt("Enter the path of your file:");
        kernel.execute("file_path = '" + path + "'");
        '''))

    select_file_via_terminal()
    # Now you can use the file_path variable to open the file
    try:
        with open(file_path, 'r') as file:
            data = file.read()
            return data
    except Exception as e:
        print(f"An error occurred: {e}")