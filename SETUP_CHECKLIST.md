# 只需人工完成的步骤

系统代码、Google Sheet表结构、查询轮换和北京时间排程已经完成。剩余步骤涉及你的外部账户和密钥，无法由ChatGPT代为创建。

## 1. Firecrawl：创建免费API Key

1. 登录Firecrawl控制台并创建API Key。
2. 复制以 `fc-` 开头的Key。
3. 后面把它保存为GitHub Secret：`FIRECRAWL_API_KEY`。

不要把Key发到聊天中，也不要写入仓库文件。

## 2. Google Cloud：创建服务账号

1. 在Google Cloud中新建或选择一个项目。
2. 启用 **Google Sheets API** 和 **Google Drive API**。
3. 创建服务账号，例如 `longread-collector`。
4. 为服务账号创建JSON密钥并下载。
5. 打开《每日深度长文推荐 - 历史库》，把该JSON里的 `client_email` 以“编辑者”身份分享进去。

本系统只需要编辑这一张Sheet，不需要给服务账号项目级管理员权限。

## 3. GitHub：建立私有仓库

1. 新建一个空的私有仓库，例如 `longread-collector`。
2. 将本压缩包解压后的全部文件上传到仓库根目录；必须保留 `.github/workflows/collector.yml`。
3. 在仓库 **Settings → Secrets and variables → Actions** 中添加：
   - `FIRECRAWL_API_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_JSON_B64`
   - `JINA_API_KEY`（可留空，不创建也可以）
4. 将服务账号JSON编码为单行Base64：

```bash
./scripts/encode-service-account.sh /你的路径/service-account.json
```

把输出完整复制到 `GOOGLE_SERVICE_ACCOUNT_JSON_B64`。

## 4. 第一次人工测试

进入仓库 **Actions → Longread Collector → Run workflow**，选择 `pre_report`。

成功后检查Google Sheet：

- `collector_runs`出现一条 `success`；
- `article_cache`出现文章；
- `extraction_log`出现Jina解析记录；
- Firecrawl回退全天不超过3次。

## 自动排程（北京时间）

- 05:20：`pre_report`，晨报前最终补充；
- 11:50：`zh_midday`，采集中国上午发布内容；
- 17:50：`zh_evening`，采集中国下午与晚间内容；
- 23:20：`intl_early`，采集美国上午、欧洲白天和中国晚间内容。

07:35的日报可使用当日05:20，以及前一日11:50、17:50、23:20形成的缓存。GitHub计划任务偶尔可能延迟，所以晨报前一轮安排在05:20而不是临近07:35。

## 当前安全状态

`collector_config.mode=shadow`。采集器只填充缓存，不会自动替换现有日报搜索。连续运行至少3天，并同时达到以下阈值后，采集器会自动切换为缓存优先：

- 过去48小时 `eligible_for_editor` 至少18篇；
- 至少12个不同域名；
- 解析成功率至少60%；
- 连续72小时内成功完成12个轮换批次。

不需要再手工改日报任务；自动切换后若健康门失效，日报会回退原有检索。
