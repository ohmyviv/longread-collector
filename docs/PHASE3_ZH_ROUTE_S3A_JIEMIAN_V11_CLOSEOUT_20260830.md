# Phase 3 — Jiemian S3-A fixed-32 v1.1 closeout

Date: 2026-08-30 BJT  
Status: **S3-A STRUCTURAL REPLAY VALID / S3-B EVIDENCE COMPLETION REQUIRED**  
Version: `zh-route-shadow-s3-jiemian-fixed32-v1.1-raw-url`

## 1. Why v1.1 exists

The immutable S3 v1 run `33262599781` failed its Control self-replay gate because offline reconstruction substituted canonical URL identity for the persisted raw runtime URL. The exact failure was the Initium `/journal/` trailing-slash semantic case documented in `PHASE3_S3_CONTROL_REPLAY_FORENSIC_20260830.md`.

v1.1 changes only that reconstruction boundary. All frozen cohort, ranking, freshness, source/host caps, 24+8 staged reserve semantics and maximum 32 attempts remain unchanged.

The v1 failure remains part of the audit trail and is not overwritten.

## 2. Immutable v1.1 execution evidence

GitHub Actions run: `33283402851`  
Artifact: `s3-jiemian-fixed32-v11-33283402851`  
Artifact digest: `sha256:c52092cdafc4ae6acf6abde6cd4ce40cfb9ebd8e5be12ec68355448dccc414d2`

Execution boundary:

- read-only: TRUE;
- body/network requests: 0;
- Sheet writes: 0;
- Production mutations: 0.

## 3. Control replay gate

All four frozen historical runs now reproduce exact attempt identity and order:

| Run | Historical attempts | Replay attempts | Exact |
| --- | ---: | ---: | --- |
| `COL-20260827-224813-BJT-zh_midday` | 24 | 24 | PASS |
| `COL-20260828-040117-BJT-zh_evening` | 32 | 32 | PASS |
| `COL-20260828-234148-BJT-zh_midday` | 25 | 25 | PASS |
| `COL-20260829-050025-BJT-zh_evening` | 32 | 32 | PASS |

Therefore the S3 structural simulator is valid for this frozen cohort under the v1.1 reconstruction contract.

## 4. Jiemian structural entry

Jiemian qualified Treatment incrementals enter the fixed-budget competition on three distinct intended schedule dates:

- 2026-08-27;
- 2026-08-28;
- 2026-08-29.

This is not extra capacity: the same max 32 attempts, source cap and host cap are preserved.

The four frozen runs contain 23 per-run eligible Jiemian Treatment identities under the exact per-run freshness/control-non-overlap rule. Treatment entry is therefore structurally real, not merely metadata supply outside the selection boundary.

## 5. Why S3-A stops before a utility conclusion

The S2-B body-review sample covered only part of the frozen 28-item Jiemian plausible universe. Four Treatment identities can enter first stage without pre-S3 body evidence. Their usable/failed outcomes change downstream second-stage identity in at least one frozen run.

The exact unique evidence-completion manifest is:

1. `https://jiemian.com/article/14977759.html` — **白云山转型半年：创新投入增长、王牌仍在下滑** — first surface `jiemian_medicine`;
2. `https://jiemian.com/article/14997276.html` — **从“长寿”到“健康长寿”，抗衰开始走进整个生活** — first surface `jiemian_consumer`;
3. `https://jiemian.com/article/14998723.html` — **ST香雪“保壳”命悬一线** — first surface `jiemian_medicine`;
4. `https://jiemian.com/article/15018993.html` — **衰老干预技术的高价困局，瑞拓龄能否打破成本壁垒** — first surface `jiemian_medicine`.

Existing-evidence check on 2026-08-30:

- Production `article_cache`: 0/4 present;
- historical `extraction_log`: 0/4 present;
- S2-B reviewed evidence: these four identities were not already body-confirmed in the frozen reviewed sample.

No title/source inference is allowed to substitute for body evidence.

## 6. Current state

Top-level S3-A state:

`STRUCTURAL_EFFECT_NEEDS_EVIDENCE`

This is stronger than the previous v1 `NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH`: the Control replay problem is resolved and Jiemian fixed-32 entry is established. The remaining uncertainty is now exactly bounded to four body outcomes.

This state does **not** yet justify `SUPPORTS_S4_SHADOW_SELECTION_REVIEW`, because aggregate body-confirmed utility delta cannot be signed until those four first-stage outcomes are observed under a separate bounded S3-B evidence-completion version.

## 7. S3-B boundary

A future S3-B evidence-completion run, if separately executed, must:

- use exactly these four URLs and no replacements;
- preserve their frozen identities/titles/surfaces;
- use a versioned isolated acquisition ledger;
- never rewrite S2-B v2.1 results;
- never write Production `article_cache` or Editor inputs;
- apply the existing frozen Standard Longread body rubric;
- feed only the resulting four terminal outcomes back into the already-frozen S3 v1.1 structural replay;
- stop once the aggregate fixed-32 utility sign is determined.

No additional Jiemian sample expansion is justified.

## 8. Production boundary

Unchanged:

- Production = `SHADOW / NOT_READY`;
- no Editor connection;
- no source/host-cap change;
- no natural 32-body-budget change;
- no S4 activation;
- no automatic promotion.
