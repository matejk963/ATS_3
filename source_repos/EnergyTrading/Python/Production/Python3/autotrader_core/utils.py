#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import errno
import bisect
import collections
import copy
import datetime
import heapq
import logging

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU
import autotrader_core.cet_day_boundaries as cet_day_boundaries
from six.moves import filter

log = logging.getLogger("autotrader.utils")


def relay_func(*args, **kwargs):
    """Simple relay function for use in some mocking applications"""
    return args, kwargs


def make_element_params(mandatory, optional):
    missing_mandatory = [key for key, value in mandatory.items() if value is None]
    if missing_mandatory:
        raise COMMON.MissingParameters(",".join(missing_mandatory))
    optional = dict((key, value) for key, value in optional.items() if value is not None)
    mandatory.update(optional)
    return mandatory


cet_date2boundaries = dict(
    (datetime.date(s[0], s[1], s[2]), (s[3], s[4])) for s in cet_day_boundaries.CET_DAY_STRUCTURE
)
cet_bisect_boundaries_list = [s[3] for s in cet_day_boundaries.CET_DAY_STRUCTURE]
cet_bisect_boundaries_dates = [
    (datetime.date(s[0], s[1], s[2]), s[3], s[4]) for s in cet_day_boundaries.CET_DAY_STRUCTURE
]


def boundaries_for_cet_day(date_object):
    return cet_date2boundaries[date_object]


def cet_date_of_timestamp(ts):
    idx = bisect.bisect_right(cet_bisect_boundaries_list, ts) - 1
    assert idx > 0, "idx: {}, ts: {}".format(idx, ts)
    assert idx < len(cet_bisect_boundaries_list), "len(cet_bisect_boundaries_list): {}".format(
        len(cet_bisect_boundaries_list)
    )
    return cet_bisect_boundaries_dates[idx]  # return date, utc_from, utc_until


def unify_xbid_and_local_product_type(products_by_span):
    """
    Maps XBID product type string into the proper local product's key of products_by_span.
    XBID product is always appended after the local product.

    "products_by_span" parameter format:
    {...
        (ts_start_N, ts_end_N, product_type_N): Product_N,
    ...}
    """

    product_type_map = {
        COMMON.ProductType.ID.XBID_Quarter_Hour_Power: [
            COMMON.ProductType.ID.Intraday_Quarter_Hour_Power,
            COMMON.ProductType.ID.NX_Intraday_Power_D_QH
        ],
        COMMON.ProductType.ID.XBID_Half_Hour_Power: [
            COMMON.ProductType.ID.Half_Hour_Power,
            COMMON.ProductType.ID.NX_Intraday_Power_D_HH
        ],
        COMMON.ProductType.ID.XBID_Hour_Power: [
            COMMON.ProductType.ID.Intraday_Hour_Power,
            COMMON.ProductType.ID.NX_Intraday_Power_D
        ]
    }

    unified_products_by_span = collections.defaultdict(list)

    for (from_dt, to_dt, product_type), product in products_by_span.items():
        key = (from_dt, to_dt, product_type)
        mapped_prod_types = product_type_map.get(product_type, [])

        for mapped_p_t in mapped_prod_types:
            mapped_key = (from_dt, to_dt, mapped_p_t)
            # if there is a mapping for the prod_type and the mapped type also exists, unify the products
            if mapped_key in products_by_span:
                unified_products_by_span[mapped_key].append(products_by_span[key])
                # if in the products_by_span key list there would be more of the mapped prod_types, we map to the first
                break
        else:
            # if there is no mapping for the prod_type, it's supposed to be local product -> put at the beginning
            if not mapped_prod_types:
                unified_products_by_span[key].insert(0, product)
            # otherwise there is a mapping, but the mapped product type doesn't exist, so the product can be thrown

    return unified_products_by_span


def recursivedict():
    return collections.defaultdict(recursivedict)


def add_elem_to_set_and_confirm(elem, given_set):
    """
    adds an element to a set and returns True if it was added or False if it is already in the set

    :param elem: element which will be added to the set
    :type elem: any
    :param given_set: set of elements
    :type given_set: set
    :return: True if added, else False if its already in the set
    :rtype: bool
    """
    old_length = len(given_set)
    given_set.add(elem)
    return len(given_set) != old_length


