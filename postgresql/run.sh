mkdir /tmp/postgres_btc_nodes
docker build -t postgres_btc_nodes . && \
docker run --rm  --name btc_nodes_scanner \
       -v btc_nodes_data:/var/lib/postgresql/data -v /tmp/postgres_btc_nodes:/var/run/postgresql/ \
       -it postgres_btc_nodes