FROM ubuntu:18.04
MAINTAINER Aleksey Karpov <admin@bitaps.com>
RUN apt-get update
# install python
RUN apt-get -y install python3
RUN apt-get -y install python3-pip
RUN apt-get -y install build-essential libtool autotools-dev automake pkg-config libssl-dev libevent-dev
RUN apt-get -y install libssl1.0-dev
RUN apt-get -y install git
RUN apt-get -y install tor
COPY requirements.txt .
RUN pip3 install --requirement requirements.txt
WORKDIR /
COPY ./ ./
RUN cd /geoip;tar --strip-components=1 -zxf GeoLite2-City.tar.gz; rm GeoLite2-City.tar.gz
RUN cd /geoip;tar --strip-components=1 -zxf GeoLite2-ASN.tar.gz; rm GeoLite2-ASN.tar.gz
RUN cd /geoip;tar --strip-components=1 -zxf GeoLite2-Country.tar.gz; rm GeoLite2-Country.tar.gz

WORKDIR /src
ENTRYPOINT service tor restart && python3 main.py -v