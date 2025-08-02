import os
from functools import wraps

# Try to import Prefect modules
try:
    from prefect import task as prefect_task, flow as prefect_flow
    prefect_installed = True
except ImportError:
    prefect_installed = False

class PhantomLogger():
    def info(self, str):
        pass
    def debug(self, str):
        pass
    def error(self, str):
        pass
    def infor(self, str):
        pass

if prefect_installed:
    task = prefect_task
    flow = prefect_flow
else:
    def task(*args, **kwargs):
        def decorator(func):
            @wraps(func)
            def wrapper(*f_args, **f_kwargs):
                return func(*f_args, **f_kwargs)
            return wrapper
        return decorator

    def flow(*args, **kwargs):
        def decorator(func):
            @wraps(func)
            def wrapper(*f_args, **f_kwargs):
                return func(*f_args, **f_kwargs)
            return wrapper
        return decorator
