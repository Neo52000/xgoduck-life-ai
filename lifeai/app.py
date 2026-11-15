"""Life AI V3.3 — memory, diagnostics and controlled evolution. No motor APIs."""
from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import build_engine, session
from .models import Concept, Event, Example, Fact, Observation, ImprovementProposal, DiagnosisRun, EvolutionCycle, ReleaseAssessment, utcnow
from .vision import ImageFeatures, match_score, prepare_image, remote_proposal
from .multiview import VisualReference, compare_references
from .evolution import collect_metrics, diagnose, developer_brief, proposal_json, review, run_json
from .continuous import (cycle_json, assessment_json, run_continuous_cycle,
    assess_release, review_assessment, visual_benchmark)

ROOT = Path(__file__).parent


def newid():
    return str(uuid4())


def stamp(v):
    return v.isoformat() if v else None


def log(db: Session, kind: str, **details):
    db.add(Event(id=newid(), kind=kind, details=details))


def observation_json(o: Observation):
    return {
        "id": o.id, "status": o.status, "source": o.source,
        "image_url": f"/api/images/{o.id}", "candidate_id": o.candidate_id,
        "candidate_label": o.candidate_label, "confidence": o.confidence,
        "notes": o.notes, "error": o.error, "created_at": stamp(o.created_at),
        "analyzed_at": stamp(o.analyzed_at),
    }


def concept_json(c: Concept):
    return {"id": c.id, "label": c.label, "category": c.category,
            "description": c.description, "status": c.status,
            "created_at": stamp(c.created_at), "updated_at": stamp(c.updated_at)}


class ConfirmBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    category: str = Field(default="objet", max_length=80)
    description: str = Field(default="", max_length=1000)


class AddFactBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source_url: str = Field(default="", max_length=500)


class FactReviewBody(BaseModel):
    approve: bool

class EvolutionReviewBody(BaseModel):
    approve: bool


