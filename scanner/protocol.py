
import ipaddress
import time
import asyncio
import random
import struct
from pybtc import *





class BitcoinProtocol():
    def __init__(self, ip, port, settings,logging, loop, address_handler=None):
        self.MAGIC = settings["MAGIC"]
        self.PING_TIMEOUT = settings["PING_TIMEOUT"]
        self.HANDSHAKE_TIMEOUT = settings["HANDSHAKE_TIMEOUT"]
        self.GETADDR_INTEVAL = settings["GETADDR_INTEVAL"]
        self.CONNECT_TIMEOUT=settings["CONNECT_TIMEOUT"]
        self.PROTOCOL_VERSION=settings['PROTOCOL_VERSION']
        self.SERVICES=settings['SERVICES']
        self.USER_AGENT=settings['USER_AGENT']
        self.MAX_UINT64=settings['MAX_UINT64']

        self.cmd_map = {
            b"ping": self.ping,
            b"pong": self.pong,
            b"verack": self.verack,
            b"version": self.version_rcv,
            b"getaddr": self.getaddr_request,
            b"addr": self.address

        }

        self.address_handler=address_handler
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
        self.loop=loop
        self.height=530000
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
        # try:
        #     self.addr_recv = NetworkAddress.from_raw(b'0000' + data[20:46])
        #     self.addr_from = NetworkAddress.from_raw(b'0000' + data[46:72])
        # except:
        #     self.log.error('protocol verson decode address error')
        #     self.handshake.cancel()
        #     return -1
        int_len=get_var_int_len(data[80:89])
        str_len=bytes_to_int(data[80:89][1:int_len], byteorder='little')
        #str_len, int_len = var_int(data[80:89])
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
            nonce = random.randint(0, self.MAX_UINT64).to_bytes(8, byteorder='little')
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
        except Exception as err:
            self.log.debug('exception open_connection %s' % err)
            return
        if self.writer is None:
            self.log.error('writer none')
        self.msg_flow = asyncio.ensure_future(self.get_next_message(), loop=self.loop)
        self.log.debug('handshake...')
        self.version_nonce = random.randint(0, self.MAX_UINT64)
        self.log.warning(self.version_nonce)
        msg = self.PROTOCOL_VERSION.to_bytes(4, byteorder='little')
        self.log.warning(self.PROTOCOL_VERSION.to_bytes(4, byteorder='little'))

        msg += self.SERVICES.to_bytes(8, byteorder='little')
        self.log.warning(self.SERVICES.to_bytes(8, byteorder='little'))

        msg += int(time.time()).to_bytes(8, byteorder='little')
        self.log.warning(int(time.time()).to_bytes(8, byteorder='little'))

        msg += self.SERVICES.to_bytes(8, byteorder='little')
        self.log.warning(self.SERVICES.to_bytes(8, byteorder='little'))

        msg += self.ip.packed + self.port.to_bytes(2, byteorder='little')
        self.log.warning(self.ip.packed + self.port.to_bytes(2, byteorder='little'))
        msg += self.SERVICES.to_bytes(8, byteorder='little')
        self.log.warning(self.SERVICES.to_bytes(8, byteorder='little'))
        msg += self.own_ip.packed + self.own_port.to_bytes(2, byteorder='little')
        self.log.warning(self.own_ip.packed + self.own_port.to_bytes(2, byteorder='little'))
        msg += self.version_nonce.to_bytes(8, byteorder='little')
        self.log.warning(self.version_nonce.to_bytes(8, byteorder='little'))
        msg += len(self.USER_AGENT).to_bytes(1, byteorder='little') + self.USER_AGENT.encode('utf-8')
        msg += self.height.to_bytes(4, byteorder='little')
        self.log.warning(self.height.to_bytes(4, byteorder='little'))
        relay = 1
        msg +=relay.to_bytes(1, byteorder='little')
        l = len(msg)
        ch = self.checksum(msg)
        msg = b'\xF9\xBE\xB4\xD9\x76\x65\x72\x73\x69\x6F\x6E\x00\x00\x00\x00\x00' + l.to_bytes(4,
                                                                                               byteorder='little') + ch + msg

        self.log.debug(msg)
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



    def serialize_string(self, data):
        length = len(data)
        if length < 0xFD:
            return chr(length) + data
        elif length <= 0xFFFF:
            return chr(0xFD) + struct.pack("<H", length) + data
        elif length <= 0xFFFFFFFF:
            return chr(0xFE) + struct.pack("<I", length) + data
        return chr(0xFF) + struct.pack("<Q", length) + data

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
        self.log.warning('getaddr request from %s'% self.ips)
        t = int(time.time())
        if (t - self.getaddr_timestamp) < self.GETADDR_INTEVAL:
            self.log.error('getaddr rejected timeout %s' %self.ips)
            return
        self.getaddr_timestamp = t

        msg = b'\x01' + int(time.time()).to_bytes(4, byteorder='little')
        msg += self.SERVICES.to_bytes(8, byteorder='little')
        msg += self.own_ip.packed + self.own_port.to_bytes(2, byteorder='big')
        header = self.msg_header('addr', msg)
        asyncio.ensure_future(self.send_msg(header + msg), loop = self.loop)
        self.log.warning('getaddr reply sent to %s'% self.ips)


    async def send_msg(self, data):
        try:
            self.log.debug("[%s]" % data)
            self.writer.write(data)
            await self.writer.drain()
            self.sent += 1
        except Exception as err:
            self.log.debug('\033[4mwrite error connection closed %s\033[2m' % err)


    def address(self, header_opt, checksum, data):
        offset=get_var_int_len(data)
        count=bytes_to_int(data[1:offset], byteorder='little')
        #count, offset = var_int(data)
        if count:
            if len(data) != (offset + 30* count):
                self.log.debugI('incorrect message to push_raw_addresses')
                return
        if self.address_handler:
            self.loop.create_task(self.address_handler(data, self.ip, self.port))
        return


    async def getaddr(self):
        try:
            self.log.debug('start to send getaddr request')
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

