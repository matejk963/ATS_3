
from functools import wraps
from .test_global_vars import global_state

def set_testing_mode(mode):
    global_state.TESTING_MODE = mode

def log_behavior(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if global_state.TESTING_MODE:
            global_state.CALL_ORDER += 1
            global_state.LOG_LIST.append({
                'func': f"[{func.__module__.split('.')[-1]}] -> {func.__name__}",
                'call_order': global_state.CALL_ORDER,
                'args': args,
                'kwargs': kwargs
            })
            return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrapper