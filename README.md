# 每日深度长文采集器 v0.3

这是《每日深度长文推荐》的上游文章获取层：

1. **Firecrawl Search**按14个开放主题查询发现新URL，并排除社交平台、招聘页等明显非文章来源；
2. **Jina Reader**优先把公开网页转换为Markdown；
3. Jina正文不足时，**Firecrawl Scrape**作为回退，但全系统每天最多调用3次；
4. 在提取前过滤社交、登录、招聘、首页和列表页，限制单域名数量；
5. 区分“抓到Markdown”和“得到有效文章正文”，再评估A/B/C/D验证等级；
6. 将缓存、解析日志、运行状态写入现有Google Sheet；
7. 先以 `shadow` 模式运行，达到健康阈值并人工复核后再让07:35日报缓存优先。

项目只处理公开可访问页面，不绕过登录、付费墙或网站访问控制。

## 已接入的Google Sheet

目标Sheet：`1Ohi2amTCPnIZZont7rwOLO487DFk64-pemLT8O76xq4`

- `source_registry`：来源注册与解析策略；
- `article_cache`：文章正文缓存；
- `extraction_log`：每次Jina/Firecrawl解析尝试；
- `collector_runs`：采集运行和额度状态；
- `collector_queries`：14条查询、轮换组、时间、域名排除与启停开关；
- `collector_config`：影子模式、免费额度和接入日报阈值。

生产运行默认直接从 `collector_queries` 读取查询，因此日后调整搜索词和启停状态不需要重新部署代码。

## 北京时间排程

| 时间 | query group | 作用 |
|---|---|---|
| 05:20 | `pre_report` | 晨报前最终补充，覆盖美国下午/晚间及中文夜间新稿 |
| 11:50 | `zh_midday` | 采集中国上午发布的科技、医学和科学内容 |
| 17:50 | `zh_evening` | 采集中国下午的商业、政策、文化与社会长文 |
| 23:20 | `intl_early` | 采集美国上午、欧洲白天和中国晚间内容 |

07:35日报使用当日05:20以及前一日11:50、17:50、23:20产生的缓存。05:20与日报之间留出2小时15分钟，避免GitHub计划任务偶发延迟影响晨报。

GitHub Actions现在支持为schedule设置IANA时区；工作流直接使用`Asia/Shanghai`，无需人工换算UTC。

## 免费额度控制

- 每天只运行14条Search查询：4+3+3+4；
- 每条查询最多8个web结果，不同时请求web和news双结果池；
- Jina无Key时并发数为2，适配20 RPM限制；
- Firecrawl Scrape回退全系统每天最多3次，额度在Google Sheet的`extraction_log`中跨运行计数；
- URL缓存7天，重复URL刷新而不重复新增。

## 自动验证等级

等级表示正文访问与核验完整度，不表示文章质量：

- A：正文较完整，标题、作者、日期均提取到，未发现明显截断；
- B：有效完整正文、标题和日期已核验，但作者字段未能可靠自动提取；
- C：只有标题、日期、摘要或短摘录；
- D：无法形成文章级核验。

只有A/B且正文达到编辑最低长度，才标记`eligible_for_editor=TRUE`。

## 需要人工完成

账户密钥不能由ChatGPT代为创建。请按 [SETUP_CHECKLIST.md](SETUP_CHECKLIST.md) 完成：

1. 创建Firecrawl免费API Key；
2. 创建Google服务账号、下载JSON，并把Sheet分享给服务账号；
3. 创建GitHub私有仓库并上传本项目；
4. 添加GitHub Actions Secrets；
5. 手动运行一次`pre_report`完成验收。

## 本地运行

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install .

# 只检查Sheet、查询组和凭据文件
longread-collector doctor

# 额外实际调用一次Jina和Firecrawl
longread-collector doctor --test-remote

# 从Google Sheet读取并运行一个组
longread-collector collect --group pre_report

# 本地YAML回退
longread-collector collect --group pre_report --query-file config/queries.yaml
```

## 影子运行转正式接入

当前`collector_config.mode=shadow`，不会改变原日报检索。连续运行至少3天，且同时达到：

- 过去48小时可供编辑文章不少于18篇；
- 至少12个独立域名；
- 解析成功率不少于60%。

达到后先人工抽查候选质量，再手动把 `collector_config.mode` 从 `shadow` 切换为 `cache_primary`。日报随后按安全门执行：

```text
article_cache优先 → 原生搜索补缺 → 最终原文复核
```

健康门要求连续72小时内12次成功轮换、过去48小时至少18篇可编辑文章、至少12个域名且有效正文成功率不少于60%。即使切换后健康门暂时失效，日报也会自动回退原生检索。在此之前，原日报完全按现有流程运行。
