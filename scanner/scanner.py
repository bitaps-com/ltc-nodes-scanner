import asyncio
import signal
import logging
import colorlog
import argparse
from setproctitle import setproctitle
import configparser
import uvloop
import model
import view
from protocol import BitcoinProtocol
import traceback
import sys
import asyncpg
import ipaddress
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
class App:
    def __init__(self, logger, config):
        self.loop = asyncio.get_event_loop()
        self.log = logger
        self.connector = False
        self.config = config
        self.db_pool = False
        self.dsn = config['POSTGRESQL']['dsn']
        self.psql_pool_threads = int(config["POSTGRESQL"]["pool_threads"])
        self.init={}
        # self.init['ip']=ipaddress.IPv4Address(config['INIT_NODE']['IP'])
        # self.init['port'] = int(config['INIT_NODE']['PORT'])
        self.settings={}
        # self.settings['MAGIC'] = config['PROTOCOL']["MAGIC_NUMBER"]
        # self.settings['PING_TIMEOUT'] = int(config['PROTOCOL']["TIMEOUT"])
        # self.settings['PROTOCOL_VERSION'] = int(config['PROTOCOL']["PROTOCOL_VERSION"])
        # self.settings['SERVICES'] = int(config['PROTOCOL']["SERVICES"])
        # self.settings['USER_AGENT'] = config['PROTOCOL']["USER_AGENT"]
        # self.settings['MAX_UINT64'] = int(config['PROTOCOL']["MAX_UINT64"])
        # self.settings['HANDSHAKE_TIMEOUT'] = int(config['PROTOCOL']["TIMEOUT"])
        # self.settings["CONNECT_TIMEOUT"] = int(config['PROTOCOL']["TIMEOUT"])
        # self.settings['GETADDR_INTEVAL'] = int(config['PROTOCOL']["GETADDR_INTEVAL"])

        self.background_tasks = []

        self.log.info("Nodes find server init ...")
        signal.signal(signal.SIGINT, self.terminate)
        signal.signal(signal.SIGTERM, self.terminate)
        asyncio.ensure_future(self.start(), loop=self.loop)

    async def start(self):
        # init database
        try:
            self.log.info("Create database model")
            conn = await asyncpg.connect(dsn=self.dsn)
            # await model.create_db_model(conn, self.log, self.init)
            await conn.close()
            self.log.info("Init db pool ")
            self.db_pool = await asyncpg.create_pool(dsn=self.dsn,
                                                     loop=self.loop,
                                                     min_size=1, max_size=self.psql_pool_threads)
            # self.background_tasks.append(self.loop.create_task(self.find_nodes()))
            # self.background_tasks.append(self.loop.create_task(self.event_nodes_handler_init()))
            self.log.info("Start success")
        except Exception as err:
            self.log.error("Start failed")
            self.log.error(str(traceback.format_exc()))
            self.terminate(None, None)

    async def find_nodes(self):
        while True:
            self.log.info("find nodes init")
            known_nodes=await model.get_known_nodes(self.db_pool)
            for node in known_nodes:
                node_task= self.node_ask(node)
                self.loop.create_task(node_task)
            await asyncio.sleep(self.settings['GETADDR_INTEVAL'])

    async def node_ask(self,node):
        self.log.warning("node info %s" %node)
        ip = node['ip']
        port = node['port']
        node_connect=BitcoinProtocol(ip, port, self.settings, self.log, self.loop, self.address_handler)
        #active_nodes=await node_connect.getaddr()


    async def address_handler(self,data,ip, port):
        self.log.warning("address response received:")
        self.log.warning(data)
        # active nodes - ip and port list
        events_list = []
        events_list.append([view.EVENT_ASK_NODE, ip, port])
        for node in data:
            events_list.append([view.EVENT_SEE_NODE, node['ip'], node['port']])
        await model.insert_events_nodes(self.db_pool, events_list)

    async def event_nodes_handler_init(self):
        while True:
            self.log.info("event handler init")
            try:
                while True:
                    await view.event_nodes_handler(self)
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                self.log.info("event handler terminated")
                break
            except Exception:
                self.log.error("Event handler error")
                self.log.error(traceback.format_exc())
            await asyncio.sleep(1)




    def _exc(self, a, b, c):
        return

    def terminate(self, a, b):
        self.loop.create_task(self.terminate_coroutine())

    async def terminate_coroutine(self):
        sys.excepthook = self._exc
        self.log.error('Stop request received')

        for task in self.background_tasks:
            task.cancel()
        if self.db_pool:
            await self.db_pool.close()

        self.log.info("Server stopped")
        self.loop.stop()


def init(argv):
    parser = argparse.ArgumentParser(description="Bitcoin nodes scanner  v 0.0.1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--config", help = "config file", type=str, nargs=1, metavar=('PATH',))
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count", default=0)
    args = parser.parse_args()

    config_file = "scanner.conf"
    log_level = logging.WARNING
    logger = logging.getLogger("btc_nodes")

    if args.config is not None:
        config_file = args.config
    config = configparser.ConfigParser()
    config.read(config_file)
    if args.verbose > 0:
        log_level = logging.INFO
    if args.verbose > 1:
        connector_log_level = logging.INFO
    if args.verbose > 2:
        log_level = logging.DEBUG
    if args.verbose > 3:
        connector_log_level = logging.DEBUG

    logger = colorlog.getLogger('btc_nodes')
    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(asctime)s %(levelname)s: %(message)s (%(module)s:%(lineno)d)')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    config = configparser.ConfigParser()
    config.read(config_file)

    try:
        config["POSTGRESQL"]["dsn"]
        config["POSTGRESQL"]["pool_threads"]
    except Exception as err:
        logger.critical("Configuration failed: %s" % err)
        logger.critical("Shutdown")
        sys.exit(0)


    app = App(logger, config)
    return app


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    app = init(sys.argv[1:])
    loop.run_forever()
    pending = asyncio.Task.all_tasks()
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.wait(pending))
    loop.close()