class memorize(dict):
    """
    This function decorator turns a function into a dictionary
    holding the relevant cache information depending on the
    type of the return of the original function.
    """

    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        result = self.func(*args, **kwargs)
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, list):
                    self[key].extend(value)
                else:
                    self[key].append(value)
        elif isinstance(result, list):
            self["res"].extend(result)
        else:
            if result not in self["res"]:
                self["res"].append(result)
        return result

    def __missing__(self, key):
        self[key] = list()
        return self[key]

    def __nonzero__(self):
        """
        Consider this dictionary to be empty, if all value lists are empty.
        :return: True if any key holds a non-empty list.
        """
        for key, value in self.items():
            if value:
                return True
        return False

    def cache(self):
        return self

    def clear_cache(self):
        self.clear()


class PriorityQueue(object):

    def __init__(self):
        self.items = []

    def pop(self):
        return heapq.heappop(self.items)

    def pop_all(self):
        list_all = self.items
        self.items = []
        return list_all

    def push(self, item):
        return heapq.heappush(self.items, item)

    def poppush(self, item):
        """Removes the item from the self.items list, to
        heappush the item afterwards.

        This function is needed if an item was appended or inserted to the
        self.items list or a property of the object responsible for the
        objects comparison has changed. In these cases self.items is no
        longer a valid heap-queue and should be redefined (or heapified).
        """
        if item in self.items:
            self.items.remove(item)
        heapq.heapify(self.items)
        return self.push(item)

    def size(self):
        return len(self.items)


