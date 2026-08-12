from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from longread_collector.models import DiscoveredURL
from longread_collector.recall_instrumentation import (
    CapturedDiscovery,
    SNAPSHOT_HEADERS,
    SnapshotCaptureState,
)
from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    MEDIUM_VERSION,
    PUBLICATION_VERSION,
    SOURCE_VERSION,
    SURFACE_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION
from longread_collector.v06.shadow.snapshot_persistence_v0738 import (
    SNAPSHOT_METADATA_CHUNK_SIZE,
    SNAPSHOT_METADATA_INLINE_LIMIT,
    SNAPSHOT_OVERFLOW_HEADERS,
    SNAPSHOT_OVERFLOW_SHEET,
    SNAPSHOT_PERSISTENCE_VERSION,
    hardened_append_snapshot_rows,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260812-042957-BJT-pre_report-pr738-replay",
        group_id="pre_report",
        scheduled_at_bj="2026-08-12 03:57:00",
        started_at_bj="2026-08-12 04:29:57",
        collector_version="collector-v0.6-pr7.3.8",
    )


def _record(item_id: str, *, url: str, title: str) -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        title_hint=title,
        discovery_method="firecrawl_search",
        raw_metadata={},
    )


def _bundle(item_id: str, *, title: str, body: str) -> AcquisitionBundle:
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_wuhan_primary_document_uses_explicit_issuer_not_page_title() -> None:
    title = "市人民政府关于印发武汉市城市更新“十五五”规划的通知 - 武汉市人民政府门户网站"
    url = "https://www.wuhan.gov.cn/zwgk/xxgk/zfwj/szfwj/202608/t20260811_2832045.shtml"
    record = _record("wuhan-primary-document-pr738", url=url, title=title)
    body = (
        "## 市人民政府关于印发武汉市城市更新“十五五”规划的通知\n\n"
        "* 索引号： K28044908/2026-12878\n"
        "* 发文机构： 武汉市人民政府\n"
        "* 发文字号： 武政〔2026〕8号\n"
        "* 主题分类： 综合政务\n"
        "* 成文日期： 2026年07月13日\n"
        "* 发布日期： 2026年07月31日\n"
        "* 有效性：有效\n\n"
        "各区人民政府，市人民政府各部门：\n"
        "经研究，现将《武汉市城市更新“十五五”规划》印发给你们，请认真组织实施。\n\n"
        "武汉市人民政府\n2026年7月13日\n\n"
        + ("城市更新规划正文继续展开公共空间、基础设施和治理机制。" * 180)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source == "武汉市人民政府"
    assert article.canonical_source == "武汉市人民政府"
    assert article.original_publisher == "武汉市人民政府"
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert article.source_action is SourceAction.NONE
    assert article.canonical_content_url == url
    assert article.published_at == "2026-07-31"
    assert any(
        item.evidence_type == "document_issuer_evidence"
        and item.value == "武汉市人民政府"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_third_party_republish_with_same_document_header_is_not_made_original() -> None:
    title = "市人民政府关于印发武汉市城市更新“十五五”规划的通知"
    record = _record(
        "third-party-government-document-negative-pr738",
        url="https://policy.example/repost/wuhan-plan",
        title=title,
    )
    body = (
        f"# {title}\n\n"
        "发文机构：武汉市人民政府\n"
        "成文日期：2026年07月13日\n"
        "发布日期：2026年07月31日\n\n"
        + ("转载页面完整保留政府文件正文。" * 220)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source != "武汉市人民政府"
    assert not any(
        item.evidence_type == "document_issuer_evidence" for item in article.evidence
    )


def test_government_article_mid_body_issuer_mention_does_not_trigger() -> None:
    title = "武汉城市更新项目观察"
    record = _record(
        "government-article-issuer-negative-pr738",
        url="https://www.wuhan.gov.cn/xw/202608/example.shtml",
        title=title,
    )
    body = (
        f"# {title}\n\n记者梳理近期项目进展。\n\n"
        + ("这是连续的新闻报道和背景分析。" * 120)
        + "\n\n附件信息中提到发文机构：武汉市人民政府。\n"
        + ("报道继续采访相关项目负责人。" * 80)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert not any(
        item.evidence_type == "document_issuer_evidence" for item in article.evidence
    )


class _FakeWorksheet:
    def __init__(self, title: str, *, fail_append: bool = False) -> None:
        self.title = title
        self.rows: list[list[object]] = []
        self.fail_append = fail_append

    def append_row(self, row, value_input_option=None):
        self.rows.append(list(row))

    def append_rows(self, rows, value_input_option=None, table_range=None):
        if self.fail_append:
            raise RuntimeError(f"append failed for {self.title}")
        self.rows.extend(list(row) for row in rows)

    def row_values(self, index: int):
        if 1 <= index <= len(self.rows):
            return list(self.rows[index - 1])
        return []

    def freeze(self, rows: int) -> None:
        return None


class _FakeBook:
    def __init__(self, *, fail_overflow: bool = False, fail_main: bool = False) -> None:
        self.sheets: dict[str, _FakeWorksheet] = {}
        self.fail_overflow = fail_overflow
        self.fail_main = fail_main

    def worksheet(self, title: str):
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def add_worksheet(self, *, title: str, rows: int, cols: int):
        ws = _FakeWorksheet(
            title,
            fail_append=(
                (self.fail_overflow and title == SNAPSHOT_OVERFLOW_SHEET)
                or (self.fail_main and title == "collector_discovery_snapshot")
            ),
        )
        self.sheets[title] = ws
        return ws


class _FakeStore:
    def __init__(self, *, fail_overflow: bool = False, fail_main: bool = False) -> None:
        self.settings = SimpleNamespace(timezone="Asia/Shanghai")
        self.book = _FakeBook(fail_overflow=fail_overflow, fail_main=fail_main)


def _snapshot_state(
    *,
    description: str = "",
    query_or_source: str = "",
    metadata: dict[str, object] | None = None,
) -> SnapshotCaptureState:
    item = DiscoveredURL(
        url="https://example.com/story/oversized",
        title="Snapshot persistence fixture",
        description=description,
        discovery_method="rss",
        query_or_source=query_or_source,
        metadata=metadata or {"source_id": "fixture"},
    )
    return SnapshotCaptureState(
        query_group="pre_report",
        discoveries=[
            CapturedDiscovery(item=item, prefilter_status="accepted_for_extraction")
        ],
    )


def _reconstruct_field(store: _FakeStore, field_name: str) -> tuple[dict, str]:
    main = store.book.sheets["collector_discovery_snapshot"]
    index = SNAPSHOT_HEADERS.index(field_name)
    cell = json.loads(str(main.rows[1][index]))
    key = (
        "_snapshot_metadata_overflow"
        if field_name == "metadata_json"
        else "_snapshot_cell_overflow"
    )
    manifest = cell[key]
    overflow = store.book.sheets[SNAPSHOT_OVERFLOW_SHEET]
    rows = [row for row in overflow.rows[1:] if str(row[0]) == manifest["snapshot_id"]]
    rows.sort(key=lambda row: int(row[4]))
    return manifest, "".join(str(row[6]) for row in rows)


def test_oversized_description_is_losslessly_chunked() -> None:
    payload = "深" * (SNAPSHOT_METADATA_INLINE_LIMIT + 20_000)
    store = _FakeStore()

    written = hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-ALL-CELL-DESCRIPTION",
        pair_list=[],
        state=_snapshot_state(description=payload),
    )

    assert written == 1
    manifest, reconstructed = _reconstruct_field(store, "description")
    assert manifest["version"] == SNAPSHOT_PERSISTENCE_VERSION
    assert manifest["field"] == "description"
    assert reconstructed == payload
    assert hashlib.sha256(reconstructed.encode("utf-8")).hexdigest() == manifest["sha256"]


def test_two_identical_oversized_fields_get_distinct_cell_ids() -> None:
    payload = "x" * (SNAPSHOT_METADATA_INLINE_LIMIT + 20_000)
    store = _FakeStore()
    hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-TWO-CELLS",
        pair_list=[],
        state=_snapshot_state(description=payload, query_or_source=payload),
    )

    description_manifest, description_value = _reconstruct_field(store, "description")
    query_manifest, query_value = _reconstruct_field(store, "query_or_source")
    assert description_manifest["snapshot_id"] != query_manifest["snapshot_id"]
    assert description_manifest["row_snapshot_id"] == query_manifest["row_snapshot_id"]
    assert description_value == payload
    assert query_value == payload


def test_astral_unicode_non_metadata_cell_uses_utf16_guard() -> None:
    payload = "😀" * 30_000
    assert len(payload) < SNAPSHOT_METADATA_INLINE_LIMIT
    assert len(payload.encode("utf-16-le")) // 2 > SNAPSHOT_METADATA_INLINE_LIMIT
    store = _FakeStore()
    hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-ALL-CELL-EMOJI",
        pair_list=[],
        state=_snapshot_state(description=payload),
    )

    manifest, reconstructed = _reconstruct_field(store, "description")
    assert manifest["utf16_units"] > SNAPSHOT_METADATA_INLINE_LIMIT
    assert reconstructed == payload
    overflow = store.book.sheets[SNAPSHOT_OVERFLOW_SHEET]
    chunks = [row for row in overflow.rows[1:] if str(row[0]) == manifest["snapshot_id"]]
    assert all(len(str(row[6])) <= SNAPSHOT_METADATA_CHUNK_SIZE for row in chunks)
    assert all(len(str(row[6]).encode("utf-16-le")) // 2 <= 40_000 for row in chunks)


def test_metadata_overflow_keeps_pr735_manifest_contract_losslessly() -> None:
    metadata = {"source_id": "fixture", "payload": "界" * 60_000}
    expected = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    store = _FakeStore()
    hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-METADATA-PR738",
        pair_list=[],
        state=_snapshot_state(metadata=metadata),
    )

    manifest, reconstructed = _reconstruct_field(store, "metadata_json")
    assert manifest["field"] == "metadata_json"
    assert reconstructed == expected


def test_all_cell_overflow_failure_propagates_before_main_snapshot() -> None:
    payload = "x" * (SNAPSHOT_METADATA_INLINE_LIMIT + 20_000)
    store = _FakeStore(fail_overflow=True)

    with pytest.raises(RuntimeError, match="append failed"):
        hardened_append_snapshot_rows(
            store,
            run_id="COL-SNAPSHOT-ALL-CELL-FAIL",
            pair_list=[],
            state=_snapshot_state(description=payload),
        )

    assert "collector_discovery_snapshot" not in store.book.sheets


def test_main_failure_after_all_cell_overflow_does_not_claim_success() -> None:
    payload = "x" * (SNAPSHOT_METADATA_INLINE_LIMIT + 20_000)
    store = _FakeStore(fail_main=True)

    with pytest.raises(RuntimeError, match="collector_discovery_snapshot"):
        hardened_append_snapshot_rows(
            store,
            run_id="COL-SNAPSHOT-ALL-CELL-MAIN-FAIL",
            pair_list=[],
            state=_snapshot_state(description=payload),
        )

    assert len(store.book.sheets[SNAPSHOT_OVERFLOW_SHEET].rows) > 1
    assert store.book.sheets["collector_discovery_snapshot"].rows == [SNAPSHOT_HEADERS]


def test_pr738_versions_change_source_service_snapshot_and_runtime_only() -> None:
    from longread_collector import recall_instrumentation
    from longread_collector.v06.shadow.pipeline import (
        LEGACY_CONTROL_VERSION,
        PARALLEL_SHADOW_PIPELINE_VERSION,
    )

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.8"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.8"
    assert SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.8"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.8"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.7"
    assert SURFACE_VERSION == "canonical-surface-v0.6-pr7.3.4"
    assert MEDIUM_VERSION == "canonical-medium-v0.6-pr2"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
    assert LEGACY_CONTROL_VERSION == "collector-v0.5.6m"
    assert recall_instrumentation._append_snapshot_rows is hardened_append_snapshot_rows
