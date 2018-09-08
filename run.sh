docker build -t btc_nodes_scanner . && docker run --rm --name btc_nodes \
 -v /tmp/postgres_btc_nodes:/var/run/postgresql --memory-swap -1 --net=host  -it btc_nodes_scanner -vvvv
