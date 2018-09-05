docker build -t btc_nodes_pgcli . && docker run  --rm --name btc_nodes_pgcli \
 -v /tmp/postgres_btc_nodes:/var/run/postgresql  -it btc_nodes_pgcli postgres://postgres:test@/btc_nodes
