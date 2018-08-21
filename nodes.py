import asyncio
import signal
import logging
import colorlog
import configparser
import uvloop
import model
from protocol import BitcoinProtocol
import traceback
import sys
import asyncpg

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
class App:
    def __init__(self, loop, logger, config):
        self.loop = loop
        self.log = logger
        self.connector = False
        self.config = config
        self.db_pool = False
        self.dsn = config['POSTGRESQL']['DSN']
        self.settings={}
        self.settings['MAGIC'] = config['PROTOCOL']["MAGIC_NUMBER"]
        self.settings['PING_TIMEOUT'] = config['PROTOCOL']["TIMEOUT"]
        self.settings['HANDSHAKE_TIMEOUT'] = config['PROTOCOL']["TIMEOUT"]
        self.settings["CONNECT_TIMEOUT"] = config['PROTOCOL']["TIMEOUT"]
        self.settings['GETADDR_INTEVAL'] = config['PROTOCOL']["GETADDR_INTEVAL"]

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
            await model.create_db_model(conn,self.log)
            await conn.close()
            self.log.info("Init db pool ")
            self.db_pool = await asyncpg.create_pool(dsn=self.dsn,
                                                     loop=self.loop)
            self.background_tasks.append(self.loop.create_task(self.find_nodes()))


        except Exception as err:
            self.log.error("Start failed")
            self.log.error(str(traceback.format_exc()))
            self.terminate(None, None)

    async def find_nodes(self):
        while True:
            known_nodes=await model.get_known_nodes(self.db_pool)
            for node in known_nodes:
                node_task= self.node_ask(node)
                self.loop.create_task(node_task)
            await asyncio.sleep(self.settings['GETADDR_INTEVAL'])

    async def node_ask(self,node):
        ip = node['ip']
        port = node['port']
        node_connect=BitcoinProtocol(ip, port, self.settings, self.log)
        active_nodes=node_connect.getaddr()
        await model.update_nodes(self.db_pool,active_nodes)


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


def init(loop):
    log_level = logging.INFO
    logger = colorlog.getLogger('fwd')
    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(asctime)s %(levelname)s: %(message)s (%(module)s:%(lineno)d)')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    config_file = "config.conf"
    config = configparser.ConfigParser()
    config.read(config_file)
    app = App(loop, logger, config)
    return app


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    app = init(loop)
    loop.run_forever()
    pending = asyncio.Task.all_tasks()
    loop.run_until_complete(asyncio.gather(*pending))
    loop.close()