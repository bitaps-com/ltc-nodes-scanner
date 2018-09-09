import asyncio
import signal
import logging
import colorlog
import argparse
from setproctitle import setproctitle
import configparser
import uvloop
import model
from protocol import BitcoinProtocol
import traceback
import sys
import asyncpg
import aiodns
import time
import aiosocks
from utils import *


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


class App:

    def __init__(self, logger, config):
        setproctitle('btc node src')
        self.loop = asyncio.get_event_loop()
        self.log = logger
        self.config = config
        self.db_pool = False
        self.network = {"default_port": int(config["NETWORK"]["default_port"]),
                        "magic": int(config["NETWORK"]["magic"], 16),
                        "version": int(config["NETWORK"]["version"]),
                        "services": int(config["NETWORK"]["services"], 2),
                        "ping_timeout": int(config["NETWORK"]["ping_timeout"]),
                        "connect_timeout": int(config["NETWORK"]["connect_timeout"]),
                        "handshake_timeout": int(config["NETWORK"]["handshake_timeout"]),
                        "ip": '::ffff:127.0.0.1',
                        "user_agent": config["NETWORK"]["user_agent"],
                        }
        self.testnet = True if config["NETWORK"]["magic"] != "0xD9B4BEF9" else False
        self.seed_domain = config["SEED"]["domain"].split(",")
        self.dsn = config['POSTGRESQL']['dsn']
        self.psql_pool_threads = int(config["POSTGRESQL"]["pool_threads"])
        self.online_nodes = 0
        self.not_scanned_addresses = dict()
        self.scanning_addresses = dict()
        self.scanned_addresses = set()
        self.scan_threads_limit = int(config["SCAN"]["threads"])
        self.scan_threads = 0
        self.discovered_nodes = 0
        self.background_tasks = []
        self.log.info("Start btc node src ...")
        signal.signal(signal.SIGINT, self.terminate)
        signal.signal(signal.SIGTERM, self.terminate)
        asyncio.ensure_future(self.start())

    async def start(self):
        # init database
        try:
            self.log.info("Init db pool ")
            self.db_pool = await asyncpg.create_pool(dsn=self.dsn,
                                                     loop=self.loop,
                                                     min_size=1, max_size=self.psql_pool_threads)
            await model.create_db_model(self.db_pool)
        except Exception as err:
            self.log.error("Start failed")
            self.log.error(str(traceback.format_exc()))
            self.terminate(None, None)
        self.background_tasks.append(self.loop.create_task(self.discovery_loop()))
        self.background_tasks.append(self.loop.create_task(self.statistics_loop()))



    async def discovery_loop(self):
        while True:
            try:
                self.log.info("Start discovering round")
                q = time.time()
                progress_timer = time.time()
                self.discovered_nodes = 0
                self.online_nodes = 0
                self.not_scanned_addresses = dict()
                self.scanning_addresses = dict()
                self.scanned_addresses = set()
                await self.get_seed_from_dns()
                await self.get_bootstrap_from_db()
                self.add_bootstrap_tor_seed()
                while self.not_scanned_addresses or self.scanning_addresses:
                    if self.scan_threads < self.scan_threads_limit:
                        if self.not_scanned_addresses:
                            address = next(iter(self.not_scanned_addresses))
                            port = self.not_scanned_addresses[address]["port"]
                            del self.not_scanned_addresses[address]
                            self.scanning_addresses[address] = {"port": port}
                            self.scan_threads += 1
                            self.loop.create_task(self.scan_address(address, port))
                        else:
                            await asyncio.sleep(0.1)
                    else:
                        await asyncio.sleep(0.1)
                    if time.time() - progress_timer > 2:
                        progress_timer = time.time()
                        total = len(self.not_scanned_addresses) + len(self.scanning_addresses)
                        total +=  len(self.scanned_addresses)
                        self.log.info("Scan progress: %s discovered: %s scanned: %s success: %s  threads: %s " %
                                      (str(round((len(self.scanned_addresses) / total ) * 100, 2)) + "%",
                                       total,
                                       len(self.scanned_addresses),
                                       self.online_nodes,
                                       self.scan_threads))

                self.log.info("Discovery round completed")
            except asyncio.CancelledError:
                self.log.warning("Discovery task canceled")
                break
            except Exception as err:
                self.log.critical("Discovery task  error %s" % err)
                self.log.critical(str(traceback.format_exc()))
            await asyncio.sleep(10)


    async def statistics_loop(self):
        while True:
            try:
                await model.summary(self.db_pool)
            except asyncio.CancelledError:
                self.log.warning("Statistics task canceled")
                break
            except Exception as err:
                self.log.critical("Statistics task  error %s" % err)
                self.log.critical(str(traceback.format_exc()))
            await asyncio.sleep(1)





    async def get_bootstrap_from_db(self):
        rows =await model.get_last_24hours_addresses(self.db_pool)
        for row in rows:
            self.not_scanned_addresses[row["ip"].decode()] = {"port" :row["port"],
                                                             "address": row["ip"].decode()}
        self.log.info("Last 24 hours active addresses from db %s" % len(rows))

    async def get_seed_from_dns(self):
        self.log.info("Get bootstrap addresses from dns seeds")
        tasks = []
        for domain in self.seed_domain:
            tasks.append(self.loop.create_task(self.resolve_domain(domain)))
        await asyncio.wait(tasks)
        self.log.info("All seed domains resolved, received %s addresses" % len(self.not_scanned_addresses))

    def add_bootstrap_tor_seed(self):
        if self.testnet:
            tor_seeds = [
                ('thfsmmn2jbitcoin.onion', 18333),
                ('it2pj4f7657g3rhi.onion', 18333),
                ('nkf5e6b7pl4jfd4a.onion', 18333),
                ('4zhkir2ofl7orfom.onion', 18333),
                ('t6xj6wilh4ytvcs7.onion', 18333),
                ('i6y6ivorwakd7nw3.onion', 18333),
                ('ubqj4rsu3nqtxmtp.onion', 18333)]
        else:
            tor_seeds = [
                ('5ghqw4wj6hpgfvdg.onion', 8333),
                ('bitcoinostk4e4re.onion', 8333),
                ('bk5ejfe56xakvtkk.onion', 8333),
                ('czsbwh4pq4mh3izl.onion', 8333),
                ('e3tn727fywnioxrc.onion', 8333),
                ('evolynhit7shzeet.onion', 8333),
                ('i2r5tbaizb75h26f.onion', 8333),
                ('jxrvw5iqizppbgml.onion', 8333),
                ('kjy2eqzk4zwi5zd3.onion', 8333),
                ('pqosrh6wfaucet32.onion', 8333),
                ('pt2awtcs2ulm75ig.onion', 8333),
                ('szsm43ou7otwwyfv.onion', 8333),
                ('tfu4kqfhsw5slqp2.onion', 8333),
                ('vso3r6cmjoomhhgg.onion', 8333),
                ('xdnigz4qn5dbbw2t.onion', 8333),
                ('zy3kdqowmrb7xm7h.onion', 8333)
            ]
        for a in tor_seeds:
            self.not_scanned_addresses[a[0]] = {"port": a[1],
                                                "address": a[0]}

    async def resolve_domain(self, domain):
        self.log.debug('resolving domain %s' % domain)
        resolver = aiodns.DNSResolver(loop=self.loop)
        query = resolver.query(domain, 'A')
        try:
            result = await asyncio.ensure_future(query, loop=self.loop)
        except Exception as err:
            self.log.error('%s %s' % (domain, err))
            return
        c = 0
        for i in result:
            self.log.debug('%s received from %s' % (i.host, domain))
            c += 1
            if not self.not_scanned_addresses or 1:
                self.not_scanned_addresses[i.host] = {"port": self.network["default_port"],
                                                               "address": i.host}
        query = resolver.query(domain, 'AAAA')
        try:
            result = await asyncio.ensure_future(query, loop=self.loop)
        except Exception as err:
            self.log.error('%s %s' % (domain, err))
            return
        t = 0
        c2 = 0
        for i in result:
            self.log.debug('%s received from %s' % (i.host, domain))
            c2 += 1
            if not self.not_scanned_addresses or 1:
                a = bytes_to_address(ip_address_to_bytes(i.host))
                if a.endswith('.onion'):
                    t += 1
                self.not_scanned_addresses[i.host] = {"port": self.network["default_port"],
                                                               "address": i.host}



        self.log.info('%s ipv4 %s ipv6 %s  tor addresses received from %s' % (c, c2, t, domain))

    async def scan_address(self, address, port):
        try:
            if address.endswith(".onion"):
                proxy = aiosocks.Socks5Addr('127.0.0.1', 9050)
            else:
                proxy = None
            conn = BitcoinProtocol(address, port, self.network, self.testnet, self.log, proxy = proxy)
            try:
                await asyncio.wait_for(conn.handshake, timeout=10)
            except:
                pass
            if conn.handshake.result() == True:
                try:
                    await asyncio.wait_for(conn.addresses_received, timeout=10)
                except:
                    pass
                for a in conn.addresses:
                    if a["address"] not in self.not_scanned_addresses:
                        if a["address"] not in self.scanning_addresses:
                            if a["address"] not in self.scanned_addresses:
                                self.not_scanned_addresses[a["address"]] = a
                self.online_nodes += 1
                # add record to db
                net = network_type(address)
                if net == "TOR":
                    geo = {"country": None,
                            "city": None,
                            "geo": None,
                            "timezone": None,
                            "asn": None,
                            "org": None}
                else:
                    geo = await self.loop.run_in_executor(None, model.get_geoip, address)

                await model.report_online(address,
                                          port,
                                          net,
                                          conn.user_agent,
                                          conn.latency,
                                          conn.version,
                                          conn.start_height,
                                          conn.services,
                                          geo,
                                          int(time.time()),
                                          self.db_pool)
            else:
                await model.report_offline(address,
                                           self.db_pool)
            conn.__del__()

        except:
            try:
                await model.report_offline(address,
                                           self.db_pool)
                conn.__del__()
            except:
                pass

        self.scan_threads -= 1
        del self.scanning_addresses[address]
        self.scanned_addresses.add(address)






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
    parser = argparse.ArgumentParser(description="Bitcoin nodes src  v 0.0.1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--config", help="config file", type=str, nargs=1, metavar=('PATH',))
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count", default=0)
    args = parser.parse_args()

    config_file = "../config/btc_node_scanner.conf"
    log_level = logging.WARNING

    if args.config is not None:
        config_file = args.config
    config = configparser.ConfigParser()
    config.read(config_file)
    if args.verbose > 0:
        log_level = logging.INFO
    if args.verbose > 1:
        log_level = logging.DEBUG


    logger = colorlog.getLogger('btc_nodes')
    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(asctime)s %(levelname)s: %(message)s')
    # formatter = colorlog.ColoredFormatter('%(log_color)s%(asctime)s %(levelname)s: %(message)s (%(module)s:%(lineno)d)')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    config = configparser.ConfigParser()
    config.read(config_file)

    try:
        config["POSTGRESQL"]["dsn"]
        config["POSTGRESQL"]["pool_threads"]
        config["SEED"]["domain"]
        int(config["NETWORK"]["default_port"])
        int(config["NETWORK"]["magic"], 16)
        int(config["NETWORK"]["version"])
        int(config["NETWORK"]["services"], 2)
        config["NETWORK"]["user_agent"]
        int(config["NETWORK"]["ping_timeout"])
        int(config["NETWORK"]["connect_timeout"])
        int(config["NETWORK"]["handshake_timeout"])
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
