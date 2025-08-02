import time
from contextlib import contextmanager
import argparse
import inspect

def load_arguments(arg_dict):
    """Load command-line arguments, ignoring unrecognized ones in Jupyter."""
    parser = argparse.ArgumentParser(description="Load command-line arguments.")

    # Add arguments dynamically
    for arg_name, properties in arg_dict.items():
        parser.add_argument(
            arg_name,
            type=properties.get('type', str),
            default=properties.get('default'),
            required=False,  # Force required=False for Jupyter compatibility
            help=properties.get('help', '')
        )

    # Use parse_known_args() to ignore unrecognized arguments (e.g., Jupyter's -f)
    args, _ = parser.parse_known_args()
    
    return tuple(getattr(args, arg_name.lstrip('-').replace('-', '_')) for arg_name in arg_dict)

@contextmanager
def execution_time(task_name=""):
    start_time = time.perf_counter()
    try:
        yield
    finally:
        end_time = time.perf_counter()
        print(f"{task_name} - Execution time: {end_time - start_time:.4f} seconds", flush=True)

@contextmanager
def print_args(method):
    def wrapper(self, *args, **kwargs):
        print(f"Calling {method.__name__} with args: {args} and kwargs: {kwargs}")
        return method(self, *args, **kwargs)

    original_method = method
    cls = None  # Class to which the method belongs

    # Find the class to which the method belongs
    for name, obj in inspect.getmembers(inspect.getmodule(method)):
        if inspect.isclass(obj) and any(method is attr for attr_name, attr in inspect.getmembers(obj)):
            cls = obj
            break

    try:
        # Patch the method
        setattr(cls, method.__name__, wrapper)
        yield
    finally:
        # Restore the original method
        setattr(cls, method.__name__, original_method)