from scanner import model

EVENT_SEE_NODE = 1
EVENT_ASK_NODE = 2


async def event_nodes_handler(self):

    events_list = await model.get_events_nodes(self.db_pool)

    if events_list:
        nodes = {}
        id_list=[]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for event in events_list:
                    id_list.append(event["id"])
                    if event['ip'] not in nodes:
                        nodes[event['ip']] = {"port": nodes[event['port']], "last_seen_timestamp": None, "last_ask_timestamp": None}
                    if event['event'] == EVENT_SEE_NODE:
                        if not nodes[event['ip']]['last_seen_timestamp']:
                            nodes[event['ip']]['last_seen_timestamp']=event['last_timestamp']
                        else:
                            if event['last_timestamp']>nodes[event['ip']]['last_seen_timestamp']:
                                nodes[event['ip']]['last_seen_timestamp'] = event['last_timestamp']
                    elif event['event'] == EVENT_ASK_NODE:
                        if not nodes[event['ip']]['last_ask_timestamp']:
                            nodes[event['ip']]['last_ask_timestamp']=event['last_timestamp']
                        else:
                            if event['last_timestamp']>nodes[event['ip']]['last_ask_timestamp']:
                                nodes[event['ip']]['last_ask_timestamp'] = event['last_timestamp']
                nodes_list=[]
                for ip in nodes:
                    nodes_list.append([
                        ip,
                        nodes[ip]['port'],
                        nodes[ip]['last_seen_timestamp'],
                        nodes[ip]['last_ask_timestamp']])

                await model.update_nodes(conn, nodes_list)
                await model.delete_events_nodes(conn, id_list)


