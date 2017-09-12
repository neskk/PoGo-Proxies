# PoGo-Proxies
Proxy checker that verifies if proxies are able to connect to PokemonGo servers.

## Credits
 - Proxy testing code came mostly from [RocketMap](http://github.com/RocketMap/RocketMap).
 - Inspiration and ideas from [a-moss/Proxy Scraper for Pokemon Go](https://gist.github.com/a-moss/1578eb07b2570b5d97d85b1e93e81cc8s).

## Feature Support
 * Python 2
 * Multi-threaded proxy checker
 * HTTP and SOCKS protocols
 * Test if proxies are anonimous
 * Output final proxy list in several formats

## Documentation
More documentation will be added soon...

## Requirements
 * Python 2
 * configargparse
 * requests
 * urllib3
 * BeautifulSoup 4

## Usage
```
python start.py [-h] [-v] (-f PROXY_FILE | -s) [-m {http,socks}]
                [-o OUTPUT_FILE] [-r RETRIES] [-t TIMEOUT] [-pj PROXY_JUDGE]
                [-na] [-nt | -er] [-bf BACKOFF_FACTOR] [-mc MAX_CONCURRENCY]
                [-bs BATCH_SIZE] [-l LIMIT] [-ic IGNORE_COUNTRY]
                [--proxychains | --kinancity | --clean]

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Run in the verbose mode.
  -f PROXY_FILE, --proxy-file PROXY_FILE
                        Filename of proxy list to verify.
  -s, --scrap           Scrap webpages for proxy lists.
  -m {http,socks}, --mode {http,socks}
                        Specify which proxy mode to use for testing. Default
                        is "socks".
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        Output filename for working proxies.
  -r RETRIES, --retries RETRIES
                        Number of attempts to check each proxy.
  -t TIMEOUT, --timeout TIMEOUT
                        Connection timeout. Default is 5 seconds.
  -pj PROXY_JUDGE, --proxy-judge PROXY_JUDGE
                        URL for AZenv script used to test proxies.
  -na, --no-anonymous   Disable anonymous proxy test.
  -nt, --no-test        Disable PTC/Niantic proxy test.
  -er, --extra-request  Make an extra request to validate PTC.
  -bf BACKOFF_FACTOR, --backoff-factor BACKOFF_FACTOR
                        Factor (in seconds) by which the delay until next
                        retry will increase.
  -mc MAX_CONCURRENCY, --max-concurrency MAX_CONCURRENCY
                        Maximum concurrent proxy testing requests.
  -bs BATCH_SIZE, --batch-size BATCH_SIZE
                        Check proxies in batches of limited size.
  -l LIMIT, --limit LIMIT
                        Stop tests when we have enough good proxies.
  -ic IGNORE_COUNTRY, --ignore-country IGNORE_COUNTRY
                        Ignore proxies from countries in this list.
  --proxychains         Output in proxychains-ng format.
  --kinancity           Output in Kinan City format.
  --clean               Output proxy list without protocol.
```

## Useful developer resources
 - [urllib3 - Session and HTTP Adapters](https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request)
 - [High-performance python async requests](https://iliauk.com/2016/03/07/high-performance-python-sessions-async-multi-tasking/)
