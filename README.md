# 每日深度长文采集器 v0.4

这是《每日深度长文推荐》的上游发现、提取和候选处理层。v0.4仍处于 `shadow` 阶段，不会自动替代07:35日报的原生检索。

核心流程：

1. 从 `source_registry` 轮换扫描优质来源，同时保留开放网络主题检索；
2. 在提取前把结果区分为独立内容、原始来源追索线索和无内容页面；
3. Jina Reader优先抓取公开正文，正文不足时有限使用Firecrawl Scrape；
4. A/B/C/D仅表示提取和元数据核验完整度，不表示编辑质量；
5. 对正文执行页面类型、内容类型、来源关系和重复簇分类；
6. 输出正式候选、特殊候选、需要追溯原始来源或淘汰四种处置；
7. 将v0.3技术放行结果与v0.4语义处置同时写入影子A/B日志；
8. 只有技术健康、金标准质量和连续影子验证全部通过后，才允许人工评估 `cache_primary`。

项目只处理公开可访问页面，不绕过登录、付费墙或网站访问控制。

## 为什么升级到v0.4

v0.3解决了“能否发现页面和抓到正文”的问题，但把A/B正文验证近似当成编辑候选资格。48篇人工金标准复核显示，原先16篇 `eligible_for_editor=TRUE` 中只有8篇仍具有正式、特殊或来源追索价值。

因此v0.4在技术提取和日报编辑之间增加语义候选处理层：

```text
发现URL
→ 页面角色
→ 正文提取与A/B/C/D验证
→ 内容类型与来源链
→ 内容级去重
→ 四出口候选处置
```

`eligible_for_editor`暂时保留用于兼容，但现在只由以下条件派生：

```text
candidate_disposition == formal_candidate
```

## 四种候选处置

- `formal_candidate`：可进入日报正常评分池；
- `special_candidate`：学术论文、政策原文等进入独立特殊池；
- `original_source_required`：当前页面只作为线索，必须追索原始文章、演讲、报告或文件；
- `reject`：不进入日报候选。

社交页面不是正式候选，但当标题和摘要明确指向可信调查或政策文件时，可以保留为 `discovery_lead`，而不是无条件丢弃。

## 来源和去重

v0.4明确区分：

- `hosting_source`：当前网页宿主；
- `canonical_source`：当前解析出的最佳编辑来源；
- `original_publisher`：原始发布者；
- `wire_service`：AP、Reuters等通讯社；
- `source_relationship`：原创、翻译转载、通讯社转载、二次转载或不确定。

去重不再仅依赖URL，还保存正文指纹、通讯社关系、翻译关系和 `content_cluster_id`。48篇金标准中的第21、46、48篇必须归入同一个AP跨站稿件簇。

## 已接入的Google Sheet

目标Sheet：`1Ohi2amTCPnIZZont7rwOLO487DFk64-pemLT8O76xq4`

- `source_registry`：定向来源注册与轮换扫描；
- `article_cache`：正文缓存和v0.4语义字段；
- `extraction_log`：每次Jina/Firecrawl提取尝试；
- `collector_runs`：采集运行和额度状态；
- `collector_queries`：开放网络查询组；
- `collector_config`：版本、影子模式和晋级阈值；
- `collector_health`：技术门、编辑门和最终晋级门；
- `collector_ground_truth`：固定48篇人工金标准，只用于回归和版本评测；
- `collector_evaluations`：每次金标准评测结果；
- `collector_shadow_ab`：v0.3与v0.4逐运行影子比较。

固定金标准不会注入每日候选，也不会由07:35任务每天复演。

## 北京时间排程

| 时间 | query group | 作用 |
|---|---|---|
| 05:20 | `pre_report` | 晨报前最终补充 |
| 11:50 | `zh_midday` | 中国上午发布内容 |
| 17:50 | `zh_evening` | 中国下午发布内容 |
| 23:20 | `intl_early` | 美国上午、欧洲白天和中国晚间内容 |

工作流使用 `Asia/Shanghai`。每轮在原查询之外最多轮换3个同语言的 `source_registry` 来源，避免定向扫描无限增加检索成本。

## 免费额度控制

- 开放网络查询继续按既有四组轮换；
- 每轮定向来源扫描最多3个来源、每个最多4个结果；
- Jina无Key时并发数为2；
- Firecrawl Scrape回退全系统每天最多3次；
- URL缓存7天，重复URL刷新而不重复新增。

## 自动验证等级

A/B/C/D只表示正文访问与元数据核验完整度：

- A：完整正文，标题、作者和日期较完整；
- B：完整正文、标题和日期可核验，作者缺失；
- C：正文或元数据不完整；
- D：无法形成文章级核验。

等级不再直接决定编辑资格。

## 本地运行

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install .

# 检查Sheet、查询组、定向来源和凭据
longread-collector doctor

# 额外调用一次Jina和Firecrawl
longread-collector doctor --test-remote

# 运行一个采集组；仍写入shadow数据
longread-collector collect --group pre_report

# 测试单个URL并查看完整语义处置
longread-collector extract "https://example.com/article"

# 手动运行固定48篇版本评测
longread-collector evaluate-ground-truth
```

金标准评测命令不属于定时采集工作流，只在发布评审时显式运行。

## 三道健康门

### 1. Transport gate

证明调度、搜索、提取、缓存和基础数量正常。

### 2. Editorial gate

至少满足：

- 48篇总体处置准确率不低于85%；
- 非淘汰候选精度不低于85%；
- 7个来源追索样本至少识别6个；
- 招聘、登录、首页、频道和垃圾页进入正式候选的数量为0；
- 第21、46、48篇AP稿件同簇准确率为100%；
- v0.4合并后至少连续3天影子A/B。

### 3. Promotion gate

只有技术门和编辑门都为READY，且人工审查影子样本后，才允许考虑切换。

当前规则仍是：

```text
collector_config.mode = shadow
auto_promote_when_ready = FALSE
promotion_gate = SHADOW
```

即使本分支的测试通过，也不意味着可以立即修改07:35自动化或切换 `cache_primary`。正确顺序是先合并并积累真实影子证据，再适配下游自动化，最后才讨论晋级。

完整接口和发布条件见 [docs/V0.4_SPEC.md](docs/V0.4_SPEC.md)。
