#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import print_function

from __future__ import absolute_import
import argparse
import datetime
import gzip
import json
import time

import mock
import os
import os.path
import pymongo
import shutil
import sqlite3
import sys

import autotrader_core.api
import autotrader_lib.common as COMMON
import autotrader_core.exchanges as APIEXCH
import autotrader_core.utils
import autotrader_lib.config_helper as ATCONF
import autotrader_lib.standard_message_adapter
import autotrader_lib.util as UTIL
from six.moves import range

EPEX_DT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

AREAS_DE = {"rwe": "10YDE-RWENET---I",
            "eon": "10YDE-EON------1",
            "ve": "10YDE-VE-------2",
            "enbw": "10YDE-ENBW-----N"}

AREAS = {
    "rte": "10YFR-RTE------C",
    "apg": "10YAT-APG------L",
    "ch": "10YCH-SWISSGRIDZ",
    "rwe": "10YDE-RWENET---I",
    "eon": "10YDE-EON------1",
    "ve": "10YDE-VE-------2",
    "enbw": "10YDE-ENBW-----N",
    "nl": "10YNL----------L",
    "be": "10YBE----------2",
    "uk": "10YGB----------A",
}

EPEX_EXCHANGE_NAME = "EPEX"
NORDPOOL_EXCHANGE_NAME = "NORD"
TRAYPORT_EXCHANGE_NAME = "TRAYPORT"

EXCHANGES = (EPEX_EXCHANGE_NAME, NORDPOOL_EXCHANGE_NAME, TRAYPORT_EXCHANGE_NAME)


TRAYPORT_INIT_FILES_MESSAGE_TYPES = {
    # message_type: query limit
    "inst_definitions": 1,
    "inst_properties": None,
    "sequence_items": 1,
    "term_format": 1,
}


