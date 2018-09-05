mkdir /tmp/postgres_btc_nodes
docker volume create btc_nodes_data
docker build -t postgres_btc_nodes . && \
docker run --rm  --name postgres_btc_nodes \
       -v btc_nodes_data:/var/lib/postgresql/data -v /tmp/postgres_btc_nodes:/var/run/postgresql/ \
       -it postgres_btc_nodes