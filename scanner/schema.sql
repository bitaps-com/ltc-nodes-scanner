
CREATE TABLE IF NOT EXISTS node(
                                ip BYTEA  PRIMARY KEY,
                                port INT4 NOT NULL,
                                network BYTEA,
                                agent BYTEA NOT NULL,
                                latency INT4,
                                version INT4,
                                block_height INT4,
                                services INT4,
                                country BYTEA,
                                city BYTEA,
                                geo BYTEA,
                                timestamp INT4);

CREATE  INDEX IF NOT EXISTS node_time ON node  USING BTREE (timestamp DESC);
CREATE  INDEX IF NOT EXISTS node_ip ON node  USING BTREE (ip);


CREATE TABLE IF NOT EXISTS stat(
                                total BIGINT DEFAULT 0,
                                ipv4_total BIGINT DEFAULT 0,
                                ipv6_total BIGINT DEFAULT 0,
                                tor_total BIGINT DEFAULT 0);
INSERT INTO stat (
                  total,
                  ipv4_total,
                  ipv6_total,
                  tor_total)
VALUES (0,0,0,0);

CREATE TABLE IF NOT EXISTS user_agent_stat(
                                agent BYTEA  PRIMARY KEY,
                                count BIGINT DEFAULT 0);

CREATE TABLE IF NOT EXISTS country_stat(
                                country BYTEA  PRIMARY KEY,
                                count BIGINT DEFAULT 0);


CREATE TABLE IF NOT EXISTS user_agent_daily_stat(
                                agent BYTEA  NOT NULL,
                                day SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (agent, day));

CREATE TABLE IF NOT EXISTS user_agent_monthly_stat(
                                agent BYTEA  NOT NULL,
                                month SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (agent, month));

CREATE TABLE IF NOT EXISTS country_daily_stat(
                                country BYTEA  NOT NULL,
                                day SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (country, day));

CREATE TABLE IF NOT EXISTS country_monthly_stat(
                                country BYTEA  NOT NULL,
                                month SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (country, month));

CREATE TABLE IF NOT EXISTS network_daily_stat(
                                network BYTEA  NOT NULL,
                                day SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (network, day));

CREATE TABLE IF NOT EXISTS network_monthly_stat(
                                network BYTEA  NOT NULL,
                                month SMALLINT NOT NULL,
                                count BIGINT DEFAULT 0,
                                PRIMARY KEY (network, month));

CREATE TABLE IF NOT EXISTS node_scan_stat(
                                ip BYTEA,
                                status SMALLINT DEFAULT 0,
                                timestamp INT4,
                                latency INT4,
                                block_height INT4,
                                services INT4);