class BaseBuildSimulation(object):
    """ Export the data from the trader according to arguments
        If split is specified, split the result in 24 files (hour) or 4 files (6hours) or by product
        If area is specified, only export the area specified (cf AREAS dict)
        Abstract class
    """

    def __init__(self, output, exchange=None, area=None, split=None, init_files_only=False):
        """

        :param output: output filepath
        :param exchange: one of the supported exchanges EPEX, TRAYPORT, NORDPOOL
        :param area: area to be filtered from the messages
        :param split: optional time split, to keep feed files small
        :param init_files_only: only build init files, and skip json file generation
        """
        self.exchange = exchange.upper() if exchange is not None else None

        assert (exchange is None) or (self.exchange in COMMON.Exchange.get_external()), \
            "Exchange must be None or one of {}".format(COMMON.Exchange.get_external())
        print("Exchange is set to {}".format(self.exchange))
        self.output = output
        self.split = split
        self.area = area

        self.nb_rows = 0
        self.trader = autotrader_core.api.AutoTrader()

        epex_config = ATCONF.EpexConfig(mock.Mock()).set_configs_from_dict(dict(autotrader_user="TRD01", password="vt"))
        nordpool_config = ATCONF.NordpoolConfig(mock.Mock()).set_configs_from_dict(dict(autotrader_user="TRD001",
                                                                                        password="vt"))
        trayport_config = ATCONF.TrayportConfig(mock.Mock()).get_defaults()

        self.trader.epex = APIEXCH.Epex(send_func=autotrader_core.utils.relay_func,
                                        create_dummy_products=True,
                                        allowed=True, exchange_config=epex_config)
        self.trader.nordpool = APIEXCH.NordPool(send_func=autotrader_core.utils.relay_func,
                                                create_dummy_products=True,
                                                allowed=True, exchange_config=nordpool_config)
        self.trader.trayport = APIEXCH.Trayport(send_func=autotrader_core.utils.relay_func,
                                                create_dummy_products=True,
                                                allowed=True, exchange_config=trayport_config)
        self._trader_exchange = {
            COMMON.Exchange.epex: self.trader.epex,
            COMMON.Exchange.nordpool: self.trader.nordpool,
            COMMON.Exchange.trayport: self.trader.trayport,
        }
        for exchange in self._trader_exchange.values():
            exchange.init_files_correlation_ids = {"initialized": True}

        # attributes use to filter by area
        self.area_filter = self.area
        self.set_area_filter()
        # object to check if some data is missing
        self.check_session = self.is_new_session()
        self.check_gap = self.is_gap()
        # overwritten in child classes
        self.date_format = "%Y-%m-%d %H:%M:%S.%f"
        self.session_utc_column_name = ""
        self.date_string = None
        self.init_files_only = init_files_only

    def set_area_filter(self):
        """ Set the area according to the area passed in parameter during __init__
        """
        if self.area and self.area in AREAS:
            if self.area in AREAS_DE:
                self.area_filter = list(AREAS_DE.values())
            else:
                self.area_filter = AREAS[self.area]
        print("Filtering area for", self.area_filter)

    @autotrader_lib.util.coroutine
    def is_new_session(self):
        """Coroutine asynchronously checking for a new session

        :yield: message if a new session has been found. The message is an empty string,
        if no new session has been detected
        """
        last_session_timestamp = None
        new_session_message = None
        while True:
            session_timestamp = yield new_session_message

            new_session_message = None

            if last_session_timestamp is None:
                last_session_timestamp = session_timestamp

            if last_session_timestamp is not None:
                if session_timestamp != last_session_timestamp:
                    new_session_message = "Reconnect found in file at {}".format(
                        autotrader_lib.util.convert_from_timestamp(session_timestamp, "%Y-%m-%d %H:%M:%S"))
                    last_session_timestamp = session_timestamp

    @staticmethod
    @autotrader_lib.util.coroutine
    def is_gap():
        """Coroutine asynchronously checking for a gaps in the data

        :yield: message if a gap has been found. The message is an empty string, if no gap has been detected
        """
        last_timestamp = None
        gap_message = None
        while True:
            timestamp = yield gap_message
            gap_message = None
            if last_timestamp is not None:
                if timestamp - last_timestamp > 60:
                    gap_message = "Gap of {} seconds found in file at {}".format(
                        timestamp - last_timestamp,
                        autotrader_lib.util.convert_from_timestamp(last_timestamp, "%Y-%m-%d %H:%M:%S"))

            last_timestamp = timestamp

    @staticmethod
    def print_progress(current, total, printed_points=0):
        """ helper to show progress of the current process
        """
        for i in range(printed_points, int(100 * float(current) / total)):
            if i % 10 == 0:
                sys.stdout.write(str(i) + "%")
            else:
                sys.stdout.write(".")
            printed_points = i + 1
            sys.stdout.flush()
        return printed_points

    def _get_output_filename(self, filename):
        """Generate a filename according to the spliting"""
        output_filename = "COMPLETE"
        if self.split == "product":
            product_id = self._trader_exchange[self.exchange].products.get_by_id(filename).name.lstrip("T")
            output_filename = "PRODUCT_{}_[{}]".format(product_id, filename)
        elif self.split is not None:
            date_str = datetime.datetime.fromtimestamp(filename).strftime("%Y-%m-%d %H")
            output_filename = "{}_{}_[{}]".format(self.split.upper(), date_str, filename)
        return "{}_{}.jsonl".format(self.date_string, output_filename).replace(":", "_")

    def get_translated_payload(self, row):
        """ Get the json_struct needed to update the trader and write files
            If old_format then we have to translate from xml to json the data
            If new_format then the translated_payload is already in the db

        :param row: the row in db to get the data from
        :type row: dict
        :return: the translated payload contained in data
        :rtype dict
        """
        raise NotImplementedError

    def get_number_of_rows(self):
        """ Get the number of rows in the database

        :return: the number of rows in the db
        :rtype int
        """
        raise NotImplementedError

    def select_all_rows(self):
        """ Query the database to get all the data from db

        :return: a list of all the data got from the db query
        :rtype list
        """
        raise NotImplementedError

    def update_trader(self, data, number_of_rows):
        log_messages = []
        points = 0

        for idx, row in enumerate(data):
            points = self.print_progress(idx, number_of_rows, printed_points=points or 0)
            if self.session_utc_column_name.endswith("dt"):
                if not row[self.session_utc_column_name]:
                    continue
                timestamp = autotrader_lib.util.convert_dt_to_float_timestamp(row[self.session_utc_column_name])
            else:
                timestamp = autotrader_lib.util.convert_to_float_timestamp(
                    row[self.session_utc_column_name].rstrip("Z"),
                    self.date_format)

            for message in [self.check_session.send(timestamp), self.check_gap.send(timestamp)]:
                if message:
                    log_messages.append(message)

            try:
                json_struct = self.get_translated_payload(row)
                if json_struct["message_type"] == "product":

                    self.trader.get_exchange(self.exchange).update_from_json(json_struct,
                                                                             json_struct.get("timestamp", time.time()))
            except autotrader_lib.util.MessageTypeNotImplemented:
                continue

        print("first run ready")
        print("\n".join(log_messages))

    def _filter_by_area(self, adapted_json_struct):
        if self.area_filter is not None:
            if adapted_json_struct["message_type"] == "order_book":
                adapted_json_struct["data"] = [
                    entry for entry in adapted_json_struct["data"]
                    if entry["delivery_area_id"] in AREAS[self.area]
                ]
            elif adapted_json_struct["message_type"] == "public_trade" and AREAS_DE:
                adapted_json_struct["data"] = [
                    entry for entry in adapted_json_struct["data"]
                    if entry["buy_delivery_area"] in self.area_filter or entry["sell_delivery_area"] in self.area_filter
                ]

    def open_file_descriptors(self, grouping_keys):
        """Open file descriptor for all the keys contained in groupin_keys
        :param grouping_keys: filename we will write into
        :type grouping_keys: list
        :return a list of all the open file descriptors
        """
        fds = dict()
        for grouping in grouping_keys:
            filename = self._get_output_filename(grouping)
            fds[grouping] = open(os.path.join(self.output, filename), "w")
        return fds

    @staticmethod
    def close_file_descriptors(file_descriptors):
        for fd in file_descriptors.values():
            fd.close()

    @staticmethod
    def write_line(fd, data):
        # sort_keys to have at least some kind of order
        fd.write(json.dumps(data, sort_keys=True))
        fd.write("\n")

    def _create_init_files(self):
        """
        creating init-files is only supported for Trayport
        :return: None
        :rtype: None
        """
        pass

    def run(self):
        self._create_init_files()

        if self.init_files_only:
            print("Only init files were requested - done!")
            return

        date_dt = UTIL.DTConv.str2y_m_d(self.date_string, "%Y-%m-%d").date()
        start_ts, end_ts = autotrader_core.utils.boundaries_for_cet_day(date_dt)
        grouping_keys = []  # can be a product_id or a timestamp according to the value of self.split
        products_list = []
        products_of_day = set()
        number_of_rows = self.get_number_of_rows()

        self.update_trader(self.select_all_rows(), number_of_rows)
        # get products from autotrader

        if self.split in ["product", "hour", "6hours"]:
            for product in self._trader_exchange[self.exchange].products.get_all():
                if not (start_ts <= product.delivery_start < end_ts):
                    continue
                products_list.append(product)
                products_of_day.add(product.product_id)
                if self.split == "product":
                    grouping_keys.append(product.product_id)
        elif not self.split:
            grouping_keys.append(self.output)
            for product in self._trader_exchange[self.exchange].products.get_all():
                if start_ts <= product.delivery_start < end_ts:
                    products_of_day.add(product.product_id)
        print("product list done")

        # put products in 1 hour/ 6h slots (only products < raster will be exported)
        if self.split in ("hour", "6hours"):
            raster = COMMON.HOUR if self.split == "hour" else COMMON.HOUR * 6
            first_start = min([p.delivery_start for p in products_list])
            first_start_rounded = first_start - (first_start % COMMON.HOUR)

            product_slots = {}
            for p in products_list:
                product_slots[p.product_id] = (p.delivery_start, p.delivery_end)
            hour_slots = list(
                range(first_start_rounded, (max([p.delivery_end for p in products_list])), raster)
            )
            slots = {}
            for hour in hour_slots:
                for p_id, p_delivery in product_slots.items():
                    p_start, p_end = p_delivery
                    if p_start >= hour and p_end <= hour + raster:
                        slots[p_id] = hour
            for hour in slots.values():
                if hour not in grouping_keys:
                    grouping_keys.append(hour)

        # put products in the correct slots
        points = 0
        self.check_session = self.is_new_session()

        file_descriptors = self.open_file_descriptors(grouping_keys)
        for idx, row in enumerate(self.select_all_rows()):
            points = self.print_progress(idx, number_of_rows, printed_points=points or 0)
            if self.session_utc_column_name.endswith("dt"):
                if not row[self.session_utc_column_name]:
                    continue
                timestamp = autotrader_lib.util.convert_dt_to_float_timestamp(row[self.session_utc_column_name])
            else:
                timestamp = autotrader_lib.util.convert_to_float_timestamp(
                    row[self.session_utc_column_name].rstrip("Z"),
                    self.date_format)

            new_session = bool(self.check_session.send(timestamp))

            if new_session:
                new_session_json = {"message_type": "new_session", "timestamp": timestamp, "data": [timestamp],
                                    "exchange": self.exchange}
                for grouping in grouping_keys:
                    self.write_line(file_descriptors[grouping], new_session_json)

            try:
                json_struct = self.get_translated_payload(row)
            except autotrader_lib.util.MessageTypeNotImplemented:
                continue
            else:
                # these are private messages and do not need to be translated
                if json_struct["message_type"] in ["error_response", "ack_response", "order_execution", "own_trade"]:
                    continue

            adapted_json_struct = json_struct.copy()
            adapted_json_struct["data"] = list()
            if not self.split:
                if json_struct and isinstance(json_struct["data"], list):
                    # filter out all products not in day
                    if not products_of_day:  # On Trayport, we do not have any product-ids
                        # NOTE (bet): TRAYPORT-support for build_simulation_files is minimalistic,
                        #             as it will not be needed once Data-Analytics will provide the exchange feeds.
                        #             We only support putting everything into a single file without any splitting.
                        adapted_json_struct["data"] = json_struct["data"]
                    else:
                        adapted_json_struct["data"] = [entry for entry in json_struct["data"]
                                                       if entry.get("product_id") in products_of_day]
                    self._filter_by_area(adapted_json_struct)
                    if adapted_json_struct["data"]:
                        self.write_line(file_descriptors[self.output], adapted_json_struct)

            else:
                if adapted_json_struct and isinstance(json_struct["data"], list):
                    for entry in json_struct["data"]:
                        product_id = entry["product_id"]
                        if self.split in ("hour", "6hours"):
                            try:
                                grouping = slots[product_id]
                            except KeyError:
                                continue
                            adapted_json_struct["data"] = [entry]
                        else:  # "product"
                            grouping = product_id
                            adapted_json_struct["data"].append(entry)
                        self._filter_by_area(adapted_json_struct)
                        if grouping in grouping_keys and adapted_json_struct["data"]:
                            self.write_line(file_descriptors[grouping], adapted_json_struct)
                else:
                    for grouping in grouping_keys:
                        self.write_line(file_descriptors[grouping], adapted_json_struct)

        self.close_file_descriptors(file_descriptors)
        print("second run ready")


