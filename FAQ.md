# PoGo-Proxies - FAQ

## Developers FAQ
----
Q: Why proxy scrappers don't include protocol in proxy URL?

A: There are three types of `ProxyParser`: `MixedParser`, `HTTPParser` and
   `SOCKSParser`.
   
   `MixedParser` is for "special" scrappers that can grab proxies
   with both protocols from the same source.
   These scrappers are the exception to the rule and should indicate proxy protocol in URL (e.g. socks5://1.2.3.4).
   If they don't include protocol, the default protocol will be defined by `--proxy-protocol` - the only scrapper that does this is the `FileReader` to allow input proxylists to not include protocol, assuming that they are all the same. In short, if a source has proxies from multiple protocols, the protocol must be in proxy URL.
   
   Since most scrappers are associated with specific protocol, they will be aggregated by `HTTPParser` and `SOCKSParser` and proxy protocol is already set by default.
   These `ProxyParser` sub-classes will perform basic duplicate filtering and because of this it's best, performance wise, **not** to include
   protocol in proxy URL while scrapping.
   This may be refactored in the future but for now it's stays this way.
