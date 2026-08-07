from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from longread_collector.v06.contracts import (
    DiscoveryRecord,
    Evidence,
    FlowStatus,
    GateAction,
    StageEventType,
    StageName,
    TechnicalStatus,
)
from longread_collector.v06.gates import (
    AcquisitionGateService,
    GateContext,
    evaluate_gate_replay,
)

BJ = ZoneInfo("Asia/Shanghai")


def _record(
    *,
    item_id: str,
    url: str,
    title: str = "",
    description: str = "",
    date_values: tuple[tuple[str, float], ...] = (),
    metadata: dict | None = None,
) -> DiscoveryRecord:
    evidence = tuple(
        Evidence(
            evidence_id=f"{item_id}-date-{index}",
            evidence_type="publication_hint",
            source_stage=StageName.DISCOVERY,
            field="published_at_hint",
            value=value,
            confidence=confidence,
            extractor="fixture",
        )
        for index, (value, confidence) in enumerate(date_values, start=1)
    )
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id="run-pr6",
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        canonical_url_hint=url,
        title_hint=title,
        description_hint=description,
        published_at_hints=tuple(value for value, _ in date_values),
        source_id="fixture",
        discovery_method="fixture",
        query_or_section="fixture",
        rank=1,
        route_status=TechnicalStatus.SUCCESS,
        raw_metadata=metadata or {},
        evidence=evidence,
    )


def _context(**kwargs) -> GateContext:
    values = {
        "now_bj": datetime(2026, 8, 7, 12, 0, tzinfo=BJ),
        "ordinary_max_age_days": 14,
    }
    values.update(kwargs)
    return GateContext(**values)


def _action(record: DiscoveryRecord, context: GateContext | None = None):
    return AcquisitionGateService().decide(record, context or _context())


@pytest.mark.parametrize(
    ("item_id", "url", "title", "reason"),
    [
        ("invalid", "ftp://example.com/file", "File", "invalid_web_url"),
        ("home", "https://example.com/", "Example", "homepage_root"),
        ("login", "https://example.com/login", "Sign in", "authentication_or_captcha_route"),
        ("search", "https://example.com/search?q=ai", "Search", "search_index_route"),
        ("tag", "https://example.com/tag/ai", "AI", "category_tag_topic_index_route"),
        ("career", "https://example.com/careers/researcher", "Jobs", "job_or_career_route"),
    ],
)
def test_only_explicit_structural_routes_are_deterministic_hard_rejects(
    item_id, url, title, reason
):
    run = _action(_record(item_id=item_id, url=url, title=title))
    assert run.decision.action is GateAction.HARD_REJECT
    assert run.decision.reason_code == reason
    assert run.event.event_type is StageEventType.GATE_RESULT
    assert run.event.flow_status is FlowStatus.REJECT


def test_exact_known_duplicate_is_hard_reject_but_fuzzy_title_is_not():
    duplicate = _record(
        item_id="dup",
        url="https://example.com/article/1?utm_source=x",
        title="Same title",
    )
    context = _context(known_duplicate_urls=frozenset({"https://example.com/article/1"}))
    assert _action(duplicate, context).decision.action is GateAction.HARD_REJECT

    other = _record(
        item_id="not-dup",
        url="https://example.com/article/2",
        title="Same title",
    )
    assert _action(other, context).decision.action is GateAction.ACQUIRE


def test_magazine_issue_landing_requires_both_path_and_issue_title():
    issue = _record(
        item_id="issue",
        url="https://example.com/magazine/123.html",
        title="2026年第8期",
    )
    article = _record(
        item_id="mag-article",
        url="https://example.com/magazine/124.html",
        title="一篇真正的深度报道",
    )
    assert _action(issue).decision.reason_code == "magazine_issue_landing"
    assert _action(issue).decision.action is GateAction.HARD_REJECT
    assert _action(article).decision.action is GateAction.ACQUIRE


def test_authoritative_stale_ordinary_article_is_hard_reject():
    record = _record(
        item_id="stale",
        url="https://example.com/article/stale.html",
        title="Old media article",
        date_values=(("2026-07-01T09:00:00+08:00", 0.97),),
    )
    run = _action(record)
    assert run.decision.action is GateAction.HARD_REJECT
    assert run.decision.reason_code == "authoritative_stale_ordinary_article"


@pytest.mark.parametrize(
    ("item_id", "url", "title"),
    [
        ("academic", "https://academic.oup.com/journal/article/123", "A journal article"),
        ("pdf", "https://example.gov/report/policy.pdf", "Official policy report"),
        ("gov", "https://www.pbc.gov.cn/policy/123.html", "关于人工智能金融应用的管理办法"),
    ],
)
def test_special_material_does_not_inherit_ordinary_14_day_hard_gate(item_id, url, title):
    record = _record(
        item_id=item_id,
        url=url,
        title=title,
        date_values=(("2026-06-01T09:00:00+08:00", 0.98),),
    )
    assert _action(record).decision.action is GateAction.ACQUIRE


