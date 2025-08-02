# input_data/__init__.py

import pkgutil
import importlib
import inspect

# Dynamically import all modules and their classes
for module_info in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f'.{module_info.name}', package=__name__)
    
    # Get all classes in the module and add them to the input_data package namespace
    for name, obj in inspect.getmembers(module, inspect.isclass):
        globals()[name] = obj

# Optionally, define __all__ for better control
__all__ = [name for name, obj in globals().items() if inspect.isclass(obj)]