class EpexBuildSimulation(BaseBuildSimulation):

    def __init__(self, filename, output, area=None, split=None):
        super(EpexBuildSimulation, self).__init__(output, exchange=COMMON.Exchange.epex, area=area, split=split)

        self.filename = filename
        # sqlite objects
        self.conn = sqlite3.connect(self.filename)
        self.conn.row_factory = sqlite3.Row  # this will allow us to access the returned data like a dictionary
        self.cursor = self.conn.cursor()
        self.date_string = os.path.basename(self.filename).split(".")[0]
        self.table_name = ""

    def get_translated_payload(self, row):
        super(EpexBuildSimulation, self).get_translated_payload(row)

    def get_number_of_rows(self):
        query = "SELECT COUNT({}) FROM {}".format(self.session_utc_column_name, self.table_name)
        return self.cursor.execute(query).fetchone()[0]

    def select_all_rows(self):
        query = "SELECT * FROM {0} ORDER BY rowid ASC".format(self.table_name)
        return self.cursor.execute(query)


class OldBuildSimulation(EpexBuildSimulation):
    """ To use on the old db format i.e with table xmldata and columns
        (session_utc_ts, xml_utc_ts, header, properties, xml_type, xml_payload, payload_sha256)
    """

    def __init__(self, filename, output, area=None, split=None, **kwargs):
        super(OldBuildSimulation, self).__init__(filename, output, area=area, split=split)
        self.table_name = "xmldata"
        self.session_utc_column_name = "session_utc_ts"

    def get_translated_payload(self, row):
        xml_utc_ts = row["xml_utc_ts"].strip("Z")
        try:
            timestamp = autotrader_lib.util.convert_to_float_timestamp(xml_utc_ts, self.date_format)
        except ValueError:
            # means there is no microseconds so we should use a slightly different dt format i.e without '.%f'
            timestamp = autotrader_lib.util.convert_to_float_timestamp(xml_utc_ts, self.date_format[:-3])
        return autotrader_lib.standard_message_adapter.M7TranslatorMixIn.from_xml_to_json(
            row["xml_payload"].encode("utf-8"), timestamp)


