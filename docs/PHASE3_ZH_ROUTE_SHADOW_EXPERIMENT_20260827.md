# Phase 3 Chinese Shadow Route Experiment — 2026-08-27

Status: **offline / Shadow only**. This document does not authorize a production `source_registry` or route change.

## Objective

Test whether richer first-party listing surfaces can improve **realized/measurable Chinese coverage** without paying for a large increase in low-value extraction. A route is not considered good merely because it returns URLs.

Common acceptance dimensions:

1. known-Final-miss recovery;
2. publication timestamp observability;
3. high-value editorial yield;
4. micro-market / notice / flow noise rate;
5. metadata requests and downstream extraction cost;
6. maintenance complexity and surface identity stability.

Primary decision objective: **high-cognitive-value recovery per incremental cost**.

## Frozen evidence from the 2026-08-21 through 2026-08-26 forensic window

### 第一财经 (Yicai)

Current configured sitemap repeatedly returns 404 and effective discovery degrades to a shallow homepage scan with weak timestamp observability.

Promising first-party Shadow surfaces:

- `https://www.yicai.com/news/`
- `https://www.yicai.com/news/kechuang`
- `https://www.yicai.com/news/jinrong/`

Observed known-Final recovery on first-party listings included `阿里拟配股800亿港元，AI“吞金兽”考验大厂钱袋子`, `C端烧钱数十亿后，互联网大厂为何集体转向AI办公？`, and `当过歌手，干过银行，他花了25年在澳门做戏剧`. Article pages exposed minute/second-level publication times for multiple misses in the window.

Negative control: `https://www.yicai.com/news/info/` was dominated by stock notices / market-flow snippets and should not be treated as the preferred longread surface despite high freshness.

### 经济观察报 (EEO)

Current homepage-only scan is shallow and largely undated. Root RSS is a useful negative control but was dominated by stock/ETF-flow snippets; some category feeds were stale.

Promising Shadow surfaces:

- `https://www.eeo.com.cn/shangyechanye/`
- current first-party author/department pages, including `https://space.eeo.com.cn/liuxiaonuo`

First-party article pages provide exact publication clocks for known misses such as `东航率先松绑“退改签” 其他航司会跟进吗`, `牵手山徳士，复宏汉霖生物类似药打包出海`, and `半年800亿美元买管线，多家跨国药企称BD已非必需`.

Author pages are an experiment surface, **not** a recommendation to hard-code a production author roster.

### 财新 (Caixin)

The configured sitemap/section path is not a stable deterministic native route in the observed runs.

Promising first-party channel surfaces:

- `https://www.caixin.com/latestnews/`
- `https://companies.caixin.com/news/`
- `https://china.caixin.com/news/`
- `https://finance.caixin.com/news`

The companies channel directly recovered the known Final miss `国产闪存龙头长存控股科创板IPO获受理 拟募资330亿元`.

`商圈` / Deepview is a distinct product surface (`https://deepview.caixin.com/topic/BQ02.000007864.html`) and must not be silently counted as covered by generic Caixin news routes.

### 界面新闻 (Jiemian)

Current v0.5.6 effective route scope is `investment|markets|macro|finance_tag|depth`. That scope is transport-healthy but incomplete for Daily Longread content space.

Promising first-party Shadow surfaces:

- `https://www.jiemian.com/lists/472.html` — 医药
- `https://www.jiemian.com/lists/854.html` — 健康
- `https://www.jiemian.com/lists/441.html` — 健康面

The 医药 listing directly contained the corrected-denominator clean miss `首个国产基因疗法的商业困局：打五折仍零处方` with a displayed publication time of `2026/08/25 09:28`. This is direct evidence of a **route-scope omission**, not a generic transport failure.

## Current interpretation

The evidence is already strong enough to reject two simplistic approaches:

- **Do not equate source scanned with source covered.** A healthy route can still cover the wrong editorial surface.
- **Do not maximize raw URL count.** Yicai `info` and EEO root RSS demonstrate that freshness/breadth can increase micro-flow noise faster than cognitive-value yield.

Highest-priority next natural Shadow validation:

1. Jiemian medicine/health routes — strongest known-miss recovery with low apparent noise.
2. Caixin deterministic channel listings — companies channel already proves one known-miss recovery.
3. Yicai broad `/news` plus selected topical sections — promising timestamps and multiple known-miss recoveries; keep `info` as noise control.
4. EEO department/author surfaces — potentially useful but needs broader denominator validation before any stable roster decision.

No production route change is authorized by this experiment alone. Promotion remains `NOT_READY`; `v06_primary`, 07:35 Editor connection, production `article_cache` consumption and automatic promotion remain disabled.
