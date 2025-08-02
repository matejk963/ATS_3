#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
import signal

import six
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
# make fast_logger the real logger. This line does not work anywhere else! It has to be the first line in the project.
FLOG.make_standard_logging_module()

import autotrader_core.autotrader_core_main_parent as ACMP
import autotrader_core.autotrader_core_main_child as ACMC
import autotrader_lib
import autotrader_lib.codec.msgpackcodec
import autotrader_lib.config_helper as ATCONF
import autotrader_lib.log
import autotrader_lib.compliance_log_templates as LOGTEMP

LOGGER = "autotrader"
log = FLOG.getLogger(LOGGER)


def main():
    """Entry point for the autotrader core executable. Parses config and instantiates AutotraderCoreMain."""

    # autotrader_lib is configured 3 times
    # first configuration uses a fallback path if nbroot is not set
    # second configuration uses a nbroot as given in the command line arguments, or home folder as fallback
    # third configuration allows to turn of console if not specified in the command line arguments
    FLOG.log_to_stdout = True

    args = ATCONF.AutotraderCommandLineConfig(log).parse_from_command_line()

    autotrader_config = ATCONF.ATConfig(log)
    epex_config = ATCONF.EpexConfig(log)
    epex_manager_config = ATCONF.EpexManagerConfig(log)
    nordpool_config = ATCONF.NordpoolConfig(log)
    nordpool_manager_config = ATCONF.NordpoolManagerConfig(log)
    trayport_config = ATCONF.TrayportConfig(log)
    trayport_manager_config = ATCONF.TrayportManagerConfig(log)

    mongo_config = ATCONF.MongoConfig(log)
    prompt_config = ATCONF.PromptConfig(log)

    autotrader_config.get_configs_from_file(args.conf, "autotrader")
    mongo_config.get_configs_from_file(args.conf, "autotrader_mongo")
    prompt_config.get_configs_from_file(args.conf, "prompt")
    if autotrader_config.epex:
        epex_config.get_configs_from_file(args.conf, "autotrader_comxerv")
        epex_manager_config.get_configs_from_file(args.conf, "autotrader_epex-manager")
        if not isinstance(epex_config.epex_account_id, six.string_types):
            raise ValueError("Could not find epex_account_id in epex configs")
        if not isinstance(epex_config.epex_user_id, six.string_types):
            raise ValueError("Could not find epex_user_id in epex configs")
        epex_manager_config.console |= args.console
    if autotrader_config.nordpool:
        nordpool_config.get_configs_from_file(args.conf, "autotrader_nordpool")
        nordpool_manager_config.get_configs_from_file(args.conf, "autotrader_nordpool-manager")
        nordpool_manager_config.console |= args.console
    if autotrader_config.trayport:
        trayport_config.get_configs_from_file(args.conf, "autotrader_trayport")
        trayport_manager_config.get_configs_from_file(args.conf, "autotrader_trayport-manager")
        trayport_manager_config.console |= args.console

    autotrader_config.console |= args.console

    log_filename = "autotrader_child_{}.log".format(args.child_id) if args.child_id is not None else "autotrader.log"
    FLOG.setup(autotrader_lib.log.create_logspath(), log_filename, p_log_to_stdout=autotrader_config.console,
               silence_time=autotrader_config.compliance_log_silence_period)

    FLOG.set_server_role(prompt_config.role_str)

    log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.autotrader_service_start)

    log.debug("autoTRADER is starting with the following environment variables: {}".format(dict(os.environ)))

    ATCONF.properties_log_dump([args, autotrader_config, mongo_config, epex_config, epex_manager_config,
                                nordpool_config, nordpool_manager_config, trayport_config, trayport_manager_config,
                                prompt_config],
                               base_log_message="autotrader startup",
                               log=log)

    if args.child_id is not None:
        at_core_main = ACMC.AutotraderCoreMainChild(args.child_id, autotrader_config, mongo_config, epex_config,
                                                    epex_manager_config, nordpool_config, nordpool_manager_config,
                                                    trayport_config, trayport_manager_config)
    else:
        at_core_main = ACMP.AutotraderCoreMainParent(autotrader_config, mongo_config, epex_config, epex_manager_config,
                                                     nordpool_config, nordpool_manager_config,
                                                     trayport_config, trayport_manager_config)

    def let_us_die(signum, unused_frame):
        """signal handler for graceful shutdown"""
        log.info("signal {} -- shutting down.".format(signum))
        at_core_main.stop()

    signal.signal(signal.SIGTERM, let_us_die)
    signal.signal(signal.SIGINT, let_us_die)

    at_core_main.run()
    at_core_main.terminate()


if __name__ == "__main__":
    main()
    log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.autotrader_service_stop)
