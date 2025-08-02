import sys
import pickle
import os
from datetime import datetime
import traceback

class CaptureExceptionsInJupyter:
    """
    Context manager to capture exceptions in Jupyter and save local variables.
    """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type is not None:
            # Capture and save locals on crash
            capture_locals_on_crash(exc_type, exc_value, exc_traceback)
            # Print traceback to the notebook output
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            return True  # Prevents Jupyter from showing the error twice


# Helper function to filter out non-pickleable objects and avoid saving function references
def safe_pickle(value):
    try:
        if callable(value):
            return "<Function reference>"  # Avoid saving function references
        return pickle.dumps(value)  # Try to pickle the object
    except Exception:
        return "<Non-pickleable object>"

def capture_locals_on_crash(exc_type, exc_value, exc_traceback):
    print("Custom exception hook triggered")
    frames_locals = []
    tb = exc_traceback
    while tb is not None:
        frame = tb.tb_frame
        frame_info = {
            'file': frame.f_code.co_filename,
            'line': tb.tb_lineno,
            'function': frame.f_code.co_name,
            'locals': {key: safe_pickle(value) for key, value in frame.f_locals.items()}
        }
        frames_locals.append(frame_info)
        tb = tb.tb_next

    filename = "crash_locals_.pkl"
    filepath = os.path.abspath(filename)

    try:
        with open(filepath, "wb") as f:
            pickle.dump(frames_locals, f)
        print(f"Local variables from each scope saved to {filepath}")
    except Exception as e:
        print(f"Failed to save local variables: {e}")

# Trigger a test exception after setting the hook
def buggy_function():
    a = "This is a test"
    b = [1, 2, 3]
    print(1 / 0)  # This will raise a ZeroDivisionError

def load_locals(file_path="crash_locals_.pkl"):
    """
    Loads and deserializes local variables from a pickle file saved during an exception.
    
    Parameters:
        file_path (str): Path to the pickle file with captured locals (default is "crash_locals_.pkl").
        
    Returns:
        dict: Dictionary containing deserialized local variables by frame.
    """
    # Load the pickle file
    with open(file_path, "rb") as f:
        frames_locals = pickle.load(f)

    # Check if there's an active exception and print it if available
    error_info = sys.exc_info()
    if error_info[0] is not None:
        error_type, error_value, error_traceback = error_info
        print("Error Information:")
        print(f"Type: {error_type.__name__}")
        print(f"Value: {error_value}")
        print("Traceback:")
        traceback.print_tb(error_traceback)
        print("\n" + "="*50 + "\n")
    else:
        print("No active exception information available.\n" + "="*50 + "\n")

    # Dictionary to store deserialized variables by frame
    deserialized_frames = {}

    # Decode and store the captured locals in a structured dictionary
    for i, frame_info in enumerate(frames_locals):
        frame_dict = {}
        print(f"File: {frame_info['file']}")
        print(f"Line: {frame_info['line']}")
        print(f"Function: {frame_info['function']}")
        print("Locals:")
        
        for var_name, var_value in frame_info['locals'].items():
            try:
                # Deserialize the value to its original form if it's in binary
                deserialized_value = pickle.loads(var_value) if isinstance(var_value, bytes) else var_value
                frame_dict[var_name] = deserialized_value  # Store in frame_dict
                print(f"  {var_name} (type: {type(deserialized_value)}): {deserialized_value}")
            except Exception as e:
                frame_dict[var_name] = f"<Unpickleable or Error: {e}>"
                print(f"  {var_name}: <Unpickleable or Error: {e}>")
        
        # Add the frame's deserialized locals to the main dictionary
        deserialized_frames[f"frame_{i}"] = {
            "file": frame_info["file"],
            "line": frame_info["line"],
            "function": frame_info["function"],
            "locals": frame_dict
        }
        print("\n" + "-"*50 + "\n")

    return deserialized_frames


# with CaptureExceptionsInJupyter():
#     buggy_function()

# r = load_locals()