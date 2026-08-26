"""Final Recall v1.3.1 forensic measurement contract.

v1.3.1 is a strict offline/Shadow measurement overlay.  It preserves v1.2
capture semantics while fixing four denominator defects found in the Phase-2
forensic replay:

* product scope is evaluated before Recall;
* a registrable domain is not treated as publication-surface identity;
* source×run coverage must join a successful durable Collector run with a
  complete snapshot persistence/readback contract;
* trusted persisted exact publication timestamps may resolve date-only
  ambiguity, while materially conflicting exact timestamps fail closed.

The scheduled Final Recall workflow intentionally remains on v1.2 until a
separate reviewed acceptance decision.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit
from dateutil import parser as date_parser
from .config import get_settings
from .final_recall_audit import _ensure_sheet, _ratio, _replace_date_rows, _sheet_datetime
from .final_recall_audit_v12 import AUDIT_V12_HEADERS, DAILY_V12_HEADERS, _upsert_daily, audit_final_recall_v12
from .final_recall_audit_v13 import REALIZED_HEADERS, CoverageEvaluation, _best_route_row, _coverage_relation, _coverage_run_started, _discovered, _editable, _full_snapshot_measurement, _marker_map, _measurement_valid, _publication_precision, _route_failure_status
from .normalization import canonicalize_url
from .recall_instrumentation import normalize_title
from .registry_matching_v056 import match_registry
from .sheets import RUN_HEADERS, SOURCE_HEADERS, GoogleSheetStore
from .source_run_coverage import SOURCE_RUN_COVERAGE_HEADERS, SOURCE_RUN_COVERAGE_SHEET, SOURCE_RUN_COVERAGE_VERSION
AUDIT_VERSION = 'final-recall-audit-v1.3.1-forensic-contract'
DENOMINATOR_VERSION = 'publication-surface-durable-run-v1.3.1'
MEASUREMENT_VERSION = DENOMINATOR_VERSION
STRICT_HEADERS = ['product_scope_status', 'product_scope_reason', 'publication_surface_id', 'publication_surface_status', 'publication_surface_reason', 'publication_evidence_status', 'resolved_published_at_bj', 'resolved_publication_precision', 'publication_evidence_sources', 'durable_run_status', 'nondurable_source_coverage_row_count', 'strict_measurement_universe_status']
AUDIT_V131_HEADERS = AUDIT_V12_HEADERS + STRICT_HEADERS + REALIZED_HEADERS
DAILY_STRICT_HEADERS = ['strict_measurement_universe', 'strict_measurement_covered', 'strict_measurement_coverage_rate', 'strict_measurement_zh_universe', 'strict_measurement_zh_covered', 'strict_measurement_en_universe', 'strict_measurement_en_covered', 'conditional_surface_recall_denominator', 'conditional_surface_recall_discovered', 'conditional_surface_recall', 'conditional_surface_editable', 'conditional_surface_editable_recall', 'product_scope_excluded_items', 'publication_surface_mismatch_items', 'preledger_items', 'publication_date_conflict_items', 'nondurable_coverage_only_items', 'coverage_ledger_started_at_bj', 'strict_measurement_version']
DAILY_V131_HEADERS = DAILY_V12_HEADERS + DAILY_STRICT_HEADERS
_TRUTHY = {'TRUE', '1', 'YES', 'Y'}
_EXACT_CONFLICT_TOLERANCE = timedelta(minutes=5)
_TZINFOS = {'UTC': 0, 'GMT': 0, 'BJT': 8 * 3600, 'CST': 8 * 3600, 'EDT': -4 * 3600, 'EST': -5 * 3600}

@dataclass(frozen=True, slots=True)
class PublicationEvidence:
    status: str
    resolved_raw: str = ''
    resolved_at: datetime | None = None
    precision: str = 'unknown'
    sources: str = ''

@dataclass(frozen=True, slots=True)
class ScopeEvaluation:
    status: str
    reason: str

@dataclass(frozen=True, slots=True)
class SurfaceEvaluation:
    surface_id: str
    status: str
    reason: str

def _truthy(value: Any) -> bool:
    return str(value or '').strip().upper() in _TRUTHY

def _safe_int(value: Any) -> int | None:
    try:
        text = str(value if value is not None else '').strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None

def _canonical_url(value: Any) -> str:
    text = str(value or '').strip()
    return canonicalize_url(text) if text else ''

def _final_url(item: dict[str, Any]) -> str:
    return str(item.get('final_url_canonical') or item.get('final_url') or '').strip()

def evaluate_product_scope(item: dict[str, Any]) -> ScopeEvaluation:
    """Return the Daily Longread product-scope classification.

    Scientific journalism remains in scope.  Scholarly journal assets and
    preprints are excluded before any Recall denominator is formed.
    """
    url = _final_url(item)
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix('www.')
    path = parts.path.lower()
    if host in {'arxiv.org', 'biorxiv.org', 'medrxiv.org'}:
        return ScopeEvaluation('excluded', 'scholarly_preprint')
    if host.endswith('nature.com') and path.startswith('/articles/s'):
        return ScopeEvaluation('excluded', 'nature_scholarly_asset')
    return ScopeEvaluation('in_scope', 'daily_longread_written_journalism')

def evaluate_publication_surface(item: dict[str, Any], source_row: dict[str, Any] | None) -> SurfaceEvaluation:
    """Evaluate exact publication-surface identity, not just publisher domain."""
    if source_row is None:
        return SurfaceEvaluation('', 'outside_registry', 'no_registry_match')
    source_id = str(source_row.get('source_id', '') or '').strip()
    url = _final_url(item)
    path = urlsplit(url).path.lower()
    if source_id == 'nature-news':
        if path.startswith('/articles/d41586-'):
            return SurfaceEvaluation(source_id, 'matched', 'nature_news_features_path')
        return SurfaceEvaluation(source_id, 'mismatch', 'not_nature_news_features')
    if source_id == 'reuters-special':
        if path.startswith('/investigates/'):
            return SurfaceEvaluation(source_id, 'matched', 'reuters_investigates_path')
        return SurfaceEvaluation(source_id, 'mismatch', 'not_reuters_special_report')
    if source_id == 'guardian-longread':
        matched_source = str(item.get('matched_source', '') or '').strip()
        if matched_source == 'The Guardian · The Long Read':
            return SurfaceEvaluation(source_id, 'matched', 'collector_long_read_feed_identity')
        if 'the-long-read' in path:
            return SurfaceEvaluation(source_id, 'matched', 'guardian_long_read_url_marker')
        return SurfaceEvaluation(source_id, 'mismatch', 'not_guardian_long_read_surface')
    return SurfaceEvaluation(source_id, 'matched', 'registry_publisher_surface')

def _parse_exact_datetime(value: Any, tz: Any) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text, tzinfos=_TZINFOS)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)

def _candidate_exact_matches(item: dict[str, Any], candidate_rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    final_url = _canonical_url(_final_url(item))
    if final_url:
        exact_url = [row for row in candidate_rows if _canonical_url(row.get('url_canonical') or row.get('url')) == final_url]
        if exact_url:
            return (exact_url, 'candidate_log_exact_url')
    final_title = normalize_title(str(item.get('final_title_norm') or item.get('final_title') or ''))
    final_source = normalize_title(str(item.get('final_source', '') or ''))
    if not final_title:
        return ([], '')
    conservative = []
    for row in candidate_rows:
        row_title = normalize_title(str(row.get('title_norm') or row.get('title') or ''))
        row_source = normalize_title(str(row.get('canonical_source', '') or ''))
        if row_title != final_title:
            continue
        if final_source and row_source and (final_source != row_source):
            continue
        conservative.append(row)
    return (conservative, 'candidate_log_exact_title_source' if conservative else '')

def resolve_publication_evidence(*, item: dict[str, Any], candidate_rows: Iterable[dict[str, Any]], tz: Any) -> PublicationEvidence:
    """Resolve publication time using a conservative persisted evidence hierarchy."""
    base_raw = str(item.get('published_date', '') or '').strip()
    base_precision = _publication_precision(base_raw)
    exact: list[tuple[datetime, str]] = []
    if base_precision == 'datetime':
        parsed = _sheet_datetime(base_raw, tz)
        if parsed is not None:
            exact.append((parsed, 'final_reference_exact'))
    matching_rows, match_source = _candidate_exact_matches(item, candidate_rows)
    for row in matching_rows:
        raw = str(row.get('published_at', '') or '').strip()
        if _publication_precision(raw) != 'datetime':
            continue
        parsed = _parse_exact_datetime(raw, tz)
        if parsed is not None:
            exact.append((parsed, match_source))
    if exact:
        exact.sort(key=lambda pair: pair[0])
        if exact[-1][0] - exact[0][0] > _EXACT_CONFLICT_TOLERANCE:
            return PublicationEvidence(status='publication_date_conflict', precision='unknown', sources='|'.join(sorted({source for _, source in exact})))
        chosen = exact[0][0]
        return PublicationEvidence(status='exact_persisted', resolved_raw=chosen.strftime('%Y-%m-%d %H:%M:%S'), resolved_at=chosen, precision='datetime', sources='|'.join(sorted({source for _, source in exact})))
    base_at = _sheet_datetime(base_raw, tz)
    if base_at is not None and base_precision == 'date':
        return PublicationEvidence(status='date_only', resolved_raw=base_at.strftime('%Y-%m-%d'), resolved_at=base_at, precision='date', sources='final_reference_date')
    return PublicationEvidence(status='unknown', precision='unknown')

def durable_run_status(row: dict[str, Any], tz: Any) -> tuple[bool, str]:
    """Validate the durable-run foreign-key contract for Recall evidence."""
    if not str(row.get('collector_run_id', '') or '').strip():
        return (False, 'missing_run_id')
    if str(row.get('final_status', '') or '').strip().lower() != 'success':
        return (False, 'run_not_success')
    if _sheet_datetime(row.get('completed_at_bj'), tz) is None:
        return (False, 'run_not_completed')
    marker = _marker_map(row.get('notes', ''))
    if marker.get('source_run_coverage_version') != SOURCE_RUN_COVERAGE_VERSION:
        return (False, 'coverage_contract_version_missing')
    if marker.get('source_run_coverage_persisted', '').upper() != 'TRUE':
        return (False, 'coverage_not_persisted')
    if marker.get('snapshot_persistence_status', '').lower() != 'success':
        return (False, 'snapshot_persistence_not_success')
    expected = _safe_int(marker.get('snapshot_expected_rows'))
    persisted = _safe_int(marker.get('snapshot_persisted_rows'))
    if expected is None or persisted is None or expected != persisted:
        return (False, 'snapshot_row_count_mismatch')
    if marker.get('snapshot_readback_performed', '').upper() != 'TRUE':
        return (False, 'snapshot_readback_not_confirmed')
    return (True, 'durable_success')

def durable_runs_by_id(collector_runs: Iterable[dict[str, Any]], tz: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in collector_runs:
        ok, _ = durable_run_status(row, tz)
        run_id = str(row.get('collector_run_id', '') or '').strip()
        if ok and run_id:
            result[run_id] = row
    return result

def strict_coverage_ledger_start(collector_runs: Iterable[dict[str, Any]], tz: Any) -> datetime | None:
    starts = []
    for row in durable_runs_by_id(collector_runs, tz).values():
        started = _sheet_datetime(row.get('started_at_bj'), tz)
        if started is not None:
            starts.append(started)
    return min(starts) if starts else None

def _coverage_row_matches_durable_run(row: dict[str, Any], durable_run: dict[str, Any], tz: Any) -> bool:
    if str(row.get('coverage_version', '') or '') != SOURCE_RUN_COVERAGE_VERSION:
        return False
    if not _truthy(row.get('selected', 'TRUE')):
        return False
    row_group = str(row.get('query_group', '') or '').strip()
    run_group = str(durable_run.get('query_group', '') or '').strip()
    if row_group and run_group and (row_group != run_group):
        return False
    row_started = _coverage_run_started(row, tz)
    run_started = _sheet_datetime(durable_run.get('started_at_bj'), tz)
    if row_started is None or run_started is None:
        return False
    return abs((row_started - run_started).total_seconds()) <= 300

def evaluate_strict_measurement_item(*, item: dict[str, Any], source_row: dict[str, Any] | None, candidate_rows: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], collector_runs: list[dict[str, Any]], ledger_started_at: datetime | None, tz: Any) -> dict[str, Any]:
    """Apply the v1.3.1 strict measurement contract to one v1.2 item."""
    scope = evaluate_product_scope(item)
    surface = evaluate_publication_surface(item, source_row)
    publication = resolve_publication_evidence(item=item, candidate_rows=candidate_rows, tz=tz)
    ledger_text = ledger_started_at.strftime('%Y-%m-%d %H:%M:%S') if ledger_started_at else ''
    source_id = str((source_row or {}).get('source_id', '') or '')
    strict = {'product_scope_status': scope.status, 'product_scope_reason': scope.reason, 'publication_surface_id': surface.surface_id, 'publication_surface_status': surface.status, 'publication_surface_reason': surface.reason, 'publication_evidence_status': publication.status, 'resolved_published_at_bj': publication.resolved_raw, 'resolved_publication_precision': publication.precision, 'publication_evidence_sources': publication.sources, 'durable_run_status': 'not_evaluated', 'nondurable_source_coverage_row_count': 0, 'strict_measurement_universe_status': 'excluded'}
    def excluded(status: str, realized_status: str) -> dict[str, Any]:
        evaluation = CoverageEvaluation(realized_source_id=source_id, publication_precision=publication.precision, coverage_ledger_started_at_bj=ledger_text, coverage_ledger_observation_status=status, realized_coverage_status=realized_status, coverage_contract_denominator_status=status)
        return {**strict, **evaluation.as_dict()}
    if scope.status != 'in_scope':
        strict['strict_measurement_universe_status'] = 'excluded_product_scope'
        return excluded('excluded_product_scope', 'out_of_product_scope')
    if source_row is None:
        strict['strict_measurement_universe_status'] = 'excluded_outside_registry'
        return excluded('excluded_outside_registry', 'outside_registry')
    if surface.status != 'matched':
        strict['strict_measurement_universe_status'] = 'excluded_publication_surface_mismatch'
        return excluded('excluded_publication_surface_mismatch', 'publication_surface_mismatch')
    observation_start = _sheet_datetime(item.get('item_observation_started_at_bj'), tz)
    cutoff = _sheet_datetime(item.get('cutoff_at_bj'), tz)
    if not _measurement_valid(item) or observation_start is None or cutoff is None:
        strict['strict_measurement_universe_status'] = 'excluded_measurement_invalid'
        return excluded('excluded_measurement_invalid', 'measurement_invalid')
    if ledger_started_at is None:
        strict['strict_measurement_universe_status'] = 'excluded_ledger_unavailable'
        return excluded('excluded_ledger_unavailable', 'coverage_ledger_unavailable')
    if observation_start < ledger_started_at:
        strict['strict_measurement_universe_status'] = 'excluded_preledger'
        return excluded('excluded_preledger', 'coverage_ledger_partial_observation')
    if publication.status == 'publication_date_conflict':
        strict['strict_measurement_universe_status'] = 'excluded_publication_date_conflict'
        return excluded('excluded_publication_date_conflict', 'publication_date_conflict')
    if publication.resolved_at is None:
        strict['strict_measurement_universe_status'] = 'excluded_publication_time_unknown'
        return excluded('excluded_publication_time_unknown', 'publication_time_unknown')
    strict['strict_measurement_universe_status'] = 'included'
    durable = durable_runs_by_id(collector_runs, tz)
    durable_source_rows = []
    nondurable_rows = []
    for row in coverage_rows:
        if str(row.get('source_id', '') or '') != source_id:
            continue
        started = _coverage_run_started(row, tz)
        if started is None or not observation_start <= started <= cutoff:
            continue
        run_id = str(row.get('collector_run_id', '') or '')
        run = durable.get(run_id)
        if run is not None and _coverage_row_matches_durable_run(row, run, tz):
            durable_source_rows.append(row)
        else:
            nondurable_rows.append(row)
    strict['nondurable_source_coverage_row_count'] = len(nondurable_rows)
    strict['durable_run_status'] = 'durable_source_coverage_present' if durable_source_rows else 'nondurable_coverage_only' if nondurable_rows else 'no_source_coverage_row'
    contract_status = 'coverage_contract_denominator'
    if not durable_source_rows:
        realized_status = 'nondurable_coverage_only' if nondurable_rows else 'source_not_selected_in_durable_window'
        evaluation = CoverageEvaluation(realized_source_id=source_id, publication_precision=publication.precision, coverage_ledger_started_at_bj=ledger_text, coverage_ledger_observation_status='full', coverage_candidate_run_count=0, source_coverage_row_count=0, realized_coverage_status=realized_status, coverage_contract_denominator_status=contract_status)
        return {**strict, **evaluation.as_dict()}
    native_rows = [row for row in durable_source_rows if str(row.get('route_status', '') or '') == 'native_covered']
    relations = [(_coverage_relation(published_raw=publication.resolved_raw, published_at=publication.resolved_at, coverage_row=row, tz=tz), row) for row in native_rows]
    covered_rows = [row for relation, row in relations if relation == 'covered']
    if covered_rows:
        chosen = min(covered_rows, key=lambda row: _coverage_run_started(row, tz) or datetime.max.replace(tzinfo=tz))
        conditional = 'conditional_surface_denominator' if _full_snapshot_measurement(item, tz) else 'partial_snapshot_observation'
        evaluation = CoverageEvaluation(realized_source_id=source_id, publication_precision=publication.precision, coverage_ledger_started_at_bj=ledger_text, coverage_ledger_observation_status='full', coverage_candidate_run_count=len({str(row.get('collector_run_id', '')) for row in durable_source_rows}), source_coverage_row_count=len(durable_source_rows), realized_coverage_status='realized_route_covered', realized_coverage_run_id=str(chosen.get('collector_run_id', '')), realized_route_status=str(chosen.get('route_status', '')), realized_selected_method=str(chosen.get('selected_method', '')), realized_selected_endpoint=str(chosen.get('selected_endpoint', '')), realized_oldest_observed_published_at=str(chosen.get('oldest_observed_published_at', '')), realized_newest_observed_published_at=str(chosen.get('newest_observed_published_at', '')), realized_horizon_hours=chosen.get('observed_horizon_hours', ''), realized_coverage_confidence=str(chosen.get('coverage_confidence', '')), coverage_contract_denominator_status=contract_status, conditional_surface_denominator_status=conditional)
        return {**strict, **evaluation.as_dict()}
    best = _best_route_row(durable_source_rows, tz)
    if any((relation == 'ambiguous' for relation, _ in relations)):
        status = 'publication_time_boundary_ambiguous'
    elif native_rows:
        status = 'target_outside_observed_horizon'
    else:
        status = _route_failure_status(durable_source_rows)
    evaluation = CoverageEvaluation(realized_source_id=source_id, publication_precision=publication.precision, coverage_ledger_started_at_bj=ledger_text, coverage_ledger_observation_status='full', coverage_candidate_run_count=len({str(row.get('collector_run_id', '')) for row in durable_source_rows}), source_coverage_row_count=len(durable_source_rows), realized_coverage_status=status, realized_coverage_run_id=str((best or {}).get('collector_run_id', '')), realized_route_status=str((best or {}).get('route_status', '')), realized_selected_method=str((best or {}).get('selected_method', '')), realized_selected_endpoint=str((best or {}).get('selected_endpoint', '')), realized_oldest_observed_published_at=str((best or {}).get('oldest_observed_published_at', '')), realized_newest_observed_published_at=str((best or {}).get('newest_observed_published_at', '')), realized_horizon_hours=(best or {}).get('observed_horizon_hours', ''), realized_coverage_confidence=str((best or {}).get('coverage_confidence', '')), coverage_contract_denominator_status=contract_status)
    return {**strict, **evaluation.as_dict()}

def strict_summary(items: list[dict[str, Any]], ledger_started_at: datetime | None) -> dict[str, Any]:
    universe = [row for row in items if row.get('strict_measurement_universe_status') == 'included']
    covered = [row for row in universe if row.get('realized_coverage_status') == 'realized_route_covered']
    conditional = [row for row in items if row.get('conditional_surface_denominator_status') == 'conditional_surface_denominator']
    discovered = sum((_discovered(row) for row in conditional))
    editable = sum((_editable(row) for row in conditional))
    zh_universe = [row for row in universe if str(row.get('language', '')) == 'zh']
    en_universe = [row for row in universe if str(row.get('language', '')) == 'en']
    zh_covered = [row for row in covered if str(row.get('language', '')) == 'zh']
    en_covered = [row for row in covered if str(row.get('language', '')) == 'en']
    return {'strict_measurement_universe': len(universe), 'strict_measurement_covered': len(covered), 'strict_measurement_coverage_rate': _ratio(len(covered), len(universe)), 'strict_measurement_zh_universe': len(zh_universe), 'strict_measurement_zh_covered': len(zh_covered), 'strict_measurement_en_universe': len(en_universe), 'strict_measurement_en_covered': len(en_covered), 'conditional_surface_recall_denominator': len(conditional), 'conditional_surface_recall_discovered': discovered, 'conditional_surface_recall': _ratio(discovered, len(conditional)), 'conditional_surface_editable': editable, 'conditional_surface_editable_recall': _ratio(editable, len(conditional)), 'product_scope_excluded_items': sum((row.get('strict_measurement_universe_status') == 'excluded_product_scope' for row in items)), 'publication_surface_mismatch_items': sum((row.get('strict_measurement_universe_status') == 'excluded_publication_surface_mismatch' for row in items)), 'preledger_items': sum((row.get('strict_measurement_universe_status') == 'excluded_preledger' for row in items)), 'publication_date_conflict_items': sum((row.get('strict_measurement_universe_status') == 'excluded_publication_date_conflict' for row in items)), 'nondurable_coverage_only_items': sum((row.get('realized_coverage_status') == 'nondurable_coverage_only' for row in items)), 'coverage_ledger_started_at_bj': ledger_started_at.strftime('%Y-%m-%d %H:%M:%S') if ledger_started_at else '', 'strict_measurement_version': MEASUREMENT_VERSION}

def _read_coverage_rows(store: GoogleSheetStore) -> list[dict[str, Any]]:
    try:
        ws = store.book.worksheet(SOURCE_RUN_COVERAGE_SHEET)
    except Exception as exc:
        if exc.__class__.__name__ == 'WorksheetNotFound':
            return []
        raise
    return ws.get_all_records(expected_headers=SOURCE_RUN_COVERAGE_HEADERS)

def _read_candidate_rows(store: GoogleSheetStore) -> list[dict[str, Any]]:
    try:
        return store.book.worksheet('candidate_log').get_all_records()
    except Exception as exc:
        if exc.__class__.__name__ == 'WorksheetNotFound':
            return []
        raise

def audit_final_recall_v131(store: GoogleSheetStore, *, report_date: date, cutoff_time: str='07:35', max_observation_days: int=14, write: bool=True) -> dict[str, Any]:
    base = audit_final_recall_v12(store, report_date=report_date, cutoff_time=cutoff_time, max_observation_days=max_observation_days, write=False)
    source_rows = store.book.worksheet('source_registry').get_all_records(expected_headers=SOURCE_HEADERS)
    collector_runs = store.book.worksheet('collector_runs').get_all_records(expected_headers=RUN_HEADERS)
    coverage_rows = _read_coverage_rows(store)
    candidate_rows = _read_candidate_rows(store)
    ledger_started_at = strict_coverage_ledger_start(collector_runs, store.tz)
    items: list[dict[str, Any]] = []
    for base_item in base['items']:
        item = dict(base_item)
        source_row = match_registry(item, source_rows)
        overlay = evaluate_strict_measurement_item(item=item, source_row=source_row, candidate_rows=candidate_rows, coverage_rows=coverage_rows, collector_runs=collector_runs, ledger_started_at=ledger_started_at, tz=store.tz)
        item.update(overlay)
        item['audit_version'] = AUDIT_VERSION
        items.append(item)
    summary = dict(base['summary'])
    summary.update(strict_summary(items, ledger_started_at))
    summary['audit_version'] = AUDIT_VERSION
    summary['denominator_version'] = DENOMINATOR_VERSION
    result = {'summary': summary, 'items': items, 'snapshot_mode': base.get('snapshot_mode', '')}
    if write:
        audit_ws = _ensure_sheet(store, 'final_recall_audit_v131', AUDIT_V131_HEADERS, rows=5000)
        daily_ws = _ensure_sheet(store, 'final_recall_daily_v131', DAILY_V131_HEADERS, rows=1000)
        report_text = report_date.isoformat()
        _replace_date_rows(audit_ws, date_column=2, report_date=report_text, rows=[[row.get(header, '') for header in AUDIT_V131_HEADERS] for row in items])
        _upsert_daily(daily_ws, report_text, [summary.get(header, '') for header in DAILY_V131_HEADERS])
    return result

def no_final_items_summary(report_date: date) -> dict[str, Any]:
    return {'report_date': report_date.isoformat(), 'audit_status': 'no_final_items', 'audit_version': AUDIT_VERSION, 'measurement_version': MEASUREMENT_VERSION, 'write_performed': False}

def main() -> None:
    parser = argparse.ArgumentParser(description='Audit Final Recall v1.3.1 with forensic measurement guards')
    parser.add_argument('--report-date', required=True)
    parser.add_argument('--cutoff-time', default='07:35')
    parser.add_argument('--max-observation-days', type=int, default=14)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    target_date = date.fromisoformat(args.report_date)
    settings = get_settings()
    store = GoogleSheetStore(settings)
    try:
        result = audit_final_recall_v131(store, report_date=target_date, cutoff_time=args.cutoff_time, max_observation_days=args.max_observation_days, write=not args.dry_run)
    except ValueError as exc:
        if str(exc).startswith('No final_items found for report_date='):
            print(no_final_items_summary(target_date))
            return
        raise
    print(result['summary'])
if __name__ == '__main__':
    main()
