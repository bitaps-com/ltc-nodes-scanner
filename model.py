import asyncpg
import time

async def create_db_model(conn,log):
    await conn.execute("""
                            CREATE TABLE IF NOT EXISTS nodes(
                              id BIGSERIAL    PRIMARY KEY,
                              ip inet NOT NULL,
                              last_seen_timestamp INT4,
                              last_ask_timestamp INT4);""")


    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS nodes_timestamp "
                       "ON nodes USING BTREE (last_seen_timestamp, last_ask_timestamp);")

    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS nodes_ip "
                       "ON nodes USING BTREE (ip);")

    await conn.execute("""
                            CREATE TABLE IF NOT EXISTS nodes_events(
                              id BIGSERIAL    PRIMARY KEY,
                              event INT4 NOT NULL,
                              ip inet NOT NULL,
                              last_timestamp INT4);""")


async def get_known_nodes(pool):
    async with pool.acquire() as conn:
        result= await conn.fetch("SELECT ip FROM nodes WHERE last_seen_timestamp>$1 ORDER BY last_ask_timestamp LIMIT 100", int(time.time())-3*3600)
        return result

async def get_all_known_nodes(pool):
    async with pool.acquire() as conn:
        result= await conn.fetch("SELECT ip FROM nodes WHERE last_seen_timestamp>$1", int(time.time())-3*3600)
        return result

async def update_nodes(pool,nodes_list):
    async with pool.acquire() as conn:
        await conn.executemany("INSERT INTO nodes as a (ip, last_seen_timestamp,last_ask_timestamp) VALUES ($1,$2,$3) ON DUPLICATE (ip) DO UPDATE SET last_seen_timestamp=COALESCE($2,a.last_seen_timestamp), COALESCE($3,a.last_ask_timestam)", nodes_list)

async def insert_events_nodes(pool,events_list):
    async with pool.acquire() as conn:
        await conn.executemany("INSERT INTO nodes_events (event,ip, last_timestamp) VALUES ($1,$2,now())", events_list)

async def get_events_nodes(pool):
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT id, event,ip, last_timestamp FROM nodes_events")
        return result

async def delete_events_nodes(pool, id_list):
    async with pool.acquire() as conn:
        await conn.fetch("DELETE FROM nodes_events WHERE id=ANY($1)", id_list)