class AssessmentBody(BaseModel):
    proposal_id: str = Field(min_length=36,max_length=36)
    baseline_cycle_id: str = Field(min_length=36,max_length=36)
    candidate_cycle_id: str = Field(min_length=36,max_length=36)
    tests_total: int = Field(ge=0,le=20000)
    tests_passed: int = Field(ge=0,le=20000)
    ci_report_sha256: str = Field(min_length=64,max_length=64)
    security_review_attested: bool = False
    rollback_prepared_attested: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "images").mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="XGO-Duck Life AI", version="0.3.3", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)

    def require_auth(request: Request):
        robot_key = request.headers.get("X-Robot-Key", "")
        if robot_key and secrets.compare_digest(robot_key, settings.robot_api_key):
            return "robot"
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                text = base64.b64decode(header[6:], validate=True).decode("utf-8")
                username, password = text.split(":", 1)
                if secrets.compare_digest(username, settings.admin_user) and secrets.compare_digest(password, settings.admin_password):
                    return "admin"
            except (ValueError, UnicodeError):
                pass
        raise HTTPException(401, "Authentification requise", headers={"WWW-Authenticate": 'Basic realm="XGO-Duck Life AI"'})

    def admin_only(request: Request):
        result = require_auth(request)
        if result != "admin":
            raise HTTPException(403, "Accès administrateur requis")
        return result

    def get_db(request: Request):
        with session(request.app.state.engine) as db:
            yield db

    def check_vision_quota(db: Session):
        if not settings.openai_api_key:
            raise HTTPException(409, "OPENAI_API_KEY absente. Confirmer un objet manuellement, ou configurer la clé.")
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        n = db.scalar(select(func.count(Event.id)).where(Event.kind == "vision_call", Event.created_at >= today)) or 0
        if n >= settings.max_ai_calls_per_day:
            raise HTTPException(429, "Quota d'analyses IA quotidiennes atteint")
        log(db, "vision_call", model=settings.vision_model)
        db.commit()

    def do_analysis(obs_id: str):
        # Background worker opens its own session. A failed call is stored for review.
        with session(app.state.engine) as db:
            obs = db.get(Observation, obs_id)
            if not obs or obs.status == "learned":
                return
            try:
                check_vision_quota(db)
                image = (settings.data_dir / "images" / obs.image_name).read_bytes()
                # Multi-view matching is opt-in because it sends stored confirmed
                # example images as well as the new observation to the AI provider.
                references = []
                if settings.remote_reference_matching and settings.max_reference_images:
                    concept_counts = {}
                    examples = db.scalars(select(Example).order_by(
                        Example.created_at.desc()).limit(100)).all()
                    for ex in examples:
                        concept = db.get(Concept, ex.concept_id)
                        if not concept or concept.status != "confirmed":
                            continue
                        if concept_counts.get(concept.id, 0) >= 2:
                            continue
                        ref_obs = db.get(Observation, ex.observation_id)
                        if not ref_obs:
                            continue
                        filepath = settings.data_dir / "images" / ref_obs.image_name
                        if not filepath.is_file():
                            continue
                        references.append(VisualReference(concept_id=concept.id,
                            label=concept.label, jpeg=filepath.read_bytes()))
                        concept_counts[concept.id] = concept_counts.get(concept.id, 0) + 1
                        if len(references) >= settings.max_reference_images:
                            break
                if references:
                    proposal = compare_references(image, references,
                        settings.openai_api_key, settings.vision_model)
                    matched_id = proposal.get("matched_id", "")
                    matched = db.get(Concept, matched_id) if matched_id else None
                    obs.candidate_id = matched.id if matched else None
                    obs.status = "recognized_candidate" if matched else (
                        "proposed" if proposal.get("label") else "unknown")
                    method = "reference_comparison"
                else:
                    proposal = remote_proposal(image,
                        settings.openai_api_key, settings.vision_model)
                    obs.candidate_id = None
                    obs.status = "proposed" if proposal.get("label") else "unknown"
                    method = "visual_proposal"
                obs.candidate_label = proposal.get("label", "")
                obs.confidence = proposal.get("confidence", 0)
                obs.notes = proposal.get("description", "")
                obs.error = ""
                log(db, "vision_proposal", observation_id=obs.id,
                    label=obs.candidate_label, method=method,
                    matched_concept_id=obs.candidate_id,
                    references_sent=len(references))
            except HTTPException as exc:
                obs.status = "unknown"
                obs.error = str(exc.detail)[:300]
            except Exception as exc:
                obs.status = "unknown"
                # Do not leak HTTP errors with secrets, URLs or service metadata to users.
                obs.error = "Analyse IA indisponible. Vérifier la clé, le réseau et les journaux serveur."
                print(f"Vision error type: {type(exc).__name__}", flush=True)
            finally:
                obs.analyzed_at = utcnow()
                db.commit()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "life-ai", "motors": "disabled"}

    @app.get("/")
    def dashboard(_: str = Depends(admin_only)):
        return FileResponse(ROOT / "static" / "index.html", media_type="text/html", headers={"Cache-Control": "no-store"})

    @app.get("/assets/{filename}")
    def assets(filename: str, _: str = Depends(admin_only)):
        files = {"app.js": ("text/javascript", "app.js"), "style.css": ("text/css", "style.css")}
        if filename not in files:
            raise HTTPException(404)
        media, name = files[filename]
        return FileResponse(ROOT / "static" / name, media_type=media)

    @app.get("/api/state")
    def state(db: Session = Depends(get_db), _: str = Depends(require_auth)):
        counts = {"observations": db.scalar(select(func.count(Observation.id))) or 0,
                  "concepts": db.scalar(select(func.count(Concept.id))) or 0,
                  "facts": db.scalar(select(func.count(Fact.id))) or 0,
                  "pending": db.scalar(select(func.count(Observation.id)).where(Observation.status.in_(["unknown", "proposed", "recognized_candidate"]))) or 0,
                  "verified_facts": db.scalar(select(func.count(Fact.id)).where(Fact.status == "verified")) or 0,
                  "examples": db.scalar(select(func.count(Example.id))) or 0,
                  "pending_facts": db.scalar(select(func.count(Fact.id)).where(Fact.status == "to_review")) or 0}
        recent = db.scalars(select(Observation).order_by(Observation.created_at.desc()).limit(35)).all()
        concepts = db.scalars(select(Concept).order_by(Concept.updated_at.desc()).limit(100)).all()
        events = db.scalars(select(Event).order_by(Event.created_at.desc()).limit(20)).all()
        facts = db.scalars(select(Fact).order_by(Fact.created_at.desc()).limit(30)).all()
        return {"stats": counts, "observations": [observation_json(o) for o in recent],
                "concepts": [concept_json(c) for c in concepts],
                "events": [{"kind": e.kind, "details": e.details, "created_at": stamp(e.created_at)} for e in events],
                "facts": [{"id": f.id, "concept_id": f.concept_id, "text": f.text,
                            "source_url": f.source_url, "status": f.status} for f in facts],
                "ai_enabled": bool(settings.openai_api_key), "auto_vision": settings.auto_vision,
                "remote_reference_matching": settings.remote_reference_matching}

    @app.post("/api/observations", status_code=201)
    async def upload_observation(background_tasks: BackgroundTasks,
                                 file: UploadFile = File(...), source: str = Form("dashboard"),
                                 db: Session = Depends(get_db), _: str = Depends(require_auth)):
        if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, "Formats acceptés : JPEG, PNG, WEBP")
        raw = await file.read(settings.max_image_bytes + 1)
        await file.close()
        if len(raw) > settings.max_image_bytes:
            raise HTTPException(413, "Image supérieure à 5 Mo")
        try:
            feat = prepare_image(raw)
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, str(exc)) from exc
        oid = newid()
        name = f"{oid}.jpg"
        (settings.data_dir / "images" / name).write_bytes(feat.jpeg)
        best_id, best_label, best_score = None, "", 0.0
        examples = db.scalars(select(Example).order_by(Example.created_at.desc()).limit(500)).all()
        for ex in examples:
            score = match_score(feat, ex)
            if score > best_score:
                concept = db.get(Concept, ex.concept_id)
                if concept:
                    best_id, best_label, best_score = concept.id, concept.label, score
        if best_score < 0.78:
            best_id, best_label, best_score = None, "", 0.0
        status = "recognized_candidate" if best_id else "unknown"
        obs = Observation(id=oid, image_name=name, sha256=feat.sha256, dhash=feat.dhash,
                          histogram=feat.histogram, texture=feat.texture, status=status,
                          source=source[:50], candidate_id=best_id, candidate_label=best_label,
                          confidence=best_score)
        db.add(obs)
        log(db, "observation_received", observation_id=oid, status=status, source=source[:50])
        db.commit()
        db.refresh(obs)
        if status == "unknown" and settings.auto_vision and settings.openai_api_key:
            background_tasks.add_task(do_analysis, oid)
        return observation_json(obs)

    @app.get("/api/images/{observation_id}")
    def image(observation_id: str, db: Session = Depends(get_db), _: str = Depends(require_auth)):
        obs = db.get(Observation, observation_id)
        if not obs:
            raise HTTPException(404, "Image introuvable")
        return FileResponse(settings.data_dir / "images" / obs.image_name, media_type="image/jpeg",
                            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/api/observations/{observation_id}/analyze")
    def analyze(observation_id: str, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        obs = db.get(Observation, observation_id)
        if not obs:
            raise HTTPException(404)
        if obs.status == "learned":
            raise HTTPException(409, "Cette observation a déjà été confirmée")
        if not settings.openai_api_key:
            raise HTTPException(409, "Configurer OPENAI_API_KEY pour l'identification automatique")
        do_analysis(observation_id)
        db.expire_all()
        with session(app.state.engine) as fresh:
            return observation_json(fresh.get(Observation, observation_id))

    @app.post("/api/observations/{observation_id}/confirm")
    def confirm(observation_id: str, body: ConfirmBody, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        obs = db.get(Observation, observation_id)
        if not obs:
            raise HTTPException(404, "Observation introuvable")
        label = " ".join(body.label.strip().split())
        if not label:
            raise HTTPException(422, "Nom vide")
        concept = db.scalars(select(Concept).where(func.lower(Concept.label) == label.casefold())).first()
        if concept is None:
            concept = Concept(id=newid(), label=label, category=body.category.strip() or "objet",
                              description=body.description.strip(), status="confirmed")
            db.add(concept)
            db.flush()
        elif body.description.strip() and not concept.description:
            concept.description = body.description.strip()
        old = db.scalars(select(Example).where(Example.observation_id == obs.id)).first()
        exact_already_learned = db.scalars(select(Example).where(
            Example.concept_id == concept.id, Example.sha256 == obs.sha256)).first()
        if old:
            old.concept_id = concept.id
        elif not exact_already_learned:
            # Avoid multiplying the same training image in visual memory.
            db.add(Example(id=newid(), concept_id=concept.id, observation_id=obs.id, sha256=obs.sha256,
                           dhash=obs.dhash, histogram=obs.histogram, texture=obs.texture))
        # A candidate corrected by a human is a measurable model error.
        if obs.candidate_label and obs.candidate_label.casefold().strip() != label.casefold():
            log(db, "vision_corrected", observation_id=obs.id,
                previous_label=obs.candidate_label[:120], confirmed_label=label[:120])
        obs.status = "learned"
        obs.candidate_id = concept.id
        obs.candidate_label = concept.label
        obs.confidence = 1.0  # confidence in the human label, not a classifier probability
        obs.notes = body.description.strip() or obs.notes
        log(db, "confirmed_learning", concept_id=concept.id, observation_id=obs.id, label=label)
        db.commit()
        return {"concept": concept_json(concept), "observation": observation_json(obs)}

    @app.delete("/api/observations/{observation_id}")
    def delete_observation(observation_id: str, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        obs = db.get(Observation, observation_id)
        if not obs:
            raise HTTPException(404)
        image_name = obs.image_name
        db.delete(obs)
        log(db, "observation_deleted", observation_id=observation_id)
        db.commit()
        (settings.data_dir / "images" / image_name).unlink(missing_ok=True)
        return {"deleted": observation_id}

    @app.delete("/api/concepts/{concept_id}")
    def delete_concept(concept_id: str, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        c = db.get(Concept, concept_id)
        if not c:
            raise HTTPException(404)
        related = db.scalars(select(Observation).where(Observation.candidate_id == concept_id)).all()
        for o in related:
            o.candidate_id = None
            o.candidate_label = ""
            o.status = "unknown"
            o.confidence = 0
        db.delete(c)
        log(db, "concept_deleted", concept_id=concept_id)
        db.commit()
        return {"deleted": concept_id}

    @app.get("/api/concepts/{concept_id}")
    def concept_detail(concept_id: str, db: Session = Depends(get_db), _: str = Depends(require_auth)):
        c = db.get(Concept, concept_id)
        if not c:
            raise HTTPException(404)
        ex = db.scalars(select(Example).where(Example.concept_id == concept_id)).all()
        facts = db.scalars(select(Fact).where(Fact.concept_id == concept_id)).all()
        return {**concept_json(c), "example_count": len(ex),
                "facts": [{"id": f.id, "text": f.text, "source_url": f.source_url, "status": f.status} for f in facts]}

    @app.post("/api/concepts/{concept_id}/facts")
    def add_fact(concept_id: str, body: AddFactBody, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        if not db.get(Concept, concept_id):
            raise HTTPException(404)
        if body.source_url and not body.source_url.startswith("https://"):
            raise HTTPException(422, "URL de source HTTPS requise")
        fact = Fact(id=newid(), concept_id=concept_id, text=body.text.strip(), source_url=body.source_url,
                    status="verified")
        db.add(fact)
        log(db, "fact_added", fact_id=fact.id, concept_id=concept_id)
        db.commit()
        return {"id": fact.id, "status": fact.status}

    def research_concept(db: Session, concept: Concept):
        """Retrieve an encyclopedic *draft*, never silently verify it."""
        if not settings.allow_wikipedia:
            raise HTTPException(403, "Recherche encyclopédique désactivée")
        # Fixed trusted host. Never request user-provided URLs (SSRF prevention).
        try:
            response = httpx.get("https://fr.wikipedia.org/w/api.php", params={
                "action": "query", "format": "json", "prop": "extracts", "exintro": "1",
                "explaintext": "1", "redirects": "1", "titles": concept.label,
            }, headers={"User-Agent": "XGODuckLifeAI/0.2 (educational personal robot project; github.com/LuwuDynamics/xgoduck_hardware)"},
                timeout=12.0, follow_redirects=False)
            response.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(503, "Encyclopédie inaccessible ; aucun fait créé")
        try:
            pages = response.json().get("query", {}).get("pages", {})
            page = next((v for v in pages.values() if v.get("pageid") and v.get("extract")), None)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(502, "Réponse encyclopédique invalide")
        if not page:
            raise HTTPException(404, "Pas d'article encyclopédique identifié ; aucune connaissance ajoutée")
        title = str(page.get("title", concept.label))
        from urllib.parse import quote
        url = "https://fr.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="()_-." )
        extract = " ".join(page["extract"].split())[:1000]
        existing = db.scalars(select(Fact).where(Fact.concept_id == concept.id,
                                Fact.source_url == url)).first()
        if existing:
            return {"id": existing.id, "text": existing.text, "status": existing.status,
                    "source_url": url, "duplicate": True}
        fact = Fact(id=newid(), concept_id=concept.id, text=extract,
                    source_url=url, status="to_review")
        db.add(fact)
        log(db, "research_proposal", concept_id=concept.id, source_url=url)
        db.commit()
        return {"id": fact.id, "text": extract, "status": "to_review", "source_url": url,
                "duplicate": False}

    @app.post("/api/concepts/{concept_id}/research")
    def research(concept_id: str, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        concept = db.get(Concept, concept_id)
        if not concept:
            raise HTTPException(404)
        return research_concept(db, concept)

    @app.post("/api/learning/cycle")
    def learning_cycle(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        """One bounded curiosity cycle, not autonomous unlimited web crawling.

        One cycle per UTC day; at most N missing concepts, Wikipedia only.
        Results stay `to_review`. An administrator may trigger this via cron.
        """
        if not settings.allow_wikipedia:
            raise HTTPException(403, "Recherche désactivée")
        today = datetime.now(timezone.utc).replace(hour=0, minute=0,
            second=0, microsecond=0)
        ran_today = db.scalar(select(func.count(Event.id)).where(
            Event.kind == "research_cycle", Event.created_at >= today)) or 0
        if ran_today:
            return {"status": "already_run_today", "processed": 0, "proposals": [],
                    "note": "Un seul cycle de curiosité par jour UTC"}
        # Record *before* network calls, so a client retry won't launch
        # another batch when a provider is unavailable.
        log(db, "research_cycle", limit=settings.max_research_per_cycle)
        db.commit()
        candidates = db.scalars(select(Concept).where(~Concept.id.in_(
            select(Fact.concept_id))).order_by(Concept.created_at.asc())
            .limit(settings.max_research_per_cycle)).all()
        output = []
        for concept in candidates:
            try:
                item = research_concept(db, concept)
                output.append({"concept_id": concept.id, "label": concept.label,
                               "result": "to_review", "fact_id": item["id"]})
            except HTTPException as exc:
                output.append({"concept_id": concept.id, "label": concept.label,
                               "result": "not_found_or_unavailable", "http_status": exc.status_code})
        log(db, "research_cycle_finished", processed=len(output))
        db.commit()
        return {"status": "completed", "processed": len(output), "proposals": output,
                "note": "Les nouvelles connaissances exigent une validation explicite"}

    @app.get("/api/learning/report")
    def learning_report(db: Session = Depends(get_db), _: str = Depends(require_auth)):
        """Measurable metrics, not claims that the AI has become intelligent."""
        concept_counts = db.execute(select(Example.concept_id, func.count(Example.id))
                                    .group_by(Example.concept_id)).all()
        local_matches = db.scalar(select(func.count(Event.id)).where(
            Event.kind == "observation_received")) or 0
        candidate_matches = db.scalar(select(func.count(Observation.id)).where(
            Observation.status == "recognized_candidate")) or 0
        proposals = db.scalar(select(func.count(Event.id)).where(
            Event.kind == "vision_proposal")) or 0
        return {"confirmed_concepts": db.scalar(select(func.count(Concept.id))) or 0,
                "confirmed_examples": sum(int(n) for _, n in concept_counts),
                "concepts_with_multiple_views": sum(int(n >= 2) for _, n in concept_counts),
                "observations_received": local_matches,
                "currently_recognized_candidates": candidate_matches,
                "external_vision_proposals": proposals,
                "verified_facts": db.scalar(select(func.count(Fact.id)).where(
                    Fact.status == "verified")) or 0,
                "pending_facts": db.scalar(select(func.count(Fact.id)).where(
                    Fact.status == "to_review")) or 0,
                "note": "Les correspondances visuelles et la confiance IA ne prouvent pas la fiabilité hors échantillon."}

    @app.get("/api/robot/knowledge")
    def robot_knowledge(db: Session = Depends(get_db), _: str = Depends(require_auth)):
        """Read-only verified memory snapshot. Contains no image or motor command."""
        concepts = db.scalars(select(Concept).where(Concept.status == "confirmed")
                              .order_by(Concept.label.asc())).all()
        facts = db.scalars(select(Fact).where(Fact.status == "verified")).all()
        facts_by_concept = {}
        for fact in facts:
            facts_by_concept.setdefault(fact.concept_id, []).append({
                "text": fact.text, "source_url": fact.source_url})
        return {"schema_version": 2, "generated_at": utcnow().isoformat(),
                "concepts": [{"id": c.id, "label": c.label,
                              "category": c.category, "description": c.description,
                              "facts": facts_by_concept.get(c.id, [])} for c in concepts]}

    @app.post("/api/facts/{fact_id}/review")
    def review_fact(fact_id: str, body: FactReviewBody, db: Session = Depends(get_db), _: str = Depends(admin_only)):
        f = db.get(Fact, fact_id)
        if not f:
            raise HTTPException(404)
        f.status = "verified" if body.approve else "rejected"
        log(db, "fact_reviewed", fact_id=f.id, approved=body.approve)
        db.commit()
        return {"id": f.id, "status": f.status}

    @app.get("/api/curiosity")
    def curiosity(db: Session = Depends(get_db), _: str = Depends(require_auth)):
        unknowns = db.scalars(select(Observation).where(Observation.status.in_(["unknown", "proposed", "recognized_candidate"]))
                              .order_by(Observation.created_at.desc()).limit(15)).all()
        to_review = db.scalars(select(Fact).where(Fact.status == "to_review")
                               .order_by(Fact.created_at.desc()).limit(10)).all()
        return {"tasks": [
            *[{"kind": "identify", "id": o.id, "summary": f"Identifier ou confirmer : {o.candidate_label or 'objet inconnu'}"} for o in unknowns],
            *[{"kind": "review_fact", "id": f.id, "summary": "Vérifier une connaissance issue de recherche"} for f in to_review]
        ], "note": "La curiosité V1 propose des tâches ; elle ne lance pas de recherches illimitées."}

    @app.get("/api/evolution")
    def evolution_state(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        proposals = db.scalars(select(ImprovementProposal).order_by(
            ImprovementProposal.created_at.desc()).limit(100)).all()
        runs = db.scalars(select(DiagnosisRun).order_by(
            DiagnosisRun.created_at.desc()).limit(15)).all()
        return {"metrics": collect_metrics(db),
                "proposals": [proposal_json(p) for p in proposals],
                "runs": [run_json(r) for r in runs],
                "mode": "supervised", "code_execution": False,
                "automatic_deployment": False, "motor_control": False}

    @app.post("/api/evolution/diagnose")
    def evolution_diagnose(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        return diagnose(db)

    @app.post("/api/evolution/proposals/{proposal_id}/review")
    def evolution_review(proposal_id: str, body: EvolutionReviewBody,
                         db: Session = Depends(get_db), _: str = Depends(admin_only)):
        proposal = db.get(ImprovementProposal, proposal_id)
        if proposal is None:
            raise HTTPException(404, "Proposition introuvable")
        try:
            return review(db, proposal, approve=body.approve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/evolution/proposals/{proposal_id}/brief")
    def evolution_brief(proposal_id: str, db: Session = Depends(get_db),
                        _: str = Depends(admin_only)):
        proposal = db.get(ImprovementProposal, proposal_id)
        if proposal is None:
            raise HTTPException(404, "Proposition introuvable")
        return PlainTextResponse(developer_brief(proposal),
            media_type="text/markdown; charset=utf-8",
            headers={"Cache-Control":"no-store", "Content-Disposition":
                f'attachment; filename="lifeai-improvement-{proposal_id}.md"'})

    # V3.3: scheduled one-shot observations only. No autonomous deployment.
    @app.get("/api/evolution/continuous")
    def continuous_state(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        cycles = db.scalars(select(EvolutionCycle).order_by(
            EvolutionCycle.created_at.desc()).limit(45)).all()
        releases = db.scalars(select(ReleaseAssessment).order_by(
            ReleaseAssessment.created_at.desc()).limit(40)).all()
        return {"cycles": [cycle_json(c) for c in cycles],
                "release_assessments": [assessment_json(a) for a in releases],
                "revision": settings.code_revision,
                "mode": "human_review_only", "auto_deploy": False,
                "auto_merge": False, "motor_control": False}

    @app.post("/api/evolution/continuous/cycle")
    def continuous_cycle(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        try:
            return run_continuous_cycle(db, revision=settings.code_revision)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/evolution/benchmark")
    def continuous_benchmark(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        return visual_benchmark(db)

    @app.post("/api/evolution/releases/assess")
    def continuous_assess(body: AssessmentBody, db: Session = Depends(get_db),
                          _: str = Depends(admin_only)):
        try:
            return assess_release(db, proposal_id=body.proposal_id,
                baseline_id=body.baseline_cycle_id,
                candidate_id=body.candidate_cycle_id,
                tests_total=body.tests_total,tests_passed=body.tests_passed,
                artifact_sha256=body.ci_report_sha256,
                security_review=body.security_review_attested,
                rollback_prepared=body.rollback_prepared_attested)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/evolution/releases/{assessment_id}/review")
    def continuous_release_review(assessment_id: str, body: EvolutionReviewBody,
                            db: Session = Depends(get_db), _: str = Depends(admin_only)):
        item = db.get(ReleaseAssessment, assessment_id)
        if not item:
            raise HTTPException(404, "Dossier de version introuvable")
        try:
            return review_assessment(db, item, approve=body.approve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/export")
    def export(db: Session = Depends(get_db), _: str = Depends(admin_only)):
        concepts = db.scalars(select(Concept)).all()
        obs = db.scalars(select(Observation)).all()
        facts = db.scalars(select(Fact)).all()
        return JSONResponse({"exported_at": utcnow().isoformat(), "concepts": [concept_json(c) for c in concepts],
                             "observations": [observation_json(o) for o in obs],
                             "facts": [{"concept_id": f.concept_id, "text": f.text, "source_url": f.source_url,
                                        "status": f.status} for f in facts],
                             "warning": "Export JSON des métadonnées seulement ; sauvegarder aussi la base et les images."},
                            headers={"Content-Disposition": 'attachment; filename="lifeai_memory.json"'})

    return app


app = create_app()