class InstanceLock(object):
    """Holds the instance lock

    The class holds the information about possible instance locking object.
    It is used, for example, as an order and trade lock for Product class.
    """

    LockingObject = collections.namedtuple("LockingObject", "object_id state timestamp instance quantity")
    lock_name = ""

    def __init__(self, timeout=None, instance_name="instance"):
        """Holds an instance lock

        The objects locking the instance are hold in the `self.locking_objects` list.
        The objects are added to the list as instances of `self.LockingObject`,
        containing information about locking object id, its state and alteration time stamp
        of the object in the InstanceLock.

        :param float timeout: timeout in sec, which specifies the time till
                                       automatic lock release. If timeout is None,
                                       the lock will never be released
        :param str instance_name: Name of the instance to lock
        """
        self.timeout = timeout
        self.instance_name = instance_name
        self.locking_objects = []

    def add(self, object_id, timestamp, instance=None, quantity=None):
        """Adds the object to the locking_objects

        The object is appended to the `self.locking_objects` with "ADD" state

        :param object_id: id of the locking object
        :type object_id: int
        :param timestamp: timestamp when the object is added to the InstanceLock
        :type timestamp: float
        :param instance: object which should be added to the lock, defaults to None
        :type instance: type
        :param quantity: the quantity of the trade/order execution to add to the lock state (only for EEX)
        :type quantity: float
        """
        self.locking_objects.append(
            self.LockingObject(object_id, COMMON.InstanceLockState.added, timestamp, instance, quantity))

    def modify(self, object_id, state, timestamp, instance=None, quantity=None):
        """Modifies the object in the locking_objects

        The object is modified in the `self.locking_objects` if it exists, or is added to the
        `self.locking_objects` with the specified state. If the state is "CONF_ALL" all objects
        with the object_id are released from the self.locking_objects. If the state is "CONF_ONE"
        only one object is released from the self.locking_objects on each modify.

        :param object_id: id of the locking object
        :type object_id: int
        :param state: state of the locking object
        :type state: str
        :param timestamp: timestamp when the object is added to the InstanceLock
        :type timestamp: float
        :param instance: object which should be added to the lock, defaults to None
        :type instance: type
        :param quantity: the quantity of the trade/order execution to add to the lock state (only for EEX)
        :type quantity: float
        :return: If at least one lock was removed, this returns the time
                 when the last now removed lock was originally added
        :rtype: float or None

        """

        if state == COMMON.InstanceLockState.confirm_one:
            self.release_one_for_object_id(object_id, timestamp, quantity=quantity)
        elif state == COMMON.InstanceLockState.confirm_all:
            return self.release_all_for_object_id(object_id)
        else:
            self.locking_objects.append(self.LockingObject(object_id, state, timestamp, instance, quantity))

    def release(self, locking_object):
        """Releases the specified locking_object from the InstanceLock

        :param locking_object: the locking_object to be release from the lock
        :type locking_object: LockingObject
        """
        self.locking_objects.remove(locking_object)

    def release_all_for_object_id(self, object_id):
        """Releases locking object based on the specified object id

        :param object_id: object id
        :type object_id: int
        :return: If at least one lock was removed, this returns the time
                 when the last now removed lock was originally added
        :rtype: float or None
        """
        timestamp = None
        for locking_object in self.iter_by_object_id(object_id):
            self.release(locking_object)
            timestamp = locking_object.timestamp
        return timestamp

    def release_one_for_object_id(self, object_id, timestamp, quantity=None):
        """Releases locking object based on the specified object id

        :param object_id: object id
        :type object_id: int
        :param timestamp: unused, only for inherited classes
        :type timestamp: float
        :param quantity: unused, only for inherited classes
        :type quantity: float
        :return: If a lock was removed, this returns the time when that lock was originally added
        :rtype: float or None
        """
        try:
            locking_object = next(obj for obj in self.locking_objects if obj.object_id == object_id)
            self.release(locking_object)
            return locking_object.timestamp
        except StopIteration:
            return

    def release_on_timeout(self, timestamp):
        """Releases locking objects due to timeout

        :param timestamp: current timestamp
        :type timestamp: float
        """

        def _release_with_log(locking_object, timeout):
            """Helper function to release an object with log entry"""
            log.warning("Freeing %s lock for order_id %s (in %s) after %s sec timeout",
                        self.lock_name, locking_object.object_id, self.instance_name, timeout)
            self.release(locking_object)

        objects_to_release = []

        # Release all objects with added_negative state after 10s timeout
        for locking_object in self.iter_by_state(COMMON.InstanceLockState.added_negative):
            if locking_object.timestamp <= timestamp - 10:
                _release_with_log(locking_object, 10)
                objects_to_release.append(locking_object)

        if self.timeout:
            for locking_object in self.iter_before_timestamp(timestamp - self.timeout):
                _release_with_log(locking_object, self.timeout)
                objects_to_release.append(locking_object)

        return objects_to_release

    def release_all(self):
        objects_to_release = self.locking_objects[:]
        self.locking_objects = []
        return objects_to_release

    def iter_by_object_id(self, object_id):
        return filter(lambda obj: obj.object_id == object_id, self.locking_objects[:])

    def iter_by_state(self, state):
        return filter(lambda obj: obj.state == state, self.locking_objects[:])

    def iter_before_timestamp(self, timestamp):
        return filter(lambda obj: obj.timestamp <= timestamp, self.locking_objects[:])

    def is_locked(self, timestamp):
        """Specifies is the instance is locked

        The function checks for objects in the `self.locking_objects`.
        If the list empty, the function returns `False`, as the instance is unlocked.
        Otherwise, it returns `True`.

        :param timestamp: current timestamp
        :type timestamp: float
        :returns: returns True, if the instance is locked
        :rtype: {bool}
        """
        if self.locking_objects:
            if self.contains_since_longer_time(None, timestamp, 15):
                log.warning("Found hanging %s lock for %s: %s", self.lock_name, self.instance_name,
                            self.locking_objects)
            else:
                log.debug("Found %s lock for %s: %s", self.lock_name, self.instance_name,
                          self.locking_objects)
            return True
        else:
            return False

    def __len__(self):
        return len(self.locking_objects)

    def __iter__(self):
        return iter(self.locking_objects)

    def __contains__(self, object_id):
        return any(locking_object.object_id == object_id for locking_object in self.locking_objects)

    def contains_since_longer_time(self, object_id, current_timestamp, cutoff=1):
        """
        Checks if the object_id is contained in this lock since more than a second.

        :param object_id: The object_id to check or None, if any object counts
        :type object_id: str or None
        :type current_timestamp: float
        :rtype: bool
        :param cutoff: Cutoff in seconds.
                       Only return True if the product is locked longer than this time (by the gien order_id, if any)
        :type cutoff: float or int

        """
        # We use 1 second as default cutoff because it is more than the typical roundtrip time
        # (autotrader -> exchange -> autoTRADER) except for high queue lag situations.
        return any((object_id is None or locking_object.object_id == object_id)
                   and current_timestamp - locking_object.timestamp > cutoff
                   for locking_object in self.locking_objects)


class ModificationLock(InstanceLock):
    lock_name = "modification"


class TagLock(InstanceLock):
    lock_name = "missing_tag"