class NewBuildSimulation(EpexBuildSimulation):
    """ To use on the new db format i.e with tables data,db_version and columns
        (session_utc, message_utc, header, properties, message_type, raw_payload, translated_payload, payload_sha256)
    """

    def __init__(self, filename, output, split=None, area=None, **kwargs):
        super(NewBuildSimulation, self).__init__(filename, output, area=area, split=split)
        self.date_format = "%Y-%m-%dT%H:%M:%S.%f"
        self.table_name = "data"
        self.session_utc_column_name = "session_utc"

    def get_translated_payload(self, row):
        return json.loads(row["translated_payload"])


class MongoBuildSimulation(BaseBuildSimulation):

    def __init__(self, host, date, username, password, database_name, database_port, output,
                 area=None, split=None, init_files_only=False, exchange=COMMON.Exchange.trayport,
                 database_auth_source="autoTRADER"):
        # looks like the exchange type is not of great importance, since "nordpool" also works with trayport data
        super(MongoBuildSimulation, self).__init__(output, exchange=exchange, area=area, split=split,
                                                   init_files_only=init_files_only)
        self.date = date
        self.date_string = date
        self.session_utc_column_name = "session_dt"
        self.database = self.init_db(database_name, host=host, port=database_port, username=username, password=password,
                                     authSource=database_auth_source)

    def init_db(self, database_name, **kwargs):
        client = pymongo.MongoClient(**kwargs)
        database = client.get_database(database_name)
        if self.date not in database.list_collection_names():
            print("Looks like the database does not have data for this date : {}".format(self.date))
        return database

    def get_number_of_rows(self):
        ret = self.database[self.date].find({"object_type": {"$nin": ["public_trade", "order_execution"]}}).count()
        return ret

    def select_all_rows(self):
        query = {"object_type": {"$nin": ["public_trade", "order_execution"]}}
        sort_query = [("message_dt", pymongo.ASCENDING)]
        # For sorting in an efficient way and to avoid running out of memory, we need an index here.
        self.database[self.date].create_index([("message_dt", -1)])
        return self.database[self.date].find(query).sort(sort_query)

    def get_translated_payload(self, row):
        return row["translated_payload"]

    def update_trader(self, data, number_of_rows):
        log_messages = []
        points = 0

        for idx, row in enumerate(data):
            points = self.print_progress(idx, number_of_rows, printed_points=points or 0)

            # if the epex connection is restarted too often, it could happen that a message has no session_dt
            # the session_dt is created on the startup of the connection and therefore all messages without it
            # are faulty and should be skipped/discarded
            if not row["session_dt"]:
                continue
            timestamp = autotrader_lib.util.convert_dt_to_float_timestamp(row["session_dt"])

            for message in [self.check_session.send(timestamp), self.check_gap.send(timestamp)]:
                if message:
                    log_messages.append(message)

            try:
                json_struct = row["translated_payload"]
                if json_struct["message_type"] == "product":
                    self.trader.update_from_json(json_struct, row["properties"])
            except autotrader_lib.util.MessageTypeNotImplemented:
                continue

        print("first run ready")
        print("\n".join(log_messages))

    def _is_trayport(self):
        """
        Utility function to check if the mongo database we are using contains data from Trayport.
        :return: True if field `translated_payload.exchange` matches `TRAYPORT_EXCHANGE_NAME`
        :rtype: bool
        """
        q = {"translated_payload.exchange": TRAYPORT_EXCHANGE_NAME}
        document = self.database[self.date].find_one(q)
        return bool(document)

    def _get_by_message_type(self, mt):
        """
        Gets all messages of message_type `mt`
        :param mt: desired message_type
        :type mt: str
        :return: mongo cursor
        :rtype: pymongo.cursor.Cursor
        """
        q = {"message_type": mt}
        cur = self.database[self.date].find(q)
        return cur

    def _create_init_file_for_mt(self, mt, init_folder, limit=None):
        """
        Creates the init-file for message type `mt` in folder `init_folder`
        :param mt: message type, used as query argument when querying mongo
        :type mt: str
        :param init_folder: destination folder for output file
        :type init_folder: str
        :param limit: optional query limit
        :type limit: int | None
        :return: None
        :rtype: None
        """
        cur = self._get_by_message_type(mt)
        if limit:
            cur = cur.limit(limit)

        if cur.count() == 0:
            print("No messages found for type {t}".format(t=mt))
            return

        dump_file = "{mt}.jsonl".format(mt=mt)
        dump_file = os.path.join(init_folder, dump_file)

        with open(dump_file, "w") as fp:
            for c in cur:
                fp.write(json.dumps(c["translated_payload"]))
                fp.write("\n")

    def _create_init_files(self):
        """
        Creates the init-files for backtesting when processing Trayport data.
        :return: None
        :rtype: None
        """
        if not self._is_trayport():
            # creating init-files is only supported for trayport-data
            return

        print("creating init files ...")

        init_folder = os.path.join(self.output, "init_files_{d}".format(d=self.date))
        if not os.path.isdir(init_folder):
            os.makedirs(init_folder)
        else:
            print("init_folder {f!r} already exists".format(f=init_folder))

        for mt, limit in TRAYPORT_INIT_FILES_MESSAGE_TYPES.items():
            self._create_init_file_for_mt(mt, init_folder, limit)


