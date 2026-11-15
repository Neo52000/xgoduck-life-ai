"""V3.3 daily continuous improvement: measurements, offline visual benchmark, review gate.

No shell, network, privileged write, code execution, firmware or deployment interfaces.
Source measurements are not an independent validation of candidate code changes.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .evolution import collect_metrics, diagnose
from .models import (Concept, Event, EvolutionCycle, Example, ImprovementProposal,
                     ReleaseAssessment, utcnow)
from .vision import ImageFeatures, match_score

MAX_BENCHMARK_EXAMPLES = 200
MIN_SAMPLES_RELEASE = 8
REVISION_RE = re.compile(r"^[A-Za-z0-9._-]{4,80}$")


def cycle_json(c: EvolutionCycle) -> dict:
    return {"id":c.id, "day_key":c.day_key, "code_revision":c.code_revision,
            "metrics":c.metrics, "benchmark":c.benchmark, "trend":c.trend,
            "diagnosis_id":c.diagnosis_id,
            "created_at":c.created_at.isoformat() if c.created_at else None}


def assessment_json(a: ReleaseAssessment) -> dict:
    return {"id":a.id,"proposal_id":a.proposal_id,
            "base_revision":a.base_revision,"candidate_revision":a.candidate_revision,
            "evidence":a.evidence, "verdict":a.verdict,"reasons":a.reasons,
            "status":a.status,"created_at":a.created_at.isoformat() if a.created_at else None,
            "reviewed_at":a.reviewed_at.isoformat() if a.reviewed_at else None}


def visual_benchmark(db: Session) -> dict:
    """Offline deterministic recognition benchmark, one gallery view per concept.

    Other confirmed views are held out, exact-image copies excluded. The benchmark
    contains NO photos or raw feature vectors. Low sample counts are inconclusive.
    """
    rows = db.execute(select(Example, Concept).join(Concept, Example.concept_id == Concept.id)
        .where(Concept.status == "confirmed")
        .order_by(Example.concept_id, Example.created_at, Example.id)
        .limit(MAX_BENCHMARK_EXAMPLES)).all()
    groups: dict[str,list[Example]] = defaultdict(list)
    for ex, concept in rows:
        groups[concept.id].append(ex)
    gallery: dict[str,Example] = {}
    queries = []
    conflicts = 0
    sha_owners = defaultdict(set)
    for cid, examples in groups.items():
        for ex in examples:
            sha_owners[ex.sha256].add(cid)
    bad_sha = {sha for sha, owners in sha_owners.items() if len(owners) > 1}
    for cid, examples in groups.items():
        uniq = []
        seen = set()
        for ex in examples:
            if ex.sha256 in bad_sha:
                conflicts += 1
                continue
            if ex.sha256 not in seen:
                uniq.append(ex)
                seen.add(ex.sha256)
        if not uniq:
            continue
        gallery[cid] = uniq[0]
        for ex in uniq[1:]:
            queries.append((cid, ex))
    # A gallery must include at least 2 distinct categories for a meaningful mis-ID test.
    if len(gallery) < 2:
        queries = []
    sample_fingerprint = [
        (cid, ex.sha256, ex.id) for cid, examples in sorted(groups.items())
        for ex in examples
    ]
    dataset_hash = hashlib.sha256(json.dumps(sample_fingerprint,
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    correct = wrong = abstained = 0
    for expected, item in queries:
        sample = ImageFeatures(jpeg=b"", sha256=item.sha256, dhash=item.dhash,
            histogram=item.histogram, texture=item.texture)
        scores = []
        for cid, reference in gallery.items():
            try:
                score = match_score(sample, reference)
            except (TypeError, ValueError, OverflowError):
                score = 0.0
            scores.append((score, cid))
        scores.sort(reverse=True)
        best_score, best_id = scores[0] if scores else (0.0, "")
        second_score = scores[1][0] if len(scores)>1 else 0.0
        # Strict and stable candidate rule; this is a benchmark, not an autonomous learner.
        if best_score < 0.80 or best_score - second_score < 0.05:
            abstained += 1
        elif best_id == expected:
            correct += 1
        else:
            wrong += 1
    n = len(queries)
    accepted = correct + wrong
    return {
        "dataset_sha256":dataset_hash, "gallery_concepts":len(gallery),
        "unique_heldout_samples":n, "correct":correct,"wrong":wrong,"abstained":abstained,
        "accuracy":round(correct/n,4) if n else None,
        "coverage":round(accepted/n,4) if n else None,
        "precision_when_recognized":round(correct/accepted,4) if accepted else None,
        "sufficient_for_release":n>=MIN_SAMPLES_RELEASE,
        "conflicting_sha_samples":conflicts,
        "note":("Essai hors échantillon : une vue par objet en référence, autres vues évaluées. "
                "Les exemples ont été confirmés par l'utilisateur, pas audités à l'aveugle ; "
                "cet indicateur ne prouve pas une performance en monde réel.")
    }


def compare_cycles(previous: EvolutionCycle|None, metrics: dict, benchmark: dict,
                   revision: str) -> dict:
    if not previous:
        return {"kind":"initial_baseline", "changes":{},
                "benchmark_comparable":False,
                "note":"Premier relevé : aucune tendance calculable."}
    changes = {k:int(v) - int(previous.metrics.get(k,0))
               for k,v in metrics.items() if isinstance(v, int) and not isinstance(v,bool)
               and isinstance(previous.metrics.get(k),int)}
    comparable = (benchmark["dataset_sha256"] == previous.benchmark.get("dataset_sha256")
                  and benchmark["unique_heldout_samples"] >= MIN_SAMPLES_RELEASE)
    delta = None
    if comparable and benchmark["accuracy"] is not None and previous.benchmark.get("accuracy") is not None:
        delta = round(benchmark["accuracy"]-previous.benchmark["accuracy"],4)
    return {"kind":"follow_up", "previous_cycle_id":previous.id,
            "previous_revision":previous.code_revision,
            "revision_changed":previous.code_revision != revision,
            "changes":changes,"benchmark_comparable":comparable,
            "accuracy_delta":delta,
            "note":("Comparaison sur le même jeu de vues, à interpréter avec la taille de l'échantillon."
                    if comparable else
                    "Jeu de vues modifié ou échantillon insuffisant : aucune conclusion de progrès du modèle.")}


def run_continuous_cycle(db: Session, *, revision: str, date_override=None) -> dict:
    if not REVISION_RE.fullmatch(revision) or revision == "unversioned":
        raise ValueError("Configurer une révision explicite (ex. lifeai-3.3.0 ou SHA Git).")
    now = date_override or datetime.now(timezone.utc)
    day = now.astimezone(timezone.utc).date().isoformat()
    existing = db.scalars(select(EvolutionCycle).where(EvolutionCycle.day_key==day)).first()
    if existing:
        return {"status":"already_run_today", "cycle":cycle_json(existing)}
    last = db.scalars(select(EvolutionCycle).order_by(EvolutionCycle.created_at.desc()).limit(1)).first()
    diagnostic = diagnose(db, once_per_utc_day=True)
    metrics = collect_metrics(db)
    benchmark = visual_benchmark(db)
    trend = compare_cycles(last, metrics, benchmark, revision)
    row = EvolutionCycle(id=str(uuid4()),day_key=day,code_revision=revision,
        metrics=metrics,benchmark=benchmark,trend=trend,
        diagnosis_id=diagnostic.get("run",{}).get("id"))
    db.add(row)
    db.add(Event(id=str(uuid4()),kind="continuous_cycle",details={
        "cycle_id":row.id,"code_revision":revision,
        "benchmark_examples":benchmark["unique_heldout_samples"],
        "benchmark_comparable":trend["benchmark_comparable"]}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalars(select(EvolutionCycle).where(EvolutionCycle.day_key==day)).first()
        if existing:
            return {"status":"already_run_today", "cycle":cycle_json(existing)}
        raise
    return {"status":"completed","cycle":cycle_json(row),
            "diagnosis":diagnostic["status"]}


def assess_release(db: Session, *, proposal_id: str, baseline_id: str,
                   candidate_id: str, tests_total: int, tests_passed: int,
                   artifact_sha256: str, security_review: bool,
                   rollback_prepared: bool) -> dict:
    """Draft a MANUAL deployment dossier from explicitly attested CI evidence.

    Readiness never authorizes merge/deploy; submitted CI metadata is not independently
    verified by this server. Only safe informational flags, no arbitrary commands/files.
    """
    proposal = db.get(ImprovementProposal,proposal_id)
    if not proposal or proposal.status != "approved_for_development":
        raise ValueError("Proposition absente ou non approuvée pour étude")
    base = db.get(EvolutionCycle,baseline_id)
    cand = db.get(EvolutionCycle,candidate_id)
    if not base or not cand:
        raise ValueError("Cycles de référence introuvables")
    if base.id == cand.id or base.code_revision == cand.code_revision:
        raise ValueError("Deux révisions différentes sont nécessaires")
    if tests_total < 0 or tests_passed < 0 or tests_passed > tests_total or tests_total > 20000:
        raise ValueError("Nombre de tests invalide")
    if not re.fullmatch(r"[a-fA-F0-9]{64}",artifact_sha256):
        raise ValueError("Empreinte SHA-256 du rapport CI invalide")
    b = base.benchmark; c=cand.benchmark
    same_dataset = bool(b.get("dataset_sha256")) and b["dataset_sha256"] == c.get("dataset_sha256")
    enough = min(b.get("unique_heldout_samples",0),c.get("unique_heldout_samples",0)) >= MIN_SAMPLES_RELEASE
    no_new_errors = c.get("wrong",0) <= b.get("wrong",0)
    accuracy_ok = (b.get("accuracy") is not None and c.get("accuracy") is not None
                   and c["accuracy"] >= b["accuracy"])
    coverage_ok = (b.get("coverage") is not None and c.get("coverage") is not None
                   and c["coverage"] >= b["coverage"])
    reasons = []
    if not same_dataset: reasons.append("Jeux de données différents : comparaison non valide")
    if not enough: reasons.append(f"Au moins {MIN_SAMPLES_RELEASE} vues indépendantes nécessaires")
    if not no_new_errors: reasons.append("Nombre de fausses correspondances en hausse")
    if not accuracy_ok: reasons.append("Exactitude hors échantillon non améliorée ou inconnue")
    if not coverage_ok: reasons.append("Couverture du système diminuée ou inconnue")
    if tests_total == 0 or tests_total != tests_passed:
        reasons.append("Tests CI non réussis dans leur totalité")
    if not security_review: reasons.append("Revue de sécurité non attestée")
    if not rollback_prepared: reasons.append("Plan de retour arrière non préparé")
    verdict = "eligible_for_human_review" if not reasons else "insufficient_evidence"
    item = ReleaseAssessment(id=str(uuid4()),proposal_id=proposal.id,
        base_revision=base.code_revision,candidate_revision=cand.code_revision,
        evidence={"base_cycle_id":base.id,"candidate_cycle_id":cand.id,
                  "same_dataset":same_dataset,"baseline":b,"candidate":c,
                  "tests_total":tests_total,"tests_passed":tests_passed,
                  "ci_report_sha256":artifact_sha256.lower(),
                  "security_review_attested":security_review,
                  "rollback_prepared_attested":rollback_prepared,
                  "ci_provenance":"operator_attested_not_cryptographically_verified"},
        verdict=verdict,reasons=reasons,status="pending_review")
    db.add(item)
    db.add(Event(id=str(uuid4()), kind="release_assessed", details={
        "id":item.id,"verdict":verdict,"proposal_id":proposal_id}))
    db.commit()
    return assessment_json(item)


def review_assessment(db: Session, item: ReleaseAssessment, *, approve: bool) -> dict:
    if item.status != "pending_review":
        raise ValueError("Ce dossier a déjà été examiné")
    if approve and item.verdict != "eligible_for_human_review":
        raise ValueError("Preuves insuffisantes : approbation interdite")
    item.status = "reviewed_for_manual_release" if approve else "rejected"
    item.reviewed_at = utcnow()
    db.add(Event(id=str(uuid4()),kind="release_reviewed",details={
        "assessment_id":item.id,"approved_manual_review":approve}))
    db.commit()
    return assessment_json(item)
