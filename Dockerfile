FROM ubuntu:18.04
MAINTAINER Aleksey Karpov <admin@bitaps.com>
RUN apt-get update
# install python
RUN apt-get -y install python3
RUN apt-get -y install python3-pip
RUN apt-get -y install build-essential libtool autotools-dev automake pkg-config libssl-dev libevent-dev
RUN apt-get -y install libssl1.0-dev
RUN apt-get -y install git
COPY requirements.txt .
RUN pip3 install --requirement requirements.txt
WORKDIR /
COPY ./ ./
WORKDIR /scanner
ENTRYPOINT ["python3", "scanner.py"]