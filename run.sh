docker build -t btc_nodes_scanner . && docker run --rm --name btc_nodes \
 -v /tmp/postgres_btc_nodes:/var/run/postgresql --net=host  -it btc_nodes_scanner -vvvv
