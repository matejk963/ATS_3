class GlobalState:
    def __init__(self):
        self.TESTING_MODE = False
        self.LOG_LIST = []
        self.CALL_ORDER = 0

global_state = GlobalState()