class ExecutionLock(InstanceLock):
    lock_name = "execution"

    def add(self, object_id, timestamp, instance=None, quantity=None):
        """Adds the object to the locking_objects

        The object is appended to the `self.locking_objects` with "ADD" state

        :param object_id: id of the locking object
        :type object_id: int
        :param timestamp: timestamp when the object is added to the InstanceLock
        :type timestamp: float
        :param instance: object which should be added to the lock, defaults to None
        :type instance: type
        :param quantity: the quantity of the trade/order execution to add to the lock state (only for EEX)
        :type quantity: float
        """
        self.release_on_timeout(timestamp)
        try:
            locking_object = next(
                obj for obj in self.locking_objects
                if obj.object_id == object_id and obj.state == COMMON.InstanceLockState.added_negative
            )
            self.release(locking_object)
            return
        except StopIteration:
            self.locking_objects.append(
                self.LockingObject(object_id, COMMON.InstanceLockState.added, timestamp, instance, quantity))

    def release_one_for_object_id(self, object_id, timestamp, instance=None, quantity=None):
        """Releases locking object based on the specified object id

        :param object_id: object id
        :type object_id: int
        :param timestamp: timestamp when negative lock objects are added to the InstanceLock
        :type timestamp: float
        :param instance: object which should be added to the lock, defaults to None
        :type instance: type
        :param quantity: the ADDNEG quantity of the own trade to add to the lock state (only for EEX)
        :type quantity: float
        """
        self.release_on_timeout(timestamp)
        try:
            locking_object = next(
                obj for obj in self.locking_objects
                if obj.object_id == object_id and obj.state == COMMON.InstanceLockState.added
            )
            self.release(locking_object)
            return
        except StopIteration:
            # for negative locks in case of a trade, reduce the timeout to 10 seconds by shifting the timestamp
            # needed when initializing system. In that state, we receive trade messages that will not be
            # followed by executions
            self.locking_objects.append(
                self.LockingObject(object_id, COMMON.InstanceLockState.added_negative, timestamp, instance, quantity))

    def handle_multimatching_modify_lock(self, lock_id, quantity):
        """
        For EEX and ICE venues in order to release the trade_lock we have to match the quantity of FEXE/PEXE and traded
        quantity.
        This function checks if the quantity is defined for the lock ID and then deletes or subtracts the
        trade quantity from the stored quantity.
        :param lock_id: The internal ID with which we received the own_trade
        :type lock_id: str
        :param quantity: The trade quantity
        :type quantity: float
        :return: True if the ADD lock cannot be found with the given ID or the trade quantity is None, equal (or more)
        than the stored order execution quantity, False if less
        :rtype: bool
        """
        for lock in self.locking_objects:
            if lock.object_id == lock_id:
                # Always only look at the first lock for this id, even in case there are multiple
                if (lock.quantity and lock.state == COMMON.InstanceLockState.added
                        and ALU.round_float(lock.quantity - quantity, precision=3) > 0):
                    modified_lock = copy.deepcopy(lock)
                    self.locking_objects.remove(lock)
                    self.add(modified_lock.object_id, modified_lock.timestamp, instance=modified_lock.instance,
                             quantity=modified_lock.quantity - quantity)
                    return False
                else:
                    return True
        return True

    def handle_multimatching_add_lock(self, lock_id, quantity):
        """
        For EEX and ICE venues. If an own_trade is received before the execution message, and later the PEXE/FEXE is
         received, the "ADDNEG" trade lock is being removed. This function matches the quantity of the existing "ADDNEG"
         trade lock and calculates a new quantity along with a new state if the FEXE/PEXE quantity would be higher than
         the lock quantity

        For example: If and own trade is received with the quantity of 3, an "ADDNEG" trade lock is created. Later on a
        FEXE is received with the quantity of 10 --> The trade_lock should stay, but it should have the state "ADD" with
        quantity of 7, so we know that we should wait for more upcoming own_trades before the trade_lock can be released

        :param lock_id: The internal ID with which we received the own_trade
        :type lock_id: str
        :param quantity: The trade quantity
        :type quantity: float
        :return: True if the ADDNEG lock cannot be found with quantity and given ID, or the lock quantity is equal to
        the order quantity (received as parameter), otherwise returns false
        :rtype: bool
        """
        # Happens if the own_trade is received before the execution message. In this case if the lock's ADDNEG
        # quantity is less than the quantity received, then the state should be changed to ADD with new quantity
        for lock in self.locking_objects:
            if lock.object_id == lock_id and lock.quantity and lock.state == COMMON.InstanceLockState.added_negative:
                remaining_quantity = ALU.round_float(-lock.quantity + quantity, precision=3)
                if not remaining_quantity:  # If 0 quantity is left remove the lock
                    self.locking_objects.remove(lock)
                    return False
                modified_lock = copy.deepcopy(lock)
                self.locking_objects.remove(lock)
                state = (COMMON.InstanceLockState.added if remaining_quantity > 0
                         else COMMON.InstanceLockState.added_negative)
                self.locking_objects.append(
                    self.LockingObject(modified_lock.object_id, state, modified_lock.timestamp, modified_lock.instance,
                                       abs(remaining_quantity)))
                return False
        return True