def test_low_confidence_old_search_date_is_not_a_hard_reject():
    record = _record(
        item_id="low-date",
        url="https://example.com/article/possible.html",
        title="Potential article",
        date_values=(("2026-06-01", 0.45),),
    )
    assert _action(record).decision.action is GateAction.ACQUIRE


def test_unknown_date_is_not_negative_evidence():
    record = _record(
        item_id="unknown",
        url="https://example.com/article/no-date.html",
        title="Unknown-date reported feature",
    )
    run = _action(record)
    assert run.decision.action is GateAction.ACQUIRE
    assert run.decision.reason_code == "acquire_for_evidence"


def test_conflicting_authoritative_dates_defer_instead_of_reject():
    record = _record(
        item_id="conflict",
        url="https://example.com/article/conflict.html",
        title="Article with conflicting metadata",
        date_values=(("2026-08-06", 0.97), ("2026-07-01", 0.95)),
    )
    run = _action(record)
    assert run.decision.action is GateAction.DEFER
    assert run.decision.reason_code == "publication_date_conflict"
    assert run.event.flow_status is FlowStatus.DEFER


def test_authoritative_future_date_defers_instead_of_permanent_reject():
    record = _record(
        item_id="future",
        url="https://example.com/article/future.html",
        title="Article with suspicious future date",
        date_values=(("2026-08-20", 0.97),),
    )
    run = _action(record)
    assert run.decision.action is GateAction.DEFER
    assert run.decision.reason_code == "authoritative_future_publication_date"


@pytest.mark.parametrize(
    ("item_id", "url", "title"),
    [
        (
            "podcast-analysis",
            "https://example.com/analysis/podcast-business.html",
            "Why the podcast business is changing investigative journalism",
        ),
        (
            "program-investigation",
            "https://example.com/investigation/degree-program.html",
            "Investigation reveals problems inside an academic program",
        ),
        (
            "conference-report",
            "https://example.com/news/conference-report.html",
            "What the AI conference revealed about the chip industry",
        ),
        (
            "training-opening",
            "https://example.gov.cn/news/training.html",
            "全市镇（街道）党（工）委书记能力建设专题培训班开班",
        ),
        (
            "book-fair",
            "https://example.com/news/bookfair.html",
            "上海书展即将开幕：完整活动与出版观察",
        ),
        (
            "cctv",
            "https://example.com/news/focus-interview.html",
            "焦点访谈：人工智能如何改变产业",
        ),
        (
            "press-release-title",
            "https://example.com/article/company-announcement.html",
            "Press Release: Company announces new research results",
        ),
        (
            "market-report-title",
            "https://example.com/article/market-report.html",
            "Market report: the semiconductor industry in 2026",
        ),
    ],
)
def test_semantic_title_classes_are_not_pre_body_hard_rejects(item_id, url, title):
    assert _action(_record(item_id=item_id, url=url, title=title)).decision.action is GateAction.ACQUIRE


def test_generic_ambiguous_route_defers_without_destroying_candidate():
    record = _record(
        item_id="events-root",
        url="https://example.com/events",
        title="Events",
    )
    run = _action(record)
    assert run.decision.action is GateAction.DEFER
    assert run.decision.reason_code == "ambiguous_non_article_route"


def test_fixed_gate_replay_has_zero_high_value_false_hard_rejects():
    rows = []
    fixtures = [
        (_record(item_id="home-r", url="https://bad.example/", title="Home"), True, False),
        (_record(item_id="search-r", url="https://bad.example/search", title="Search"), True, False),
        (_record(item_id="jobs-r", url="https://bad.example/careers", title="Careers"), True, False),
        (
            _record(
                item_id="stale-r",
                url="https://bad.example/article/old.html",
                title="Old article",
                date_values=(("2026-07-01", 0.98),),
            ),
            True,
            False,
        ),
        (
            _record(
                item_id="turnintl",
                url="https://global.udn.com/global_vision/story/8662/",
                title="深度分析：国家治理的边界",
            ),
            False,
            True,
        ),
        (
            _record(
                item_id="reported-feature",
                url="https://example.com/features/investigation.html",
                title="调查：播客行业的商业逻辑",
            ),
            False,
            True,
        ),
        (
            _record(
                item_id="academic-r",
                url="https://academic.oup.com/journal/article/999",
                title="Research article",
                date_values=(("2026-06-01", 0.98),),
            ),
            False,
            True,
        ),
        (
            _record(
                item_id="unknown-r",
                url="https://example.com/article/unknown.html",
                title="Reported feature with no discovery date",
            ),
            False,
            True,
        ),
    ]
    service = AcquisitionGateService()
    for record, expected_hard, high_value in fixtures:
        decision = service.decide(record, _context()).decision
        rows.append((decision, expected_hard, high_value))

    metrics = evaluate_gate_replay(rows)
    assert metrics.hard_reject_precision >= 0.98
    assert metrics.false_hard_reject_count == 0
    assert metrics.high_value_false_hard_reject_count == 0