def extract_zip(filename):
    """ If the filename in param ends with .gz we assume it's an archive and try to extract it
        Creates the unzipped file in the same folder than the file itself

    :param filename: the name of the archive
    :type filename: str
    """
    with gzip.open(filename, 'rb') as f_in, open(filename[:-3], 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)


def parse_args(argv=None):
    epilog = """
Usage example:
    You first have to specify the common parameter output and if you want to split or filter the output
    (with --split, --area). Optionally you can add information on whose exchange's data will be parsed.
    That exchange will be added to error messages without explicit mention of the exchange in the data feed.
    Then specify the database to use (sqlite or mongo) and specify the parameters needed according to the database.

    Using a sqlite database:
        - `python -m build_simulation_files /tmp/output_folder sqlite ./database.sqlite3`

    Using a sqlite database, using EPEX as info:
        - `python -m build_simulation_files /tmp/output_folder --exchange EPEX sqlite ./database.sqlite3`
        - `python -m build_simulation_files /tmp/output_folder -eEPEX sqlite ./database.sqlite3`


    To get more help with building simulation files with sqlite :
        - python -m build_simulation_files /tmp/output_folder sqlite --help
        - python -m build_simulation_files /tmp/output_folder -eEPEX sqlite --help


    Using a mongo database:
        - python -m build_simulation_files /tmp/output_folder mongo localhost 2020-02-08 -u vt -p vt
        - python -m build_simulation_files /tmp/output_folder -eTRAYPORT mongo localhost 2020-02-08 -u vt -p vt
        - python -m build_simulation_files /tmp/output_folder --exchange TRAYPORT mongo localhost 2020-02-08 -u vt -p vt

    To get more help with building simulation files with mongo :
        - python -m build_simulation_files /tmp/output_folder mongo --help

    Or start it by referencing the module, and only executing for init files on trayport
        - python -m autotrader_core.i9ntests.build_simulation_files --init_files_only=True
              /home/vt/trayport/trayport-data/SPY/ mongo --database_port=27017
              --database_name=SPY -u vt -p vt atspy-trayport.visotech.at "2021-06-05"
        - python -m autotrader_core.i9ntests.build_simulation_files --init_files_only=True
              /home/vt/trayport/trayport-data/SPY/ -eTRAYPORT mongo --database_port=27017
              --database_name=SPY -u vt -p vt atspy-trayport.visotech.at "2021-06-05"
        - python -m autotrader_core.i9ntests.build_simulation_files --init_files_only=True
              /home/vt/trayport/trayport-data/SPY/ --exchange TRAYPORT mongo --database_port=27017
              --database_name=SPY -u vt -p vt atspy-trayport.visotech.at "2021-06-05"

    You can also specify the database_name and the database_port in case this is different than the default.
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(epilog=epilog, formatter_class=argparse.RawTextHelpFormatter)
    # common parameter for both sqlite and mongo version
    parser.add_argument('output', help="Where to save the exported files.")
    parser.add_argument('-s', '--split', metavar='SPLIT', choices=["hour", "6hours", "product"],
                        help="Where to split the exported files. (\"hour\", \"6 hours\", \"product\")")
    area_text = ", ".join("\"{}\"".format(area) for area in sorted(AREAS.keys()))
    parser.add_argument('-a', '--area', metavar='AREA', choices=list(AREAS.keys()),
                        help="Filter data by area. ({})".format(area_text))

    parser.add_argument("--init_files_only", default=False,
                        help="create only the init files, currently only supported for trayport exchange")
    parser.add_argument('-e', '--exchange', default=None, metavar='exchange', choices=EXCHANGES,
                        help=("Exchange of the given feed, one of: {}. "
                              "Used when new session messages is injected.".format(EXCHANGES)))

    subparser = parser.add_subparsers(
        title="database", description="The database to use to create the simulation files", help="Available databases"
    )

    sqlite_parser = subparser.add_parser(
        "sqlite", help="Use a local .sqlite3 file as data input. Mandatory parameters : filename"
    )
    sqlite_parser.add_argument('filename', help="The input data stored in a .sqlite3 file.")
    mongo_parser = subparser.add_parser("mongo", help="Connect to an external mongo database as data input. "
                                                      "Mandatory parameters : host, data")
    mongo_parser.add_argument('host', help="Database host to connect to.")
    mongo_parser.add_argument('date', help="Date of the data to use (e.g 2020-01-21).")
    mongo_parser.add_argument("-u", "--username", default=None, help="username of the mongo user.")
    mongo_parser.add_argument("-p", "--password", default=None, help="password for the user in mongo.")
    mongo_parser.add_argument("--database_name", default="SPY", help="Name of the database.")
    mongo_parser.add_argument("--database_port", default=27017, type=int, help="Port of the database.")

    args = parser.parse_args(argv)
    return args


def get_available_tables_from_db(filename):
    """ Get all the table from the database of the filename

    :param filename: the db filename
    :type filename: str
    :return: the tables of the db
    :rtype list
    """
    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    result = cursor.fetchall()[0]
    conn.close()
    return result


if __name__ == "__main__":
    args = parse_args()

    obj = None
    if hasattr(args, "filename"):  # we are in sqlite mode
        if args.filename.endswith(".gz"):
            extract_zip(args.filename)
            args.filename = args.filename[:-3]
        available_table_in_db = get_available_tables_from_db(args.filename)
        obj_class = OldBuildSimulation if "xmldata" in available_table_in_db else NewBuildSimulation
        obj = obj_class(**args.__dict__)
    elif hasattr(args, "host"):  # we are in mongo mode
        obj = MongoBuildSimulation(**args.__dict__)
    else:
        print("Unknown mode. Exiting...")

    obj.run()
