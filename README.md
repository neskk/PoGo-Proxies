# PoGo-Proxies
Proxy checker that verifies if proxies are able to connect to PokemonGo servers.

## Credits
 - Proxy testing code came mostly from [RocketMap](http://github.com/RocketMap/RocketMap).
 - Inspiration and ideas from [a-moss/Proxy Scraper for Pokemon Go](https://gist.github.com/a-moss/1578eb07b2570b5d97d85b1e93e81cc8s).

## Feature Support
 * Python 2
 * Multi-threaded proxy checker
 * HTTP and SOCKS protocols
 * Output final proxy list in several formats (e.g. KinanCity proxy format)

## Documentation
More documentation will be added soon...

## Requirements
 * Python 2
 * configargparse
 * requests
 * BeautifulSoup 4

## Usage
```
python start.py [-h] [-v] [-f PROXY_FILE] [-o OUTPUT_FILE] [-r RETRIES]
                [-t TIMEOUT] [-bf BACKOFF_FACTOR] [-mt MAX_THREADS]
                [-rw RESTART_WORK] [-ic IGNORE_COUNTRY] [--proxychains]
                [--kinan]

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Run in the verbose mode.
  -f PROXY_FILE, --proxy-file PROXY_FILE
                        Filename of proxy list to verify.
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        Output filename for working proxies.
  -r RETRIES, --retries RETRIES
                        Number of attempts to check each proxy.
  -t TIMEOUT, --timeout TIMEOUT
                        Connection timeout. Default is 5 seconds.
  -bf BACKOFF_FACTOR, --backoff-factor BACKOFF_FACTOR
                        Factor (in seconds) by which the delay until next
                        retry will increase.
  -mt MAX_THREADS, --max-threads MAX_THREADS
                        Maximum concurrent proxy testing threads.
  -rw RESTART_WORK, --restart-work RESTART_WORK
                        Restart work cycle after a period of time specified in
                        seconds. (0 to disable).
  -ic IGNORE_COUNTRY, --ignore-country IGNORE_COUNTRY
                        Ignore proxies from countries in this list.
  --proxychains         Output in proxychains-ng format.
  --kinan               Output in Kinan City format.

```

## Useful developer resources
 - [urllib3 - Session and HTTP Adapters](https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request)
