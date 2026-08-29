# S2-B v2.1 machine audit summary

- Run `33254126921`: SUCCESS
- Artifact ID `9715820206`
- Artifact ZIP SHA-256 `8445559eda0e43c072e0f92dfbea74f2eb0e0eb17621d9e089e65d647cd71d7d`
- Manifest SHA-256 `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`
- Canary: READY, 3/3 HTTP 200, no Authorization
- Actual HTTP: 90 <=230
- direct HTML: 40
- panel Jina: 21, all HTTP 422, zero 429
- Firecrawl: 10 logical calls / 26 actual HTTP due retries; 2 terminal 200, 7 terminal 500, 1 terminal 408
- Body evaluable: 21/40
- Live Sheet/article_cache/Editor writes: 0

This audit establishes execution integrity only. Source utility is determined separately by the frozen reviewed body rubric.
