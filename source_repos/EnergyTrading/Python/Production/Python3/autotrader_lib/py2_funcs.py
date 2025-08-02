"""
Provide Python 2 functionality where Python 3 changes in a breaking way
"""

import numpy as np


def py2max(values):
    """

    :type values: list
    """
    try:
        return max(v for v in values if v is not None)
    except ValueError:
        if len(values) != 0:
            return None
        raise
    except TypeError:
        raise


def py2min(values):
    """Helper to imitate python2 behaviour of min, handling None values.

    Restrictons:
    Input argument has to be a list. Elements must be comparable or None.

    Examples which work in Python2 but are not covered by this helper function:

    >>> min([2, 1, None], "")        Result: [2, 1, None]
    >>> min([""], "")                Result: ['']
    >>> min([2, 1, None], "")        Result: [2, 1, None]
    >>> min([2, 1, None], 1000)      Result: 1000
    >>> min([2, 1, None], -1000)     Result:-1000
    >>> min([2, 1, None], 0)         Result:    0

    :type values: list
    """
    if None in values:
        return None
    return min(v or 0 for v in values)


def bigger_than(arg1, arg2):
    """
    Returns True if arg1 is strictly bigger than arg2
    Mimics behaviour of Python 2 when comparing number to None: any number is bigger than None

    :type arg1: float or None
    :type arg2: float or None
    """
    if arg1 is None:
        return False
    if arg2 is None:
        return True
    return arg1 > arg2


def less_than(arg1, arg2):
    """
    Returns True if arg1 is strictly less than arg2
    Mimics behaviour of Python 2 when comparing number to None: None is less than any number

    :type arg1: float or None
    :type arg2: float or None
    """
    return bigger_than(arg2, arg1)


def convert_dict_with_numpy_values(dictionary):
    """
    Converts numpy int32 and int64 values in dict to python int
    """
    for k, v in dictionary.items():
        if isinstance(v, dict):
            convert_dict_with_numpy_values(v)
        elif isinstance(v, list):
            for x, i in enumerate(v):
                if isinstance(i, (dict, list)):
                    convert_dict_with_numpy_values(i)
                else:
                    if type(i) in (np.int32, np.int64):
                        i = int(i)
                    v[x] = i
        else:
            if type(v) in (np.int32, np.int64):
                v = int(v)
            dictionary.update({k: v})
    return dictionary


def is_none(val):
    """
    Returns True if val is (None or numpy.nan)
    """
    return True if val is None or np.isnan(val) else False
