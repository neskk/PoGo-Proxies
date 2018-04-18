# PoGo-Proxies

Proxy checker that verifies if proxies are able to connect to PokemonGo servers.

## Feature Support

- Multi-threaded proxy checker.
- HTTP and SOCKS protocols.
- Test proxy anonymity using an external proxy judge.
- MySQL database for keeping proxy status.
- Output final proxy list in several formats: Normal, KinanCity, RocketMap and ProxyChains.

## Requirements

**Note**: Required package versions are the same as RocketMap for compatibility.
- beautifulsoup4==4.6.0
- configargparse==0.10.0
- six==1.10.0
- peewee==2.8.1
- PySocks==1.5.6
- requests==2.18.4
- ip2location==8.0.0
- ~~jsbeautifier==1.7.5~~ Using modified [packer.py](proxytools/packer.py) from this library.

## Create database

```sql
CREATE DATABASE <dbname>;
GRANT ALL ON <dbname>.* TO '<dbuser>'@'%' IDENTIFIED BY '<dbpassword>';
```

## Usage

```
usage: start.py [-h] [-cf CONFIG] [-v] [--log-path LOG_PATH]
                [--download-path DOWNLOAD_PATH] [-pj PROXY_JUDGE] --db-name
                DB_NAME --db-user DB_USER --db-pass DB_PASS
                [--db-host DB_HOST] [--db-port DB_PORT] [-Pf PROXY_FILE] [-Ps]
                [-Pp {http,socks,all}] [-Pri PROXY_REFRESH_INTERVAL]
                [-Psi PROXY_SCAN_INTERVAL] [-Pic PROXY_IGNORE_COUNTRY]
                [-Oi OUTPUT_INTERVAL] [-Ol OUTPUT_LIMIT] [-Onp]
                [-Oh OUTPUT_HTTP] [-Os OUTPUT_SOCKS] [-Okc OUTPUT_KINANCITY]
                [-Opc OUTPUT_PROXYCHAINS] [-Orm OUTPUT_ROCKETMAP]
                [-Tr TESTER_RETRIES] [-Tbf TESTER_BACKOFF_FACTOR]
                [-Tt TESTER_TIMEOUT] [-Tmc TESTER_MAX_CONCURRENCY] [-Tda]
                [-Tni TESTER_NOTICE_INTERVAL] [-Sr SCRAPPER_RETRIES]
                [-Sbf SCRAPPER_BACKOFF_FACTOR] [-St SCRAPPER_TIMEOUT]
                [-Sp SCRAPPER_PROXY]

Args that start with '--' (eg. -v) can also be set in a config file
(config/config.ini or specified via -cf).
The recognized syntax for setting (key, value) pairs is based on the
INI and YAML formats (e.g. key=value or foo=TRUE).
If an arg is specified in more than one place, then commandline values
override config file values which override defaults.

optional arguments:
  -h, --help            show this help message and exit
  -cf CONFIG, --config CONFIG
                        Set configuration file.
  -v, --verbose         Run in the verbose mode.
  --log-path LOG_PATH   Directory where log files are saved.
  --download-path DOWNLOAD_PATH
                        Directory where download files are saved.
  -pj PROXY_JUDGE, --proxy-judge PROXY_JUDGE
                        URL for AZenv script used to test proxies.

Database:
  --db-name DB_NAME     Name of the database to be used.
  --db-user DB_USER     Username for the database.
  --db-pass DB_PASS     Password for the database.
  --db-host DB_HOST     IP or hostname for the database.
  --db-port DB_PORT     Port for the database.

Proxy Sources:
  -Pf PROXY_FILE, --proxy-file PROXY_FILE
                        Filename of proxy list to verify.
  -Ps, --proxy-scrap    Scrap webpages for proxy lists.
  -Pp {http,socks,all}, --proxy-protocol {http,socks,all}
                        Specify proxy protocol we are testing. Default: socks.
  -Pri PROXY_REFRESH_INTERVAL, --proxy-refresh-interval PROXY_REFRESH_INTERVAL
                        Refresh proxylist from configured sources every X
                        minutes. Default: 180.
  -Psi PROXY_SCAN_INTERVAL, --proxy-scan-interval PROXY_SCAN_INTERVAL
                        Scan proxies from database every X minutes.
                        Default: 60.
  -Pic PROXY_IGNORE_COUNTRY, --proxy-ignore-country PROXY_IGNORE_COUNTRY
                        Ignore proxies from countries in this list.
                        Default: ["china"]

Output:
  -Oi OUTPUT_INTERVAL, --output-interval OUTPUT_INTERVAL
                        Output working proxylist every X minutes. Default: 60.
  -Ol OUTPUT_LIMIT, --output-limit OUTPUT_LIMIT
                        Maximum number of proxies to output. Default: 100.
  -Onp, --output-no-protocol
                        Proxy URL format will not include protocol.
  -Oh OUTPUT_HTTP, --output-http OUTPUT_HTTP
                        Output filename for working HTTP proxies.
                        To disable: None/False.
  -Os OUTPUT_SOCKS, --output-socks OUTPUT_SOCKS
                        Output filename for working SOCKS proxies.
                        To disable: None/False.
  -Okc OUTPUT_KINANCITY, --output-kinancity OUTPUT_KINANCITY
                        Output filename for KinanCity proxylist.
                        Default: None (disabled).
  -Opc OUTPUT_PROXYCHAINS, --output-proxychains OUTPUT_PROXYCHAINS
                        Output filename for ProxyChains proxylist.
                        Default: None (disabled).
  -Orm OUTPUT_ROCKETMAP, --output-rocketmap OUTPUT_ROCKETMAP
                        Output filename for RocketMap proxylist.
                        Default: None (disabled).

Proxy Tester:
  -Tr TESTER_RETRIES, --tester-retries TESTER_RETRIES
                        Maximum number of web request attempts. Default: 5.
  -Tbf TESTER_BACKOFF_FACTOR, --tester-backoff-factor TESTER_BACKOFF_FACTOR
                        Time factor (in seconds) by which the delay until next
                        retry will increase. Default: 0.5.
  -Tt TESTER_TIMEOUT, --tester-timeout TESTER_TIMEOUT
                        Connection timeout in seconds. Default: 5.
  -Tmc TESTER_MAX_CONCURRENCY, --tester-max-concurrency TESTER_MAX_CONCURRENCY
                        Maximum concurrent proxy testing threads.
                        Default: 100.
  -Tda, --tester-disable-anonymity
                        Disable anonymity proxy test.
  -Tni TESTER_NOTICE_INTERVAL, --tester-notice-interval TESTER_NOTICE_INTERVAL
                        Print proxy tester statistics every X seconds.
                        Default: 60.

Proxy Scrapper:
  -Sr SCRAPPER_RETRIES, --scrapper-retries SCRAPPER_RETRIES
                        Maximum number of web request attempts. Default: 3.
  -Sbf SCRAPPER_BACKOFF_FACTOR, --scrapper-backoff-factor SCRAPPER_BACKOFF_FACTOR
                        Time factor (in seconds) by which the delay until next
                        retry will increase. Default: 0.5.
  -St SCRAPPER_TIMEOUT, --scrapper-timeout SCRAPPER_TIMEOUT
                        Connection timeout in seconds. Default: 5.
  -Sp SCRAPPER_PROXY, --scrapper-proxy SCRAPPER_PROXY
                        Use this proxy for webpage scrapping. Format:
                        <proto>://[<user>:<pass>@]<ip>:<port> Default: None.
```

## Useful developer resources

- [Python Requests](http://docs.python-requests.org/en/master/)
- [urllib3](https://urllib3.readthedocs.io/en/latest/)
- [urllib3 - set max retries](https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request)
- [Peewee 2.10.2 API Documentation](http://docs.peewee-orm.com/en/2.10.2/peewee/api.html)
- [Conversion from IP string to integer and backwards](https://stackoverflow.com/a/13294427)
- [Coerse INET_ATON](https://github.com/coleifer/peewee/issues/342)
- [ProxyChains](https://github.com/haad/proxychains)
- [IP2Location python library](https://www.ip2location.com/developers/python)


## Credits

This software includes IP2Location LITE data available from [http://lite.ip2location.com](http://lite.ip2location.com)