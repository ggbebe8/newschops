# Only feed metadata is retained. Body/AI/paper rights are not inferred from HTTP access.
SOURCES = [
    ("donga", "동아일보", "donga.com", "https://rss.donga.com/total.xml"),
    (
        "chosun",
        "조선일보",
        "chosun.com",
        "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",
    ),
    ("seoul", "서울신문", "seoul.co.kr", "https://www.seoul.co.kr/xml/rss/rss_top.xml"),
    ("hani", "한겨레", "hani.co.kr", "https://www.hani.co.kr/rss/"),
    (
        "khan",
        "경향신문",
        "khan.co.kr",
        "https://www.khan.co.kr/rss/rssdata/total_news.xml",
    ),
    (
        "segye",
        "세계일보",
        "segye.com",
        "https://www.segye.com/Articles/RSSList/segye_recent.xml",
    ),
    ("yna", "연합뉴스", "yna.co.kr", "https://www.yna.co.kr/rss/news.xml"),
    (
        "sbs",
        "SBS",
        "sbs.co.kr",
        "https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER",
    ),
    ("mk", "매일경제", "mk.co.kr", "https://www.mk.co.kr/rss/30000001/"),
    ("hankyung", "한국경제", "hankyung.com", "https://www.hankyung.com/feed/all-news"),
]
