# Acquisition Body Usability Regression Contract v1

Date: 2026-08-30  
Status: **DESIGN / OFFLINE REGRESSION ONLY**  
Tracks: Issue #53  
Production effect: **NONE**

## 1. First-principles problem

An extractor returning bytes/text is not equivalent to obtaining an article body.

The acquisition layer must distinguish at least:
1. transport/HTTP success;
2. extractor returned content;
3. content is a plausible article body;
4. body is sufficient for downstream canonical/editorial judgment.

A 2xx response containing tracking pixels, ads, navigation chrome, consent text or an extremely short non-article fragment is a **pseudo-success**. It must not terminate fallback merely because a provider returned non-empty text.

## 2. Reference failure

Fixed historical reference from #53:
- run: `COL-20260805-045835-BJT-pre_report`;
- article_id: `fff0827dc4790e16c060`;
- source/page: ProPublica investigation-methodology article;
- Jina returned about 37 characters of ad/tracking material;
- human review established the page itself as an editorially valid methodology article.

Therefore the defect class is acquisition/body-usability state, not article-value classification.

## 3. Frozen state model

Each attempt should conceptually emit independent fields:
- `transport_status`;
- `extractor_status`;
- `body_usability_status`;
- `body_usability_reason`;
- `prose_chars`;
- `raw_content_chars`;
- `content_hash`;
- `provider`;
- `attempt_ordinal`;
- `fallback_triggered`.

Suggested body-usability terminal vocabulary:
- `usable_article_body`;
- `pseudo_success_shell_or_ad`;
- `insufficient_non_article_text`;
- `empty_body`;
- `unknown_unvalidated`.

The exact enum names are not authorized by this document; the semantic distinction is frozen.

## 4. Fallback invariant

> `extractor success` may stop the chain only if body usability passes the frozen gate.

If body usability fails:
- continue to the next already-authorized path if budget remains;
- otherwise record an explicit terminal body-unavailable state.

Do not increase Firecrawl budget or the max-32 article-attempt budget to fix pseudo-success.

## 5. Minimum deterministic fixture set

A future implementation must register at least three controlled fixtures before changing Production semantics.

### Fixture A — pseudo-success shell/ad
Reference characteristics:
- tiny content body;
- tracking/ad/nav-like text;
- HTTP/extractor technically successful;
- expected: body unusable and fallback eligible.

The historical ProPublica 37-character extraction is the canonical regression reference where a stable offline fixture can be captured without redistributing copyrighted full text.

### Fixture B — legitimate short methodology/explainer
Characteristics:
- relatively short but coherent editorial prose;
- independent article identity;
- expected: not rejected merely because it is shorter than a typical longread.

Purpose: prevent the pseudo-success fix from becoming a crude minimum-length rule.

### Fixture C — genuine short news brief
Characteristics:
- coherent article body;
- technically usable;
- editorially a short brief/non-target for longread product.

Expected:
- acquisition says body usable;
- editorial/product layer, not acquisition, decides it is not a target longread.

This fixture enforces separation of acquisition quality from editorial suitability.

## 6. Acceptance tests

A future code patch is acceptable only if all are true:
1. pseudo-success shell/ad does not terminate fallback as success;
2. legitimate coherent short editorial text is not rejected solely by a single hard character threshold;
3. a true short brief is acquisition-usable but remains available for downstream non-target classification;
4. every attempt remains visible in acquisition provenance;
5. run-level provider/Firecrawl request accounting equals attempt-level evidence;
6. fallback remains inside existing paid/request budgets;
7. no duplicate paid request is generated after an ambiguous prior side effect;
8. historical normal-body fixtures remain unchanged.

## 7. Recommended implementation order

1. capture small non-copyright-sensitive structural fixtures and expected states;
2. implement a pure `body_usability` evaluator behind offline tests;
3. replay historical acquisition attempts without networking;
4. compare old vs proposed terminal states;
5. only after explicit runtime authorization, wire the gate into v0.6 Acquisition Shadow;
6. collect natural Shadow evidence before any primary use.

Do not patch the legacy control merely to make the reference sample green unless a separately reviewed reliability/security exception applies.

## 8. Readiness interpretation

This contract targets **Acquisition readiness (A-axis)** and **Measurement integrity (M-axis)**. It does not provide Source/Route Value evidence and does not authorize source promotion.
