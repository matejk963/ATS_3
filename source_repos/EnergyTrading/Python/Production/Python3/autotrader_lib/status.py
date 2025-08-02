# coding: utf-8


class Status(object):
    STARTING_MANAGER = dict(code=1, text="Initializing connection.")
    ONLINE = dict(code=2, text="Connection established.")
    CONNECTION_TEARDOWN = dict(code=3, text="Tearing down connection.")
    NO_CONNECTION = dict(code=4, text="Disconnected.")
    HALT = dict(code=5, text="The manager has been shut down.")
