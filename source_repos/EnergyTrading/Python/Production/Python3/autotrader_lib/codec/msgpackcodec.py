# -*- coding: utf-8 -*-
from __future__ import print_function
import datetime
import time

try:
    import msgpack
except ImportError:
    print("msgpack is not installed")
    msgpack = None

from .. import SerializationError


def _encoder(obj):
    # TODO(keb) handle timezone-aware datetimes
    if isinstance(obj, datetime.datetime):
        return {'__datetime__': True, 'as_str': obj.strftime('%Y%m%dT%H:%M:%S.%fZ')}
    elif isinstance(obj, time.struct_time):
        return {'__timestruct__': True, 'as_str': time.strftime('%Y%m%dT%H:%M:%SZ', obj)}
    return obj


def _decoder(obj):
    if '__datetime__' in obj:
        dt_str = obj['as_str'].strip('Z')
        try:
            obj = datetime.datetime(int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8]),
                                    int(dt_str[9:11]), int(dt_str[12:14]), int(dt_str[15:17]), int(dt_str[18:]))
        except ValueError:
            obj = datetime.datetime.strptime(obj['as_str'], '%Y%m%dT%H:%M:%S.%fZ')
    elif '__timestruct__' in obj:
        dt_str = obj['as_str'].strip('Z')
        try:
            obj = datetime.datetime(int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8]),
                                    int(dt_str[9:11]), int(dt_str[12:14]), int(dt_str[15:]))
        except ValueError:
            obj = datetime.datetime.strptime(obj['as_str'], '%Y%m%dT%H:%M:%SZ')
    return obj


def serialize(obj):
    return msgpack.packb(obj, default=_encoder, use_bin_type=False)


def deserialize(serialized):
    try:
        return msgpack.unpackb(serialized, object_hook=_decoder)
    except ValueError as err:
        raise SerializationError(err)
