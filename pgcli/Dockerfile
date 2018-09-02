FROM python:2.7.10-slim
MAINTAINER Aleksey Karpov <admin@bitaps.com>
RUN apt-get -y update && apt-get -y install libpq-dev build-essential
RUN pip install pgcli==1.10.3
RUN mkdir /var/run/postgresql
ENTRYPOINT ["pgcli"]