class InternalMarketVault(InstanceLock):
    lock_name = "vault"

    def __init__(self):
        super(InternalMarketVault, self).__init__(timeout=10, instance_name="entry_order")

    def get_orders(self, product_id):
        return [locking_obj.instance for locking_obj in self if locking_obj.instance.product.product_id == product_id]

    def get_products(self):
        """
        Return a set of products for which we have orders in the vault
        :return: A set of products
        :rtype: set[autotrader_core.exchange_trading.Product]
        """
        return set([order_obj.instance.product for order_obj in self])

    def add_entry_orders(self, orders_to_check, current_timestamp):
        """

        :return the discarded orders
        :rtype: list
        """
        if COMMON.ResolverState.entry_orders in orders_to_check:
            for order in orders_to_check[COMMON.ResolverState.entry_orders]:
                if order.internal_id not in self:
                    self.add(order.internal_id, current_timestamp, order)

    def __str__(self):
        return " ".join(locking_obj.object_id for locking_obj in self)


class ListVariable(object):
    """Descriptor class to convert a variable to a list

    In the __set__ the class sets:
     - variable to [], if the user tries to set it to None;
     - variable to a list with one element, if the user tries to set it to a non list value;
     - variable to a user provided value, if the value is a list.
    """

    def __init__(self, name="var"):
        self.name = name
        self.value = []

    def __get__(self, instance, owner):
        return self.value

    def __set__(self, instance, val):
        if val is None:
            self.value = []
        elif not isinstance(val, list):
            self.value = [val]
        else:
            self.value = val


def internal_order_execution(action, orders, route=None):
    def _make_dict(order):
        return {"direction": order.direction,
                "product_id": order.product.product_id,
                "quantity": order.quantity,
                "order_id": getattr(order, "order_id", order.internal_id),
                "internal_id": order.internal_id,
                "broker_id": getattr(order, "broker_id", None),
                "price": order.price,
                "delivery_area_id": order.delivery_area_id,
                "action": action,
                "txt": ALU.serialize_order_tags(order.tags),
                "user": COMMON.INTERNAL_USER,
                "execution_restriction": order.execution_restriction,
                "validity_restriction": order.validity_restriction,
                "validity_date": None,
                "initial_order_id": None,
                "type": COMMON.OrderType.order,
                "state": COMMON.OrderState.acti,
                "last_update_user": COMMON.INTERNAL_USER,
                "revision": 9999,
                "route_id": route,
                }

    return [_make_dict(order) for order in orders]


def internal_order_reject(exchange_id, orders, reasons_dict, timestamp):
    return dict(exchange=exchange_id,
                message_type=COMMON.Response.internal_order_reject,
                data=[{"internal_id": order.internal_id,
                       "product_id": order.product.product_id,
                       "portfolio_key": order.portfolio_key,
                       "tags": order.tags,
                       "reason":
                           reasons_dict.get(order.internal_id)}
                      for order in orders],
                timestamp=timestamp)


def pid_exists(process_id):
    """Check whether pid exists, which tells if the process has exited gracefully.

    Function was extrapolated from psutil to avoid having to import the psutil package
    """
    if process_id < 0:
        return False
    if process_id == 0:
        raise ValueError("Process ID 0 always exists as a root process and should therefore not be checked")
    try:
        os.kill(process_id, 0)  # os.kill 0 basically pings the process
    except OSError as error:
        if error.errno == errno.ESRCH:
            return False
        elif error.errno == errno.EPERM:  # access denied which means the process exists
            return True
        else:
            raise
    else:
        return True


class Singleton(type):
    """
    This class is to be used as metaclass for any other class that you want to make a singleton class.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def _remove_instance(mcs, cls):
        """
        Forcefully break the singleton pattern by removing the instance saved for this class. This is to be used in
        tests when we need to force creation of new instance of some class.

        :param cls: A class for which to remove the instance
        """
        del mcs._instances[cls]

    @classmethod
    def _set_instance(mcs, cls, instance):
        """
        Manually set the instance to be returned for a certain class. This is to be used in tests when we need to mock
        a certain object.

        :param cls: Class for which to return the instance
        :param instance: Which instance to return for all new objects of specified class
        """
        mcs._instances[cls] = instance
