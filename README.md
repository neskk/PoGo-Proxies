# PoGo-Proxies
Proxy checker that verifies if proxies are able to connect to PokemonGo servers.

## Credits
Most work was grabbed from RocketMap (http://github.com/RocketMap/RocketMap).

## Feature Support
 * Python 2
 * Multi-threaded proxy checker
 * HTTP and SOCKS protocols
 * Output final proxy list in several formats (e.g. KinanCity proxy format)

## Documentation
More documentation soon...

## Requirements
 * Python 2
 * configargparse
 * requests
 * BeautifulSoup 4

## Usage
```
proxy_tester.py [-h] [-v] -f PROXY_FILE [-o OUTPUT_FILE] [-r RETRIES]
                [-t TIMEOUT] [-bf BACKOFF_FACTOR] [-mt MAX_THREADS]
                [--proxychains] [--kinan]

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
  --proxychains         Output in proxychains-ng format.
  --kinan               Output in Kinan City format.
```
