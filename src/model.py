import asyncpg
import time
import geoip2.database
from geoip2.errors import AddressNotFoundError
from decimal import Decimal
import traceback
from  datetime import datetime

# MaxMind databases
GEOIP_CITY = geoip2.database.Reader("../geoip/GeoLite2-City.mmdb")
GEOIP_COUNTRY = geoip2.database.Reader("../geoip/GeoLite2-Country.mmdb")
ASN = geoip2.database.Reader("../geoip/GeoLite2-ASN.mmdb")

async def create_db_model(pool):

    async with pool.acquire() as conn:
        await conn.execute(open("schema.sql", "r").read().replace("\n",""))


async def get_last_24hours_addresses(pool):
    async with pool.acquire() as conn:
        t = int(time.time()) - 60 * 60 * 24
        rows = await conn.fetch("SELECT ip, port FROM node WHERE timestamp > $1;", t)
    return rows

def get_geoip(address):
    country = None
    city = None
    geo = "0.0;0.0"
    timezone = None
    asn = None
    org = None
    try:
        gcountry = GEOIP_COUNTRY.country(address)
    except AddressNotFoundError:
        pass
    else:
        country = gcountry.country.iso_code

    try:
        gcity = GEOIP_CITY.city(address)
    except AddressNotFoundError:
        pass
    else:
        city = gcity.city.name
        if gcity.location.latitude is not None and \
                gcity.location.longitude is not None:
            lat = float(Decimal(gcity.location.latitude).quantize(Decimal('.000001')))
            lng = float(Decimal(gcity.location.longitude).quantize(Decimal('.000001')))
            geo = "%s;%s" % (lat, lng)
        timezone = gcity.location.time_zone
    try:
        asn_record = ASN.asn(address)
    except AddressNotFoundError:
        pass
    else:
        asn = 'AS{}'.format(asn_record.autonomous_system_number)
        org = asn_record.autonomous_system_organization
    return {"country": country,
            "city": city,
            "geo": geo,
            "timezone": timezone,
            "asn": asn,
            "org": org}

async def report_online(address,
                        port,
                        network_type,
                        user_agent,
                        latency,
                        version,
                        start_height,
                        services,
                        geo,
                        time, pool):
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO node as a "
                               "                 (ip, "
                               "                  port, "
                               "                  network,"
                               "                  agent,"
                               "                  latency,"
                               "                  version,"
                               "                  block_height, "
                               "                  services,"
                               "                  country,"
                               "                  city,"
                               "                  geo,"
                               "                  timestamp) "
                               "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) "
                               "ON CONFLICT(ip) "
                               "DO UPDATE "
                               "SET "
                               "port = EXCLUDED.port,"
                               "network = EXCLUDED.network,"
                               "agent = EXCLUDED.agent,"
                               "latency = EXCLUDED.latency,"
                               "version = EXCLUDED.version,"
                               "block_height = EXCLUDED.block_height,"
                               "services = EXCLUDED.services,"
                               "country = EXCLUDED.country,"
                               "city = EXCLUDED.city,"
                               "geo = EXCLUDED.geo, "
                               "timestamp = EXCLUDED.timestamp;",
                               address.encode(),
                               port,
                               network_type.encode(),
                               user_agent.encode(),
                               latency,
                               version,
                               start_height,
                               services,
                               b"" if geo["country"] is None else geo["country"].encode(),
                               b"" if geo["city"] is None else geo["city"].encode(),
                               b"" if geo["geo"] is None else geo["geo"].encode(),
                               time
                               )
            await conn.execute("INSERT  INTO node_scan_stat (ip,"
                               "                             status,"
                               "                             timestamp,"
                               "                             latency,"
                               "                             block_height,"
                               "                             services) "
                               "VALUES ($1,$2,$3,$4,$5,$6)",
                               address.encode(),
                               0,
                               time,
                               latency,
                               start_height,
                               services)

    except:
        pass


async def report_offline(address, pool):
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval("SELECT ip FROM node  WHERE ip = $1 LIMIT 1;", address.encode())
            if not row:
                return
        async with pool.acquire() as conn:
            await conn.execute("INSERT  INTO node_scan_stat (ip,"
                               "                             status,"
                               "                             timestamp,"
                               "                             latency,"
                               "                             block_height,"
                               "                             services) "
                               "VALUES ($1,$2,$3,$4,$5,$6)",
                               address.encode(),
                               1,
                               int(time.time()),
                               0,
                               0,
                               0)
    except:
        pass

async def summary(pool):
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM node "
                               "WHERE  timestamp < $1;",
                               int(time.time()) - 60 * 60 * 24)
            rows = await conn.fetch("SELECT ip,"
                                   "       network,"
                                   "       agent,"
                                   "       latency,"
                                   "       version,"
                                   "       block_height,"
                                   "       services,"
                                   "       country,"
                                   "       city,"
                                   "       geo,"
                                   "       timestamp "
                                   " FROM node;")
        total = len(rows)
        ipv4_total = 0
        ipv6_total = 0
        tor_total = 0
        agent = dict()
        country = dict()
        network = dict()
        for row in rows:
            try:
                agent[row["agent"]] += 1
            except:
                agent[row["agent"]] = 1
            try:
                country[row["country"]] += 1
            except:
                country[row["country"]] = 1
            try:
                network[row["network"]] += 1
            except:
                network[row["network"]] = 1

            if row["network"] == b"IPv4":
                ipv4_total += 1

            if row["network"] == b"IPv6":
                ipv6_total += 1

            if row["network"] == b"TOR":
                tor_total += 1

        day = int(int(time.time())//86400)
        d = datetime.fromtimestamp(int(time.time()))
        month = d.year * 12 + d.month
        async with pool.acquire() as conn:
            await conn.execute("UPDATE stat  SET "
                               "total = $1,"
                               "ipv4_total = $2,"
                               "ipv6_total = $3,"
                               "tor_total = $4;",
                               total,
                               ipv4_total,
                               ipv6_total,
                               tor_total
                               )
            await conn.executemany("INSERT INTO user_agent_stat "
                                   "as a (agent, count) "
                                   "values  ($1,$2) "
                                   "ON CONFLICT (agent) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(k,agent[k]) for k in agent])

            await conn.executemany("INSERT INTO country_stat "
                                   "as a (country, count) "
                                   "values  ($1,$2) "
                                   "ON CONFLICT (country) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(k,country[k]) for k in country])

            await conn.executemany("INSERT INTO user_agent_daily_stat "
                                   "as a (day, agent, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (agent, day) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(day, k,agent[k]) for k in agent])

            await conn.executemany("INSERT INTO country_daily_stat "
                                   "as a (day, country, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (country, day) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(day, k,country[k]) for k in country])


            await conn.executemany("INSERT INTO network_daily_stat "
                                   "as a (day, network, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (network, day) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(day, k,network[k]) for k in network])

            await conn.executemany("INSERT INTO user_agent_monthly_stat "
                                   "as a (month, agent, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (agent, month) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(month, k,agent[k]) for k in agent])

            await conn.executemany("INSERT INTO country_monthly_stat "
                                   "as a (month, country, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (country, month) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(month, k,country[k]) for k in country])

            await conn.executemany("INSERT INTO network_monthly_stat "
                                   "as a (month, network, count) "
                                   "values  ($1,$2,$3) "
                                   "ON CONFLICT (network, month) "
                                   "DO UPDATE SET count = EXCLUDED.count",
                                   [(month, k,network[k]) for k in network])



    except:
        pass