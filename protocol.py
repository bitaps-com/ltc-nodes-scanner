
import ipaddress
import time
import asyncio
import logger
import colorlog
import random
import struct
from pybtc import *
import hashlib
import json
import binascii
import model
import traceback



class BitcoinProtocol():
    def __init__(self, ip, port, settings,logging):
        self.MAGIC = settings["MAGIC"]
        self.PING_TIMEOUT = settings["PING_TIMEOUT"]
        self.HANDSHAKE_TIMEOUT = settings["HANDSHAKE_TIMEOUT"]
        self.GETADDR_INTEVAL = settings["GETADDR_INTEVAL"]
        self.CONNECT_TIMEOUT=settings["CONNECT_TIMEOUT"]
        self.cmd_map = {
            b"ping": self.ping,
            b"pong": self.pong,
            b"verack": self.verack,
            b"version": self.version_rcv,
            b"getaddr": self.getaddr_request

        }


        self.recv = 0
        self.sent = 0
        self.verack = False
        self.version_rcv = False
        self.inventory_received = 0
        self.latency = 0
        self.pong = None
        self.reader = None
        self.writer = None
        self.msg_flow = None
        self.ping_pong = None
        self.ping_pong_task = None
        self.version = False
        self.services = False
        self.timestamp = False
        self.addr_recv = False
        self.addr_from = False
        self.version_nonce = False
        self.user_agent = False
        self.start_height = False
        self.relay = False
        self.raw_version = False
        self.getaddr_timestamp = 0

        self.ip = ip
        self.ips = str(ip)
        self.port = port
        self.start_time = int(time.time())
        self.own_ip = ipaddress.IPv6Address('::ffff:127.0.0.1')
        self.own_port = 8333
        self.log = logging
        self.handshake = asyncio.Future()
        asyncio.ensure_future(self._start(), loop=self.loop)
        # asyncio.ensure_future(self.test(), loop = self.loop)

    def ping(self, header_opt, checksum, data):
        data = self.MAGIC + b'pong\x00\x00\x00\x00\x00\x00\x00\x00' + header_opt[-8:] + data
        asyncio.ensure_future(self.send_msg(data))

    def pong(self, header_opt, checksum, data):
        if self.ping_pong is not None:
            if not self.ping_pong.done():
                self.ping_pong.set_result(data)

    def verack(self, header_opt, checksum, data):
        if self.handshake.done():
            return
        self.verack = True
        if self.version and self.verack:
            self.handshake.set_result(True)

    def version_rcv(self, header_opt, checksum, data):
        if self.version:
            return
        if self.version_nonce == data[72:80]:
            self.log.debug('Itself connection detected')
            self.handshake.cancel()
            return -1
        self.version = int.from_bytes(data[0:4], byteorder='little')
        if self.version < 70000:
            self.log.debug('protocol verson < 70000 reject connection')
            self.handshake.cancel()
            return -1

        self.services = int.from_bytes(data[4:12], byteorder='little')
        self.timestamp = int.from_bytes(data[12:20], byteorder='little')
        try:
            self.addr_recv = NetworkAddress.from_raw(b'0000' + data[20:46])
            self.addr_from = NetworkAddress.from_raw(b'0000' + data[46:72])
        except:
            self.log.error('protocol verson decode address error')
            self.handshake.cancel()
            return -1
        str_len, int_len = var_int(data[80:89])
        try:
            self.user_agent = data[80 + int_len:80 + int_len + str_len].decode()
        except:
            self.user_agent = ''
        self.start_height = int.from_bytes(data[80 + int_len + str_len:80 + int_len + str_len + 4], byteorder='little')
        if self.version < 70002:
            self.relay = 1
        else:
            self.relay = int.from_bytes(data[-1:], byteorder='little')
        self.raw_version = data
        if int((int(time.time()) - 1231469665) / 60 / 8.5) < self.start_height:
            self.log.error('%s start_height %s  ' % (self.ips, self.start_height))
            self.version = False
            return
        if self.handshake.done():
            return
        if self.version and self.verack:
            self.handshake.set_result(True)

    async def test(self):
        while 1:
            print(self.ips)
            await asyncio.sleep(3)
            pass


    async def ping_pong_start(self, timeout=60):
        while True:
            t = (time.time())
            self.ping_pong = asyncio.Future()
            nonce = random.randint(0, bitcoin_max_uint64).to_bytes(8, byteorder='little')
            checksum = self.checksum(nonce)
            msg = self.MAGIC + b'ping\x00\x00\x00\x00\x00\x00\x00\x00\x08\x00\x00\x00' + checksum + nonce
            await self.send_msg(msg)
            while True:
                try:
                    nonce_recieved = await asyncio.wait_for(self.ping_pong, self.PING_TIMEOUT)
                except:
                    self.log.debug('ping timeout')

                    return
                if nonce == nonce_recieved:
                    break
            self.ping_pong = None
            self.latency = int(((time.time()) - t) * 1000)

            await asyncio.sleep(timeout)

    def __del__(self):
        if self.msg_flow is not None:
            self.msg_flow.cancel()
        if self.ping_pong_task is not None:
            self.ping_pong_task.cancel()
        if self.writer is not None:
            self.writer.close()

    async def _start(self):
        self.log.debug('_start %s %s' % (self.ip, self.port))
        try:
            self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.ips, int(self.port)),
                                                              self.CONNECT_TIMEOUT)
            self.log.debugIII('2')

        except Exception as err:
            self.log.debug('exception open_connection %s' % err)
            return
        if self.writer is None:
            self.log.error('writer none')
        self.msg_flow = asyncio.ensure_future(self.get_next_message(), loop=self.loop)
        self.log.debug('handshake...')
        self.version_nonce = random.randint(0, bitcoin_max_uint64)
        msg = bitcoin_version.to_bytes(4, byteorder='little')
        msg += bitcoin_services.to_bytes(8, byteorder='little')
        msg += int(time.time()).to_bytes(8, byteorder='little')
        msg += bitcoin_services.to_bytes(8, byteorder='little')
        msg += self.ip.packed + self.port.to_bytes(2, byteorder='little')
        msg += bitcoin_services.to_bytes(8, byteorder='little')
        msg += self.own_ip.packed + self.own_port.to_bytes(2, byteorder='big')
        msg += self.version_nonce.to_bytes(8, byteorder='little')
        msg += len(bitcoin_user_agent).to_bytes(1, byteorder='little') + bitcoin_user_agent
        msg += b'\x00\x00\x00\x00\x01'
        l = len(msg)
        ch = self.checksum(msg)
        msg = b'\xF9\xBE\xB4\xD9\x76\x65\x72\x73\x69\x6F\x6E\x00\x00\x00\x00\x00' + l.to_bytes(4,
                                                                                               byteorder='little') + ch + msg

        await self.send_msg(msg)
        try:
            await asyncio.wait_for(self.handshake, timeout=self.HANDSHAKE_TIMEOUT)
        except:
            self.log.debug('Bitcoin protocol handshake error [connection closed]')

            return
        self.log.debug('handshake done.')
        self.log.debug('connected')
        self.getheaders_future = None
        self.getheaders_block_locator_hash_list = None
        self.ping_pong_task = asyncio.ensure_future(self.ping_pong_start(), loop=self.loop)

    def connection_lost(self, exc):
        self.terminate_connection()

    def data_received(self, data):
        self.reader.feed_data(data)

    def checksum(self, data):
        return double_sha256(data)[:4]




    async def get_next_message(self):
        header = b''
        while True:
            data = b''
            try:
                header += await self.reader.readexactly(1)
                if header != self.MAGIC[:len(header)]:
                    header = b''
                if header != self.MAGIC:
                    continue
                header = b''
                header_opt = await self.reader.readexactly(20)
                command, length, checksum = struct.unpack('<12sLL', header_opt)
                command = command.rstrip(b'\0')
                # command = header_opt[:12].decode().rstrip('\0')
                # length = int.from_bytes(header_opt[12:16], byteorder='little', signed=False)
                # checksum = int.from_bytes(header_opt[16:20], byteorder='little', signed=False)
                data = await self.reader.readexactly(length)
            except Exception as err:

                return
            self.log.debug("received command [%s] length [%s] " % (command, len(command)))

            self.recv += 1
            if command in self.cmd_map:
                try:
                    r = self.cmd_map[command](header_opt, checksum, data)
                    if r == -1:
                        return
                except Exception as err:
                    self.log.error('command processing error [%s] %s' % (command, err))
            else:
                self.log.debug('Unknown command %s' % command)


    def getaddr_request(self, header_opt, checksum, data):
        pass

    async def send_msg(self, data):
        try:
            self.log.debug("[%s]" % data)
            self.writer.write(data)
            await self.writer.drain()
            self.sent += 1
        except Exception as err:
            self.log.debug('\033[4mwrite error connection closed %s\033[2m' % err)


    async def getaddr(self):
        try:
            self.log.debug('getaddr')
            msg = b'\x01' + int(time.time()).to_bytes(4, byteorder='little')
            msg += bitcoin_services.to_bytes(8, byteorder='little')
            msg += self.own_ip.packed + self.own_port.to_bytes(2, byteorder='big')
            header = self.msg_header('addr', msg)
            await self.send_msg(header + msg)
            header = self.msg_header('getaddr', b'')
            await self.send_msg(header)
            self.log.debug('getaddr done')
            return True
        except Exception as err:
            self.log.error('getaddr : %s' % err)

    def msg_header(self, msg_type, data):
        checksum = self.checksum(data)
        return self.MAGIC + msg_type.encode().ljust(12, b'\x00') + len(data).to_bytes(4, byteorder='little',
                                                                                      signed=False) + checksum

