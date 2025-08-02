#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Defines classes for bookkeeping Trayport resords. This includes instruments, sequences, sequence items etc.

Record class represents a wrapper around a dict object received from the connection manager.

RecordCollection represents an extension of the Record class able to store a list of sub-records as a
collection with dict-like access on the object.
"""

from __future__ import absolute_import
import datetime
import logging

import autotrader_lib.common as COMMON
import autotrader_core.persistence as PERSIST
import autotrader_core.trayport_items as TRITEMS
import autotrader_core.utils as UTILS


log = logging.getLogger("trayport_records")


class Record(object):
    """Base class for bookkeeping trayport records with dynamic attributes"""
    _counter = 0

    def __init__(self, store=False, obj_id=None, object_type=None, **record):
        """

        :param bool store: specifies if the object should be stored in the DB
        :param [int, str] obj_id: object id, if is it None, the class counter will be used
        :param str object_type: object type, specifying the record
        :param record: key-values to be converted to attribute-values of the object
        """
        if object_type is None:
            object_type = self.__class__.__name__
        record["object_type"] = object_type
        if obj_id is None:
            obj_id = Record._counter
            Record._counter += 1
        record["obj_id"] = obj_id
        self.__dict__.update(**record)
        if store:
            self.update_db()

    def to_dict(self):
        store_dict = self.__dict__.copy()
        for record_type, records in list(store_dict.items()):
            if isinstance(records, Record):
                store_dict[record_type] = records.to_dict()
            elif isinstance(records, list):
                store_dict[record_type] = [el.__dict__ if isinstance(el, Record) else el for el in records]
            elif isinstance(records, dict):
                store_dict[record_type] = {key: el.to_dict() if isinstance(el, Record) else el
                                           for key, el in records.items()}
            elif isinstance(records, TRITEMS.BaseItem):
                store_dict.pop(record_type)
            elif record_type in ["delivery_start", "delivery_end", "trading_start", "trading_end"]:
                store_dict[record_type] = datetime.datetime.utcfromtimestamp(records)
        return store_dict

    def update_db(self):
        """Updates instance in the mongo"""
        PERSIST.MongoDBConnector().update_db_record(self.to_dict())


class RecordCollection(Record):
    """Extension of the Record class to take into account sub-records as a collection of dict type providing
    a dict-like access to the collection elements on the object"""

    def __init__(self, collection=None, store=False, obj_id=None, object_type=None, **record):
        """

        :param dict collection: collection of sub-records to be stored on the object with a dict-like access
        :param bool store:
        :param str obj_id:
        :param str object_type:
        :param dict record: dictionary with key-values to be converted to attribute-values of the object
        """
        self.collection = {} if collection is None else collection
        super(RecordCollection, self).__init__(store=store, obj_id=obj_id, object_type=object_type, **record)

    def __contains__(self, key):
        return key in self.collection

    def __len__(self):
        return len(self.collection)

    def __getitem__(self, key):
        return self.collection[key]

    def __setitem__(self, key, value):
        self.collection[key] = value

    def __iter__(self):
        return iter(self.collection)

    def items(self):
        return list(self.collection.items())

    def keys(self):
        return list(self.collection.keys())

    def values(self):
        return list(self.collection.values())


class SequenceItemRecord(Record):
    """Class holding trayport sequence item record"""
    SEQ_ITEM_CLS = {COMMON.GasPromptItemId.within_day: "WithinDayItem",
                    COMMON.GasPromptItemId.day_ahead: "DayAheadItem",
                    COMMON.GasPromptItemId.bow: "BalanceOfWeekItem",
                    COMMON.GasPromptItemId.weekend: "WeekEndItem",
                    COMMON.GasPromptItemId.saturday: "SaturdayItem",
                    COMMON.GasPromptItemId.sunday: "SundayItem",
                    COMMON.GasPromptItemId.monday: "MondayItem",
                    COMMON.GasPromptItemId.tuesday: "TuesdayItem",
                    COMMON.GasPromptItemId.wednesday: "WednesdayItem",
                    COMMON.GasPromptItemId.thursday: "ThursdayItem",
                    COMMON.GasPromptItemId.friday: "FridayItem",
                    COMMON.GasPromptItemId.bom: "BalanceOfMonthItem"}

    _DEFAULT_CLS = "BaseItem"
    BOM_SEQ_ID = "10000301"
    GAS_PROMPT_SEQ_ID = "10000302"

    def __init__(self, seq_id=None, item_id=None, **record):
        """

        :param str seq_id: sequence id
        :param str item_id: item id
        :param dict record: dictionary with key-values to be converted to attribute-values of the object
        """
        self.seq_id = seq_id
        self.item_id = item_id
        super(SequenceItemRecord, self).__init__(object_type="SequenceItem", **record)
        if self.seq_id == self.GAS_PROMPT_SEQ_ID and self.item_id in self.SEQ_ITEM_CLS:
            self.item_cls = self.SEQ_ITEM_CLS[self.item_id]
        elif self.seq_id == self.BOM_SEQ_ID:
            self.item_cls = self.SEQ_ITEM_CLS["35"]
        else:
            self.item_cls = self._DEFAULT_CLS
        self.item_interval = getattr(TRITEMS, self.item_cls)(self)


class Area(Record):
    """Class holding area record

    An area corresponds to a Trayport instrument acquired from instrument definition
    """

    def __init__(self, inst_id=None, inst_name=None, sequences=None, venue=None, broker_ids=None, **record):
        self.inst_id = inst_id
        self.inst_name = inst_name
        self.sequences = TrayportSequences(sequences)
        self.venue = None if not venue else venue[0]["name"]
        self.brokers = AreaBrokers(brokers=broker_ids)
        super(Area, self).__init__(store=True, obj_id=inst_id, **record)

    @staticmethod
    def _convert_to_records(record_cls, record_list):
        """

        :param str record_cls: name of the record class to which to convert the records provided in record_list
        :param list record_list: list of dictionaries to be converted to the corresponding Record
        :return: list of converted records objects
        """
        record_cls = globals().get(record_cls, Record)
        if record_list is None:
            return None
        return [record_cls(**record) for record in record_list]

    def __eq__(self, other):
        return self.inst_id == other.inst_id


class AreaBrokers(RecordCollection):
    """Collection of term_format_ids corresponding to a certain broker_id for a specific area"""

    def __init__(self, brokers):
        super(AreaBrokers, self).__init__()
        if brokers:
            self.collection = {broker_record["broker_id"]: broker_record["term_format_id"] for broker_record in brokers}

    def __setitem__(self, broker_id, term_format_id):
        super(AreaBrokers, self).__setitem__(broker_id, term_format_id)


class TrayportAreas(RecordCollection):
    """Class does bookkeeping of Trayport instruments by converting them to Areas and storing the collection with
    keys corresponding to the Trayport instrument ids"""

    MANDATORY_INSTR_FILTERS = {"inst_type": ("Sequential Instrument",)}
    EXCLUDE_INSTR_FILTERS = {"inst_name": ("UNUSED",)}

    commodities = UTILS.ListVariable("commodities")
    venues = UTILS.ListVariable("venues")

    def __init__(self, commodities=None, venues=None):
        self.commodities = commodities
        self.venues = venues
        super(TrayportAreas, self).__init__()

    def _venue_filter(self, instrument):
        """
        Checks if instrument belongs to the given list of venues

        :param instrument: The instrument definition, as received from the connection manager
        :type instrument: dict
        :returns: False if the instrument should not be filtered out, and a string with the filter reason otherwise.
        """
        if self.venues:
            venue = instrument.get("venue", [])
            if not venue:
                return "no venue metadata provided"
            if venue[0].get("name") not in self.venues:
                return "venue metadata: {} is not in the configured venues: {}".format(venue[0].get("name"),
                                                                                       self.venues)
        return False

    def _inst_filter(self, instrument):
        """
        Checks if the instrument matches the filter criteria set in the class

        :param instrument: The instrument definition, as received from the connection manager
        :type instrument: dict
        :returns: False if the instrument should not be filtered out, and a string with the filter reason otherwise.
        """
        reasons = []
        for filter_name, filter_set in self.EXCLUDE_INSTR_FILTERS.items():
            if instrument.get(filter_name) in filter_set:
                reasons.append("instrument's field: {} is: {},"
                               " which is blacklisted (hardcoded)".format(filter_name,
                                                                          instrument.get(filter_name)))
        for filter_name, filter_set in self.MANDATORY_INSTR_FILTERS.items():
            if instrument.get(filter_name) not in filter_set:
                reasons.append("instrument's field: {} is: {}, but our hardcoded filter"
                               " requires it to be in: {}".format(filter_name, instrument.get(filter_name),
                                                                  filter_set))
        if reasons:
            return "; ".join(reasons)
        else:
            return False

    def _commodity_filter(self, instrument):
        """
        Filter out instruments without sequences that match the commodities of the object

        :param instrument: The instrument definition, as received from the connection manager
        :type instrument: dict
        :returns: False if the instrument should not be filtered out, and a string with the filter reason otherwise.
        """
        sequences = instrument.get("sequences", [])
        matching_sequences = []
        for sequence in sequences:
            matches = [sequence.get("seq_name", "").startswith(commodity) for commodity in self.commodities]
            if any(matches):
                matching_sequences.append(sequence)

        if not matching_sequences:
            return "None of the instrument's sequences ({}) starts with one of the configured" \
                   " commodities: {}".format([sequence.get("seq_name", "") for sequence in sequences],
                                             self.commodities)

        instrument["sequences"] = matching_sequences
        return False

    def _btfassociation_filter(self, instrument):
        """
        Filter out instruments with no broker_ids (btfassociations in the XML)

        :param instrument: The instrument definition, as received from the connection manager
        :type instrument: dict
        :returns: False if the instrument should not be filtered out, and a string with the filter reason otherwise.
        """
        if instrument["broker_ids"]:
            return False
        return "The instrument has no btfassociations (broker ids)"

    def __setitem__(self, instrument_id, instrument):
        should_filter = [self._btfassociation_filter(instrument),
                         self._venue_filter(instrument),
                         self._inst_filter(instrument),
                         self._commodity_filter(instrument)]

        if any(should_filter):
            log.debug("Filtering out area with instrument_id: %s, because of the following reasons: %s", instrument_id,
                      "; ".join(reason for reason in should_filter if reason))
            return None

        area = Area(**instrument)
        self.collection[instrument_id] = area


class Sequence(RecordCollection):
    """Class holding trayport sequence record"""

    def __init__(self, seq_id=None, seq_items=None, **record):
        self.seq_id = seq_id
        super(Sequence, self).__init__(collection=seq_items, store=True, obj_id=seq_id, **record)

    def __setitem__(self, item_id, sequence_item):
        """Adds a sequence item to the object collection with the corresponding item_id as key

        :param str item_id: item id
        :param sequence_item: dict or :class:`SequenceItemRecord`
        """
        if isinstance(sequence_item, dict):
            if getattr(self, "seq_name", "").startswith("Gas"):
                sequence_item["gas"] = True
            else:
                sequence_item["gas"] = False
            sequence_item = SequenceItemRecord(**sequence_item)
        if self.seq_id == sequence_item.GAS_PROMPT_SEQ_ID and item_id not in sequence_item.SEQ_ITEM_CLS:
            return None
        self.collection[item_id] = sequence_item


class TrayportSequences(RecordCollection):
    """Collection of Trayport sequences"""

    def __init__(self, sequences=None):
        """

        :param list sequences: if list of sequences is provided, it will be converted to a dict and stored in
                               collection with seq_ids specifying the keys
        """
        super(TrayportSequences, self).__init__()
        if sequences:
            for sequence in sequences:
                seq_id = sequence["seq_id"]
                self[seq_id] = sequence

    def __setitem__(self, seq_id, sequence):
        """Adds a sequence to the collection with the corresponding seq_id as key

        :param str seq_id: sequence id
        :param sequence: dict or :class:`Sequence`
        """
        if isinstance(sequence, dict):
            sequence = Sequence(**sequence)
        self.collection[seq_id] = sequence


class TermDefinition(Record):
    """Defines all definitions that belong to the specific term"""

    def __init__(self, control=None, default_value=None, phase=None,
                 min_decimal_places=None, max_decimal_places=None, flags=None):
        """
        Initialize TermDefinition object

        :param control: The type and the choices of the control
        :type control: dict
        :param default_value: Default value for the term
        :type default_value: str
        :param flags: Flags of the term
        :type flags: dict
        """
        kwdefinitions = {}
        if control:
            choice_list = []
            for choice_wrap in control.get("choices", []):
                for choice in choice_wrap["choice"]:
                    choice_list.append(choice["value"])
            kwdefinitions.update({
                "control_type": control.get("control_type"),
                "choices": choice_list
            })
        if default_value is not None:
            kwdefinitions.update({"default_value": default_value})
        if flags:
            kwdefinitions.update({"flags": flags})
        super(TermDefinition, self).__init__(object_type="TermDefinition", phase=phase,
                                             min_decimal_places=min_decimal_places,
                                             max_decimal_places=max_decimal_places,
                                             **kwdefinitions)

    def format_value(self, value):
        """
        Get the term's default value, formatted to the required decimal places (if applicable)

        :param value: The term value to be formatted
        :type value: str
        :return: The term's default value
        :rtype: str
        """
        if self.min_decimal_places is not None:
            whole_part, _, fract_part = value.partition(".")
            value = whole_part + "." + fract_part.ljust(self.min_decimal_places, "0")
        if self.max_decimal_places is not None:
            whole_part, _, fract_part = value.partition(".")
            if self.max_decimal_places == 0:
                value = whole_part
            else:
                if len(fract_part) > self.max_decimal_places:
                    value = whole_part + "." + fract_part[:self.max_decimal_places]
        return value


class TermDefinitions(RecordCollection):
    """Collection of term choices for a specific TermDefinitions defined by term_format_id"""

    def __init__(self, term_format_id=None):
        super(TermDefinitions, self).__init__(obj_id=term_format_id, object_type="TermDefinitions")

    def __setitem__(self, label, term):
        """
        Example format of term:

        [{"label": "Label_of_term",
          "default_value": "",
          "control": [
              {"choices": [
                  {"choice": [
                      {"name": "Default_value", "value": ""},
                      {"name": "Some_value", "value": "Some"}]}],
              "control_type": "ComboboxString"}],
          "flags": [
              {"read_only": True}]}]
        """

        control = term.get("control", [])
        first_control = control[0] if len(control) > 0 else None   # currently we store only the first control
        default_value = term.get("default_value", "")
        flags_list = term.get("flags", [])
        flags = flags_list[0] if len(flags_list) > 0 else None   # flags_list is a list, but contains 0 or 1 dictionary
        term_def = TermDefinition(first_control, default_value, term.get("phase"), term.get("min_decimal_places"),
                                  term.get("max_decimal_places"), flags)
        self.collection[label] = term_def


class TrayportTermFormats(RecordCollection):
    """Collection of Trayport terms"""

    def __setitem__(self, term_format_id, terms_collection):
        """Adds a term to the collection with the corresponding term_format_id as key

        :param str term_format_id: term format id
        :param terms_collection: list with elements of dict or class:`TermDefinitions` type
        """
        terms = TermDefinitions(term_format_id)
        for term in terms_collection:
            terms[term["label"]] = term

        self.collection[term_format_id] = terms


class TrayportProperties(RecordCollection):
    """Collection of Trayport instrument properties"""

    def __setitem__(self, property_id, property):
        """Adds a term to the collection with the corresponding term_format_id as key

        :param str property_id: str with (broker_id, instrument_id, first_sequence_id, first_item_id)
                                in the form like "20_10002148_10000302_1"
        :param dict property: dict with instrument properties as received from Trayport
        """
        self.collection[property_id] = Record(object_type="Property", **property["properties"][0])

    def add_property(self, property):
        """Adds property to a correct key extracted from the dict with instrument properties as received from
        Trayport

        :param dict property: dict with instrument properties as received from Trayport
        """
        key = "{}_{}_{}_{}".format(property["broker_id"][0]["value"],
                                   property["inst_specifier"][0]["instrument_id"],
                                   property["inst_specifier"][0]["first_sequence_id"],
                                   property["inst_specifier"][0]["first_item_id"])
        self.__setitem__(key, property)
