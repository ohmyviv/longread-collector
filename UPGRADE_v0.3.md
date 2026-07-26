# v0.3 升级说明

本版本针对首次影子运行中“32条候选、有效文章0条”的问题进行修复。

## 核心变化

- 在抓取正文前过滤社交平台、登录页、招聘页、首页、搜索/列表页。
- 每个域名每次运行最多保留2个URL，增加来源多样性。
- 验证Markdown是否为有效文章正文；验证码、登录页不再计入成功率。
- Jina返回无作者/日期时，从正文及URL补提取。
- B级调整为：正文、标题和日期可靠，但作者字段未可靠提取。
- Jina返回长验证码页时也会触发Firecrawl回退，而不再只看字符数。
- collector_runs补充预过滤数量与原因；sources_scanned写入真实域名数。
- 自动晋级已在Google Sheet中关闭，READY后人工审核再切换。

## 主要修改文件

- `src/longread_collector/quality.py`（新增）
- `src/longread_collector/extraction.py`
- `src/longread_collector/pipeline.py`
- `config/queries.yaml`
- `tests/test_quality.py`（新增）
- `README.md`
- `pyproject.toml`
- `.github/workflows/collector.yml`

## 验证

本地测试：10 passed。
