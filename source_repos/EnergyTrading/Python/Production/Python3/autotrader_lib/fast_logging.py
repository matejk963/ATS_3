import sys
import six

if six.PY2:
    import autotrader_lib.fast_logging_py2  # noqa
    sys.modules[__name__] = sys.modules['autotrader_lib.fast_logging_py2']

else:
    import autotrader_lib.fast_logging_py3  # noqa
    sys.modules[__name__] = sys.modules['autotrader_lib.fast_logging_py3']
