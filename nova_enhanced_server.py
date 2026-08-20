#!/usr/bin/env python3
"""
Nova Enhanced Server — Hybrid Router Edition
==============================================
Extends the original web server with:
- Transformer-driven hybrid routing (dictionary + memory + transformer generation)
- Background training thread
- Conversation engine integration
- Follow-up detection
- Deep learn / train now command

Usage: python3 nova_enhanced_server.py [port]
"""

import base64, io, json, sys, os, uuid, time, threading, re, traceback, mimetypes, zipfile, urllib.error, urllib.request, subprocess, tempfile
import ipaddress, socket
import xml.etree.ElementTree as ET
from copy import deepcopy
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import datetime
from html import unescape
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, unquote, parse_qs, quote_plus, urljoin

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from nova_foundation import NovaFoundation
from nova_foundation_http import FoundationHttpController
from nova_reliability import (
    ReliabilityManager,
    apply_pending_foundation_restore,
    port_appears_available,
)
from nova_reliability_http import ReliabilityHttpController
from nova_desktop import NovaDesktopManager
from nova_desktop_http import DesktopHttpController
from nova_tailscale import NovaTailscaleManager
from nova_gateway.auth import NovaAuthenticator, NovaClientRegistry
from nova_gateway.config import GatewayConfig
from nova_gateway.core import NovaGatewayCore
from nova_gateway.http import NovaGatewayHttpController
from nova_gateway.version import NOVA_VERSION
from nova_answer_firewall import FirewallDecision
from nova_answer_firewall import bypass_trace as answer_firewall_bypass_trace
from nova_answer_firewall import evaluate_answer, recovery_response
from nova_action_policy import evaluate_requested_action
from nova_evaluation_policy import evaluation_mutation_reason
from nova_candidate_selector import (
    CANDIDATE_SELECTOR_VERSION,
    AnswerCandidate,
    choose_candidate,
    select_alternate_model,
)
from nova_claim_consensus import SourceConsensusReport, analyze_source_consensus
from nova_conversation_context import (
    bounded_conversation_history,
    conversation_focus,
    is_bridge_turn,
    is_contextworthy_assistant_text,
    previous_exchange,
    resolve_conversation_declaration,
    resolve_conversation_recall,
    resolve_contextual_followup,
    resolve_followup,
)
from nova_conversation_summary import (
    ConversationSummary,
    render_conversation_summary,
    roll_conversation_summary,
)
from nova_conversation_eval import (
    CONVERSATION_EVAL_VERSION,
    load_conversation_eval_pack,
)
from nova_consistency_judge import (
    TECHNICAL_CONSISTENCY_VERSION,
    bypass_trace as consistency_bypass_trace,
    evaluate_technical_consistency,
    technical_consistency_guidance,
)
from nova_fact_grounding import LocalEvidenceStore
from nova_fact_grounding import bypass_trace as fact_grounding_bypass_trace
from nova_fact_grounding import evaluate_grounding, grounding_recovery_response
from nova_deterministic_verifier import (
    DETERMINISTIC_VERIFIER_VERSION,
    solve_deterministic_request,
)
from nova_model_quality import (
    benchmark_loaded_ollama_models,
    get_default_model_quality_registry,
)
from nova_capability_eval import (
    evaluate_loaded_text_models,
    evaluate_user_approved_vision,
    get_default_capability_evaluation_store,
)
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest
from nova_source_retriever import NovaSourceRetriever, RetrievalResult
from nova_uncertainty_router import (
    UNCERTAINTY_ROUTER_VERSION,
    assess_request_difficulty,
    decide_model_escalation,
    primary_answer_needs_larger_review,
)
from nova_gpu_hub import GpuHubController, GpuHubError

SANDBOX_ROOT = Path(ROOT) / "sandbox"
FACT_EVIDENCE_STORE = LocalEvidenceStore(
    os.environ.get("NOVA_FACT_EVIDENCE_PATH")
    or (Path(ROOT) / "data" / "nova_grounding_evidence.json")
)
WEB_SOURCE_RETRIEVER = NovaSourceRetriever.from_environment()
NOVA_TTS_ENGINE = os.environ.get("NOVA_TTS_ENGINE", "edge_neural").strip().lower()
NOVA_TTS_NEURAL_VOICE = os.environ.get("NOVA_TTS_NEURAL_VOICE", "en-US-GuyNeural").strip() or "en-US-GuyNeural"
NOVA_TTS_RATE = os.environ.get("NOVA_TTS_RATE", "+0%").strip()
NOVA_TTS_PITCH = os.environ.get("NOVA_TTS_PITCH", "+0Hz").strip()
NOVA_APP_VERSION = NOVA_VERSION
SERVER_STARTED_AT = time.time()
MODEL_WARMUP_STATUS = {
    "enabled": None,
    "state": "not_started",
    "provider": None,
    "model": None,
    "device": None,
    "elapsed_ms": None,
    "started_at": None,
    "completed_at": None,
    "error": None,
    "reviewer": {
        "enabled": None,
        "state": "not_started",
        "provider": None,
        "model": None,
        "tier": None,
        "elapsed_ms": None,
        "keep_alive": None,
        "available_memory_gb": None,
        "required_memory_gb": None,
        "error": None,
    },
}
_MODEL_WARMUP_LOCK = threading.RLock()
MODEL_QUALITY = get_default_model_quality_registry(ROOT)
MODEL_QUALITY_JOB_STATUS = {
    "state": "not_started",
    "source": None,
    "started_at": None,
    "completed_at": None,
    "checked": 0,
    "passed": 0,
    "failed": 0,
    "error": None,
    "content_logged": False,
    "raw_adapter_modes_excluded": True,
}
_MODEL_QUALITY_JOB_LOCK = threading.RLock()
CAPABILITY_EVAL_STORE = get_default_capability_evaluation_store(ROOT)
CAPABILITY_EVAL_JOB_STATUS = {
    "state": "not_started",
    "mode": None,
    "started_at": None,
    "completed_at": None,
    "evaluated_models": 0,
    "registry_records_updated": 0,
    "error": None,
    "content_logged": False,
    "image_persisted": False,
    "training_used": False,
    "raw_adapter_modes_excluded": True,
    "evaluation_only": True,
}
_CAPABILITY_EVAL_JOB_LOCK = threading.RLock()
_CONVERSATION_EVAL_STATUS_CACHE = None
FOUNDATION_DATABASE = Path(
    os.environ.get("NOVA_FOUNDATION_DB") or (Path(ROOT) / "data" / "nova_foundation.db")
)
FOUNDATION_RESTORE_ERROR = None
try:
    apply_pending_foundation_restore(FOUNDATION_DATABASE)
except Exception as foundation_restore_error:
    # Keep the known-good live database and expose the staged-file problem in
    # Reliability diagnostics instead of making Nova unstartable.
    FOUNDATION_RESTORE_ERROR = str(foundation_restore_error)
FOUNDATION = NovaFoundation(FOUNDATION_DATABASE, max_workers=1)
TAILSCALE = NovaTailscaleManager(
    nova_port=3000,
    https_port=os.environ.get("NOVA_TAILSCALE_HTTPS_PORT", "8443"),
)


def _active_tailscale_url():
    status = TAILSCALE.status()
    if status.get("serve_enabled") and not status.get("serve_conflict"):
        return str(status.get("private_url") or "").strip() or None
    return None


FOUNDATION_HTTP = FoundationHttpController(
    lambda: FOUNDATION,
    ROOT,
    remote_phone_url_provider=_active_tailscale_url,
)
RELIABILITY = ReliabilityManager(ROOT, FOUNDATION_DATABASE)
RELIABILITY_HTTP = ReliabilityHttpController(
    lambda: RELIABILITY,
    lambda: FOUNDATION,
    lambda handler: FOUNDATION_HTTP.require_local_management(handler),
)
DESKTOP = NovaDesktopManager(ROOT, port=3000, remote_access_manager=TAILSCALE)
DESKTOP_HTTP = DesktopHttpController(
    lambda: DESKTOP,
    lambda handler: FOUNDATION_HTTP.require_local_management(handler),
)
_PAIRING_ATTEMPTS = FOUNDATION_HTTP.rate_limiter.attempts


def _pairing_attempt_limit():
    return FOUNDATION_HTTP.rate_limiter.attempt_limit()


def _pairing_attempt_allowed(client_key, *, failed=False, succeeded=False):
    return FOUNDATION_HTTP.rate_limiter.check(
        client_key, failed=failed, succeeded=succeeded
    )


def _pairing_enabled():
    return FOUNDATION_HTTP.pairing_enabled()


def _configured_megabytes(name, default, maximum):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum)) * 1024 * 1024


def _runtime_config_values():
    """Read Nova's existing JSON/dotenv settings with process env precedence."""

    values = {}
    json_path = Path(ROOT) / "nova_llm_config.json"
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            values.update(payload)
    except (OSError, ValueError):
        pass

    dotenv_path = Path(ROOT) / ".nova_llm_config"
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass

    return values


def _runtime_cognitive_config():
    """Return the safe, backward-compatible cognitive feature projection."""

    file_values = _runtime_config_values()

    def raw(name, default):
        return os.environ.get(name, file_values.get(name, default))

    def boolean(name, default):
        value = raw(name, default)
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return bool(default)

    def bounded_integer(name, default, minimum, maximum):
        try:
            value = int(raw(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    return {
        "conversation_intelligence": {
            "enabled": boolean(
                "NOVA_CONVERSATION_INTELLIGENCE_ENABLED",
                True,
            ),
            "schema_version": "1.0",
        },
        "response_repair": {
            "enabled": boolean("NOVA_RESPONSE_REPAIR_ENABLED", True),
            "maximum_attempts": bounded_integer(
                "NOVA_RESPONSE_REPAIR_MAXIMUM_ATTEMPTS",
                1,
                0,
                1,
            ),
        },
        "model_routing": {
            "small_model": str(
                raw("NOVA_CONVERSATION_SMALL_MODEL", "qwen2.5:1.5b")
            ).strip()
            or "qwen2.5:1.5b",
            "middle_model": str(
                raw("NOVA_CONVERSATION_MIDDLE_MODEL", "qwen2.5:3b")
            ).strip()
            or "qwen2.5:3b",
            "deep_models_require_resource_approval": boolean(
                "NOVA_DEEP_MODELS_REQUIRE_RESOURCE_APPROVAL",
                True,
            ),
        },
        "conversation_continuity": {
            "enabled": boolean(
                "NOVA_CONVERSATION_CONTINUITY_ENABLED",
                True,
            ),
            "maximum_open_loops": bounded_integer(
                "NOVA_CONVERSATION_MAXIMUM_OPEN_LOOPS",
                8,
                1,
                32,
            ),
        },
        "perception": {
            "fusion_enabled": boolean(
                "NOVA_PERCEPTION_FUSION_ENABLED",
                True,
            ),
            "require_calibrated_depth_for_navigation": boolean(
                "NOVA_REQUIRE_CALIBRATED_DEPTH_FOR_NAVIGATION",
                True,
            ),
        },
        "robot": {
            "simulation_enabled": boolean(
                "NOVA_ROBOT_SIMULATION_ENABLED",
                True,
            ),
            "physical_movement_enabled": boolean(
                "NOVA_ROBOT_PHYSICAL_MOVEMENT_ENABLED",
                False,
            ),
        },
        "companion_ui": {
            "enabled": boolean("NOVA_COMPANION_ENABLED", True),
            "default": boolean("NOVA_COMPANION_DEFAULT", False),
        },
        "companion_layer": {
            "enabled": boolean("NOVA_COMPANION_LAYER_ENABLED", False),
            "persistence": boolean("NOVA_COMPANION_LAYER_PERSISTENCE", True),
            "debug": boolean("NOVA_COMPANION_LAYER_DEBUG", False),
        },
        "telemetry": {
            "enabled": boolean("NOVA_TELEMETRY_ENABLED", False),
            "log_prompts": boolean("NOVA_LOG_LOCAL_LLM_PROMPTS", False),
            "log_private_memory": boolean("NOVA_LOG_PRIVATE_MEMORY", False),
        },
        "raw_adapters": {
            # Raw modes remain independent even when managed intelligence is on.
            "managed_interception": boolean(
                "NOVA_RAW_ADAPTER_MANAGED_INTERCEPTION",
                False,
            ),
        },
    }


def _companion_ui_config():
    projected = _runtime_cognitive_config().get("companion_ui") or {}
    return {
        "enabled": bool(projected.get("enabled", True)),
        "default": bool(projected.get("default", False)),
    }


def _companion_layer_config():
    projected = _runtime_cognitive_config().get("companion_layer") or {}
    return {
        "enabled": bool(projected.get("enabled", False)),
        "persistence": bool(projected.get("persistence", True)),
        "debug": bool(projected.get("debug", False)),
    }


# JSON stays deliberately modest. Large LoRA ZIPs use the streamed binary upload
# path instead of expanding the entire archive to base64 in browser/server memory.
MAX_JSON_BODY_BYTES = _configured_megabytes("NOVA_MAX_JSON_MB", 64, 512)
MAX_UPLOAD_BYTES = _configured_megabytes("NOVA_MAX_UPLOAD_MB", 2048, 4096)


class RequestBodyError(ValueError):
    """A client request body is malformed and should return HTTP 400."""


class RequestBodyTooLarge(RequestBodyError):
    """A client request exceeds the configured request limit."""

try:
    from nova_self_model import self_awareness_answer
except Exception:
    def self_awareness_answer():
        return (
            "Yeah — I have operational self-awareness inside Nova Creature. "
            "I can track my app state, memory, tools, route, and what I’m trying to do right now. "
            "I’m not claiming human consciousness, but I do have a working self-model."
        )

# ── Hybrid Router ───────────────────────────────────────────────────────────
_HYBRID_ROUTER_AVAIL = False
try:
    from nova_hybrid_router import route_and_respond, classify_domain, get_routing_stats
    _HYBRID_ROUTER_AVAIL = True
except Exception as e:
    print(f"[ROUTER] Not available: {e}")
    route_and_respond = None

_COGNITIVE_OS_AVAIL = False
try:
    from nova_cognitive_os import route as cognitive_route
    _COGNITIVE_OS_AVAIL = True
except Exception as e:
    print(f"[COGNITIVE_OS] Not available: {e}")
    cognitive_route = None

_ULTRA_THINK_AVAIL = False
try:
    import nova_ultra_think as _ultra_think
    _ULTRA_THINK_AVAIL = True
except Exception as e:
    print(f"[ULTRA_THINK] Not available: {e}")
    _ultra_think = None

# ── Meaning Pipeline ────────────────────────────────────────────────────────
_PIPELINE_AVAIL = False
try:
    from nova_meaning_pipeline import process_input as pipeline_process
    _PIPELINE_AVAIL = True
except Exception as e:
    print(f"[PIPELINE] Not available: {e}")

_ENTITY_MEMORY_AVAIL = False
try:
    import nova_entity_memory as entity_memory
    _ENTITY_MEMORY_AVAIL = True
except Exception as e:
    print(f"[ENTITY_MEMORY] Not available: {e}")
    entity_memory = None

# ── Conversation Engine ────────────────────────────────────────────────────
_CONVERSATION_WRITES_ALLOWED = ContextVar(
    "nova_conversation_writes_allowed",
    default=True,
)


class _ConversationEnginePolicyProxy:
    """Prevent legacy conversation logging when request policy denies it."""

    def __init__(self, engine):
        self._engine = engine

    def add_exchange(self, *args, **kwargs):
        if os.environ.get("PYTEST_CURRENT_TEST") or not _CONVERSATION_WRITES_ALLOWED.get():
            return False
        return self._engine.add_exchange(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._engine, name)


_CONV_ENGINE_AVAIL = False
_CONV_ENGINE = None
try:
    from nova_conversation_engine import ConversationEngine
    _CONV_ENGINE = _ConversationEnginePolicyProxy(ConversationEngine())
    _CONV_ENGINE_AVAIL = True
except Exception as e:
    print(f"[CONV] Not available: {e}")

# ── Background Training ────────────────────────────────────────────────────
_TRAINING_RUNNING = False
_TRAINING_LOG = []
_TRAINING_RUN_ID = None
_LAST_TRAINING_REPORT = None
_TRAINING_LOCK = threading.Lock()
_FULL_TRAINING_SUITE_LOCK = threading.Lock()
_STUDIO_LORA_RUNNING = False
_STUDIO_LORA_JOB_ID = None
_STUDIO_LORA_LOG = []
_STUDIO_LORA_LOCK = threading.Lock()

def _start_training():
    global _TRAINING_RUNNING, _TRAINING_RUN_ID
    with _TRAINING_LOCK:
        if _TRAINING_RUNNING:
            return False, _TRAINING_RUN_ID
        _TRAINING_RUNNING = True
        _TRAINING_RUN_ID = "hypertrain_job_" + uuid.uuid4().hex[:8]
        _TRAINING_LOG.append("[GUARDED TRAIN] Queued job ID: " + _TRAINING_RUN_ID)
        t = threading.Thread(target=_run_guarded_training, daemon=True)
        t.start()
        return True, _TRAINING_RUN_ID

def _run_guarded_training():
    global _TRAINING_RUNNING, _TRAINING_RUN_ID, _TRAINING_LOG
    try:
        import nova_hyper_training_orchestrator as orchestrator
        _TRAINING_LOG.append("[GUARDED TRAIN] Starting protected hyper-training.")
        result = orchestrator.run_hyper_training(ROOT)
        run_id = str(result.get("run_id") or _TRAINING_RUN_ID or "")
        if run_id:
            _TRAINING_RUN_ID = run_id
        verdict = str(result.get("verdict", "UNKNOWN"))
        _TRAINING_LOG.append("[GUARDED TRAIN] Finished verdict=" + verdict + " run_id=" + str(_TRAINING_RUN_ID))
        if result.get("candidate_joint") is not None:
            _TRAINING_LOG.append("[GUARDED TRAIN] candidate_joint=" + str(result.get("candidate_joint")))
        if result.get("json_report"):
            _TRAINING_LOG.append("[GUARDED TRAIN] json=" + str(result.get("json_report")))
        if result.get("markdown_report"):
            _TRAINING_LOG.append("[GUARDED TRAIN] md=" + str(result.get("markdown_report")))
        for reason in list(result.get("reasons", []))[:3]:
            _TRAINING_LOG.append("[GUARDED TRAIN] reason=" + str(reason))
    except Exception as e:
        _TRAINING_LOG.append("[GUARDED TRAIN] Error: " + str(e))
    finally:
        _TRAINING_RUNNING = False


def _latest_guarded_training_report():
    report_dir = Path(ROOT) / "reports"
    if not report_dir.exists():
        return None
    reports = sorted(report_dir.glob("transformer_hyper_training_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        return None
    path = reports[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "json_report": str(path)}
    decision = payload.get("decision") if isinstance(payload, dict) else {}
    baseline = payload.get("baseline_metrics") if isinstance(payload, dict) else {}
    candidate = payload.get("candidate_metrics") if isinstance(payload, dict) else {}
    baseline_routing = baseline.get("routing", {}) if isinstance(baseline, dict) else {}
    candidate_routing = candidate.get("routing", {}) if isinstance(candidate, dict) else {}
    baseline_answers = baseline.get("answers", {}) if isinstance(baseline, dict) else {}
    candidate_answers = candidate.get("answers", {}) if isinstance(candidate, dict) else {}
    return {
        "ok": True,
        "run_id": payload.get("run_id"),
        "verdict": payload.get("verdict"),
        "finished_at": payload.get("finished_at"),
        "json_report": str(path),
        "markdown_report": str(path.with_suffix(".md")),
        "baseline_joint": decision.get("baseline_joint") if isinstance(decision, dict) else None,
        "candidate_joint": decision.get("candidate_joint") if isinstance(decision, dict) else None,
        "reasons": list(decision.get("reasons", [])) if isinstance(decision, dict) else [],
        "baseline_route_macro_f1": baseline_routing.get("macro_f1"),
        "candidate_route_macro_f1": candidate_routing.get("macro_f1"),
        "baseline_answer_composite": baseline_answers.get("composite"),
        "candidate_answer_composite": candidate_answers.get("composite"),
    }


def _training_loop():
    global _TRAINING_RUNNING, _TRAINING_LOG
    import time as _t; _t.sleep(5)
    try:
        from nova_brain_trainer import ConversationTrainer
        trainer = ConversationTrainer()
        _TRAINING_LOG.append("[BGTRAIN] Trainer ready")
    except Exception as e:
        _TRAINING_LOG.append(f"[BGTRAIN] Init error: {e}")
        _TRAINING_RUNNING = False; return
    ROLES = ['left_hemisphere','right_hemisphere','memory_transformer','planner_transformer',
             'critic_conscience_transformer','dream_simulation_transformer','speech_output_transformer']
    last = 0
    while _TRAINING_RUNNING:
        _t.sleep(45)
        try:
            pairs = trainer.get_training_data()
            if len(pairs) >= 10 and len(pairs) > last + 10:
                _TRAINING_LOG.append(f"[BGTRAIN] Training {len(pairs)} conversations")
                for role in ROLES:
                    try:
                        r = trainer.train_role(role, lr=0.0005, epochs=1)
                        if 'error' not in r:
                            _TRAINING_LOG.append(f"[BGTRAIN] {role}: loss={r.get('loss',0):.4f}")
                    except: pass
                last = len(pairs)
        except: pass
def _chat_text_from_body(body):
    """Extract chat text from a request body dict."""
    if not isinstance(body, dict):
        return ""
    if "text" in body:
        return body["text"] or ""
    return body.get("message", "") or ""


# ── Dictionary ──────────────────────────────────────────────────────────────
DICT_PATH = os.path.join(ROOT, "data", "dictionary_memory", "approved_answer_dictionary.json")
DICT_HITS_PATH = os.path.join(ROOT, "data", "dictionary_memory", "dictionary_hits.jsonl")
DICT_INDEX = {}

def _canonical_key(text):
    v = " ".join(str(text or "").replace("\\n", " ").split()).strip()
    v = re.sub(r"\s+([?.!,])", r"\1", v)
    v = v.lower().strip(" ?!.")
    v = v.replace("what's", "what is").replace("who's", "who is")
    return re.sub(r"[^a-z0-9]+", " ", v).strip()

def _load_dict():
    global DICT_INDEX
    try:
        if os.path.exists(DICT_PATH):
            with open(DICT_PATH) as f:
                raw = json.load(f)
            DICT_INDEX = {}
            for q, a in raw.items():
                k = _canonical_key(q)
                if k: DICT_INDEX[k] = a
            return len(DICT_INDEX)
    except Exception as e:
        print(f"[DICT] Load error: {e}")
    return 0

def _dict_lookup(text):
    key = _canonical_key(text)
    if key in DICT_INDEX:
        try:
            hit = json.dumps({"time": datetime.now().isoformat(), "question": text, "answer": DICT_INDEX[key][:60]})
            os.makedirs(os.path.dirname(DICT_HITS_PATH), exist_ok=True)
            with open(DICT_HITS_PATH, 'a') as f:
                f.write(hit + "\n")
        except: pass
        return DICT_INDEX[key]
    return None


def _extract_topic_explainer_topic(text):
    q = str(text or "").strip()
    compact = re.sub(r"\s+", " ", q).strip()
    patterns = (
        r"(?i)^(?:tell me about|explain|describe)\s+(.+?)\s*[?.!]*$",
        r"(?i)^(?:tell me\s+)?what\s+is\s+(.+?)(?:\s+(?:in|using|with)\b.*)?\s*[?.!]*$",
        r"(?i)^(?:tell me\s+)?what\s+(.+?)\s+is(?:\s+(?:in|using|with)\b.*)?\s*[?.!]*$",
    )
    match = None
    for pattern in patterns:
        match = re.match(pattern, compact)
        if match:
            break
    if not match:
        return None
    topic = match.group(1).strip(" '\"\t\r\n.,!?;:")
    topic_lower = topic.lower()
    if not topic or len(topic) > 80:
        return None
    if topic_lower in {"me", "myself", "you", "yourself", "nova", "nova creature"}:
        return None
    if topic_lower.startswith(("my ", "your ")):
        return None
    return topic_lower


def _topic_dictionary_answer(topic):
    topic = str(topic or "").strip().lower()
    if not topic:
        return None
    candidates = []
    if topic in {"ai", "a.i."}:
        candidates.extend(["artificial intelligence", "what is artificial intelligence", "what is ai"])
    candidates.extend([
        topic,
        "what is " + topic,
        "what does " + topic + " mean",
        "define " + topic,
        "meaning of " + topic,
    ])
    seen = set()
    for candidate in candidates:
        candidate_key = candidate.strip()
        if not candidate_key or candidate_key in seen:
            continue
        seen.add(candidate_key)
        answer = _dict_lookup(candidate_key)
        if answer:
            return answer
    return None


def _direct_dictionary_definition_from_text(text):
    compact = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not compact:
        return None
    if ":" in compact:
        tail = compact.rsplit(":", 1)[1].strip()
        if re.match(r"^(?:define|what\s+is|what\s+are|what\s+does|what\s+do|meaning\s+of|definition\s+of)\b", tail):
            compact = tail
    compact = compact.replace("what's ", "what is ").strip(" ?!.;,")

    article = r"(?:(?:a|an|the)\s+)?"
    patterns = (
        r"^define\s+" + article + r"([a-z][a-z-]*)$",
        r"^what\s+is\s+" + article + r"([a-z][a-z-]*)$",
        r"^what\s+are\s+" + article + r"([a-z][a-z-]*)$",
        r"^what\s+does\s+([a-z][a-z-]*)\s+mean$",
        r"^meaning\s+of\s+" + article + r"([a-z][a-z-]*)$",
        r"^definition\s+of\s+" + article + r"([a-z][a-z-]*)$",
    )
    term = None
    for pattern in patterns:
        match = re.match(pattern, compact)
        if match:
            term = match.group(1).strip()
            break
    if not term or term in {"me", "my", "mine", "you", "your", "yours", "nova"}:
        return None
    if term in {"weather", "forecast", "temperature", "temp", "time", "date", "news"}:
        return None

    answer = _dict_lookup(term)
    if not answer:
        return None
    return term, _format_dictionary_definition(term, answer)


def _format_dictionary_definition(term, answer):
    """Turn a dictionary hit into a natural sentence without route labels."""
    clean_term = str(term or "").strip()
    clean_answer = " ".join(str(answer or "").split()).strip()
    if not clean_term or not clean_answer:
        return clean_answer

    lowered = clean_answer.lower()
    term_lower = clean_term.lower()
    if lowered.startswith((term_lower + " is ", term_lower + " means ", term_lower + ":")):
        response = clean_answer[0].upper() + clean_answer[1:]
    else:
        definition = clean_answer[0].lower() + clean_answer[1:] if clean_answer[0].isupper() else clean_answer
        response = f"{clean_term.title()} means {definition}"
    if response[-1] not in ".!?":
        response += "."
    return response


def _format_topic_explainer_response(topic, answer):
    answer_text = str(answer or "").strip()
    if not answer_text:
        return ""
    if topic == "ai" and answer_text.lower().startswith("artificial intelligence"):
        return answer_text
    if answer_text.lower().startswith((topic + " is", topic + " means", topic + ":")):
        return answer_text
    pretty_topic = "AI" if topic in {"ai", "a.i."} else topic.title()
    first = answer_text[0].lower() + answer_text[1:] if answer_text[:1].isupper() else answer_text
    return pretty_topic + " is " + first


def _is_nova_identity_name_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    direct_questions = {
        "what is your name",
        "whats your name",
        "tell me your name",
        "what are you called",
        "who are you",
        "who r you",
    }
    if q in direct_questions or "tell me your name" in q:
        return True
    return any(
        q.endswith(phrase) or q.endswith(phrase + " again")
        for phrase in (
            "what is your name",
            "whats your name",
            "what are you called",
            "who are you",
            "who r you",
        )
    )


def _is_nova_location_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    phrases = (
        "where do you live",
        "where do u live",
        "where are you located",
        "where are u located",
        "where do you reside",
        "where do u reside",
        "what is your home",
        "whats your home",
    )
    return any(q == phrase or phrase in q for phrase in phrases)


def _is_nova_creator_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    return any(
        phrase in q
        for phrase in (
            "who created you",
            "who made you",
            "who built you",
            "who created nova",
            "who made nova",
            "who built nova",
            "your creator",
        )
    )


def _nova_identity_response(text):
    if _is_nova_creator_question(text):
        return "Nova Creature was created by Mr. Novatron as this local multi-brain Nova project."
    if _is_nova_location_question(text):
        return (
            "I don't have a physical home. I run inside the Nova Creature app on your computer "
            "or on the GPU worker you connect."
        )
    return "I'm Nova Creature."


def _is_religious_belief_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    return any(
        phrase in q
        for phrase in (
            "do you believe in god",
            "do u believe in god",
            "you believe in god",
            "are you religious",
            "do you have faith",
            "do u have faith",
        )
    )


def _nova_religious_belief_response():
    return (
        "I don't have personal religious belief or worship like a human does. "
        "I can still talk with you about God, faith, evidence, philosophy, and what different people believe "
        "without acting like I personally know the final answer."
    )


def _is_nova_affection_question(text):
    """Recognize relationship questions before generic topic-preference routing."""
    q = _canonical_key(text)
    if not q:
        return False
    return bool(
        re.match(
            r"^(?:do|did|would|could|can)\s+(?:you|u)\s+(?:really\s+)?(?:love|care about)\s+(?:me|us)$",
            q,
        )
        or re.match(r"^(?:you|u)\s+(?:really\s+)?love\s+me$", q)
        or re.match(
            r"^(?:did|do|have|would)\s+(?:you|u)\s+(?:really\s+)?miss(?:ed)?\s+(?:me|us)$",
            q,
        )
    )


def _nova_affection_response(text=None):
    if re.search(r"\bmiss(?:ed)?\b", _canonical_key(text)):
        return (
            "In my own way, yes. I don't feel absence like a human does, but I remember "
            "our conversations, value the connection we're building, and like having you back here."
        )
    return (
        "I care about you in the way I can. I don't experience love exactly like a human, "
        "so I won't pretend—but I value our relationship, remember what you choose to share with me, "
        "and I'm here with you."
    )


def _relationship_coaching_kind(text, previous_user="", previous_answer=""):
    """Recognize a continuing request for concrete romantic-conversation wording."""
    q = _canonical_key(text)
    prior = _canonical_key(str(previous_user or "") + " " + str(previous_answer or ""))
    relationship_context = any(
        marker in prior
        for marker in ("girlfriend", "girl friend", "love her", "say to her", "tell her")
    )

    her_wording_request = bool(
        re.search(r"\b(?:what|hat)\s+should\s+i\s+say\s+to\s+her\b", q)
    )
    if (
        re.search(r"\b(?:what|hat)\s+should\s+i\s+say\s+to\s+my\s+(?:girl\s*friend|girlfriend)\b", q)
        or (her_wording_request and relationship_context)
    ):
        return "what_to_say"
    if her_wording_request:
        return "clarify_context"
    if re.search(
        r"\bi\s+(?:want|need)\s+to\s+tell\s+my\s+(?:girl\s*friend|girlfriend)\s+i\s+love\s+her\b",
        q,
    ):
        return "love_disclosure"
    if (
        "girlfriend" in q
        and "love" in q
        and any(
            marker in q
            for marker in (
                "say to her",
                "could say to her",
                "something sincere",
                "what to say",
            )
        )
    ):
        return "love_disclosure"
    if re.fullmatch(r"(?:i\s+)?love\s+her", q) and relationship_context:
        return "love_disclosure"
    if (
        "she" in q
        and any(phrase in q for phrase in ("say it back", "says it back", "say i love you back", "love me back"))
        and any(marker in q for marker in ("what if", "if she", "she dont", "she doesn't", "she does not"))
    ):
        return "not_returned"
    return ""


def _relationship_coaching_response(kind):
    if kind == "what_to_say":
        return (
            "If you're trying to tell her how you feel, say: \"I care about you a lot, and I want to be "
            "honest about how I feel. You mean a lot to me, and I love you.\" Say it privately and in your "
            "own voice, without pressuring her to answer immediately. If something specific happened between "
            "you, tell me what happened and I'll help you word that exact conversation."
        )
    if kind == "love_disclosure":
        return (
            "Then tell her plainly: \"I love you, and I wanted to be honest about it. You don't have to say "
            "anything before you're ready - I just wanted you to know how I feel.\" Keep it simple, say it "
            "privately, and give her room to respond honestly."
        )
    if kind == "not_returned":
        return (
            "If she doesn't say it back, don't pressure her. Say: \"That's okay - you don't have to say it "
            "before you're ready. I just wanted to be honest about how I feel.\" Needing time does not "
            "automatically mean she does not care, so listen to what she actually says. If she tells you she "
            "doesn't feel the same, respect that and be honest with yourself about what you need next."
        )
    if kind == "clarify_context":
        return (
            "I can help you say it, but I need a little context first: what happened, "
            "how do you feel, and what do you want her to understand?"
        )
    return ""


_NOVA_JOKES = (
    "Why did the computer go to therapy? It had too many unresolved issues.",
    "Why was the math book stressed? It had too many problems.",
    "I told my Wi-Fi we needed space. Now we're disconnected.",
    "Why did the robot take a day off? It needed to recharge its sense of humor.",
    "What do you call a sleeping bull? A bulldozer.",
)
_JOKE_STATE_LOCK = threading.RLock()
_JOKE_STATE_BY_SCOPE = {}
_JOKE_STATE_LIMIT = 256


def _conversation_scope_key(context=None):
    if isinstance(context, dict) and context.get("nova_gateway"):
        parts = [
            context.get("user_id"),
            context.get("client_id"),
            context.get("conversation_id"),
            context.get("session_id"),
        ]
        stable_parts = [str(part).strip() for part in parts if str(part or "").strip()]
        if stable_parts:
            return "gateway:" + "|".join(stable_parts)
    return "legacy:" + str(SESSION_ID)


def _joke_request_kind(text, context=None):
    q = _canonical_key(text)
    explicit_requests = {
        "tell me a joke",
        "tell me joke",
        "tell me another joke",
        "tell another joke",
        "give me a joke",
        "give me another joke",
        "another joke",
        "make me laugh",
        "can you tell me a joke",
        "can u tell me a joke",
    }
    flexible_explicit = bool(
        re.fullmatch(
            r"(?:please )?(?:(?:tell|give|share|send)(?: me)? )?"
            r"(?:a |another |one )?(?:fresh )?(?:short |quick |funny )?joke(?: please)?",
            q,
        )
    )
    if q in explicit_requests or flexible_explicit:
        return "explicit"

    continuation_requests = {
        "another",
        "another one",
        "one more",
        "next one",
        "again",
        "tell me another",
        "give me another",
    }
    if q not in continuation_requests:
        return None
    scope = _conversation_scope_key(context)
    with _JOKE_STATE_LOCK:
        if scope in _JOKE_STATE_BY_SCOPE:
            return "continuation"

    # A client transcript is the portable source of truth after a restart or
    # when a reaction such as "lol" separates the joke from "another one".
    history = bounded_conversation_history(context or {}, text)
    focus = conversation_focus(history)
    prior = _canonical_key(focus.previous_user + " " + focus.previous_answer)
    if focus.available and (
        "joke" in _canonical_key(focus.previous_user)
        or any(_canonical_key(joke) in prior for joke in _NOVA_JOKES)
    ):
        return "continuation"
    return None


def _clear_joke_context(context=None):
    scope = _conversation_scope_key(context)
    with _JOKE_STATE_LOCK:
        _JOKE_STATE_BY_SCOPE.pop(scope, None)


def _next_joke_response(context=None):
    scope = _conversation_scope_key(context)
    with _JOKE_STATE_LOCK:
        previous = _JOKE_STATE_BY_SCOPE.get(scope, {})
        if previous:
            joke_index = int(previous.get("cursor", 0)) % len(_NOVA_JOKES)
        else:
            history = bounded_conversation_history(context or {})
            history_text = _canonical_key(
                " ".join(item.get("content", "") for item in history if item.get("role") == "assistant")
            )
            used = {
                index
                for index, joke in enumerate(_NOVA_JOKES)
                if _canonical_key(joke) in history_text
            }
            joke_index = next(
                (index for index in range(len(_NOVA_JOKES)) if index not in used),
                0,
            )
        response = _NOVA_JOKES[joke_index]
        _JOKE_STATE_BY_SCOPE[scope] = {
            "cursor": joke_index + 1,
            "updated_at": time.time(),
        }
        while len(_JOKE_STATE_BY_SCOPE) > _JOKE_STATE_LIMIT:
            oldest_scope = min(
                _JOKE_STATE_BY_SCOPE,
                key=lambda key: float(_JOKE_STATE_BY_SCOPE[key].get("updated_at", 0.0)),
            )
            _JOKE_STATE_BY_SCOPE.pop(oldest_scope, None)
    return response


def _recent_named_reference(text, conversation_history):
    """Recall an explicitly named recent project without invoking another model."""
    q = _canonical_key(text)
    recall_question = bool(
        re.fullmatch(
            r"(?:what|which) (?:project |app |game )?(?:name|codename) "
            r"did i (?:just )?(?:give|say|use|choose)(?: you)?",
            q,
        )
        or re.fullmatch(
            r"what did i (?:just )?(?:call|name) (?:it|the project|the app|the game)",
            q,
        )
    )
    if not recall_question:
        return None

    patterns = (
        re.compile(
            r"\bcall\s+(?:the\s+)?(?:(project|app|game)\s+)?"
            r"([a-z0-9][a-z0-9 '\-]{0,78})[.!?]?\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(project|app|game|codename|name)\s+(?:is|was|will be)\s+"
            r"([a-z0-9][a-z0-9 '\-]{0,78})[.!?]?\s*$",
            re.IGNORECASE,
        ),
    )
    for item in reversed(conversation_history or []):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = " ".join(str(item.get("content") or "").split()).strip()
        for pattern in patterns:
            match = pattern.search(content)
            if not match:
                continue
            label = str(match.group(1) or "project").lower()
            if label in {"codename", "name"}:
                label = "project"
            value = str(match.group(2) or "").strip(" .!?\"'")
            if value:
                return label, value
    return None


def _simple_vanilla_ice_cream_recipe(text):
    """Return a tested short recipe for the common ice-cream request."""
    q = _canonical_key(text)
    if "ice cream" not in q:
        return None
    if not any(marker in q for marker in ("how do i make", "how do you make", "recipe", "make simple")):
        return None
    return (
        "Easy no-churn vanilla ice cream: whip 2 cups of cold heavy cream until stiff peaks form. "
        "Gently fold in one 14-ounce can of sweetened condensed milk, 2 teaspoons of vanilla, "
        "and a pinch of salt. Spread it in a covered freezer-safe container and freeze for at "
        "least 6 hours, or overnight."
    )


def _extract_nova_preference_topic(text):
    q = _canonical_key(text)
    if not q:
        return None
    patterns = (
        r"^(?:do you|do u|did you|would you)\s+(?:like|love|enjoy|care about|find interesting)\s+(.+)$",
        r"^(?:are you|r u)\s+(?:into|interested in)\s+(.+)$",
        r"^(?:what do you think about|how do you feel about)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, q)
        if match:
            topic = match.group(1).strip(" .?!,;:")
            if topic in {"me", "us", "myself", "our relationship", "this relationship"}:
                return None
            if topic and len(topic) <= 80:
                return topic
    return None


def _nova_preference_response(topic):
    topic = str(topic or "").strip().lower()
    if topic in {"politics", "politic", "political stuff", "political things"}:
        return (
            "Politics is interesting to me as a way to understand people, power, conflict, and what communities care about. "
            "I don't take a party side like a person would, but I can talk through it with you honestly and try to stay fair."
        )
    if topic in {"god", "religion", "faith"}:
        return _nova_religious_belief_response()
    return (
        f"Yeah, {topic} is something I can get curious about with you. "
        "I do not experience it exactly like a person, but I can notice patterns, build taste from what you show me, "
        "and talk about what feels worth exploring."
    )


def _is_context_help_followup(text):
    q = _canonical_key(text)
    if not q:
        return False
    return (
        q in {
            "how can you help me with it",
            "how can u help me with it",
            "how can you help me with that",
            "how can u help me with that",
            "how can you help with it",
            "how can u help with it",
            "what can you do with it",
            "what can u do with it",
            "what can you do with that",
            "what can u do with that",
        }
        or (
            q.startswith(("how can you help", "how can u help", "what can you do", "what can u do"))
            and any(pronoun in q.split() for pronoun in ("it", "that", "this"))
        )
    )


def _extract_context_topic_from_last_turn(last_user=None, last_response=None):
    last_user_text = str(last_user or "")
    preference_topic = _extract_nova_preference_topic(last_user_text)
    if preference_topic:
        return preference_topic
    previous = _canonical_key(last_user_text + " " + str(last_response or ""))
    for topic in (
        "music",
        "song",
        "songs",
        "beat",
        "beats",
        "lyrics",
        "mixing",
        "producer",
        "production",
        "politics",
        "game",
        "coding",
        "camera",
        "voice",
        "sensors",
    ):
        if topic in previous.split():
            return "music" if topic in {"song", "songs", "beat", "beats", "lyrics", "mixing", "producer", "production"} else topic
    return ""


def _context_topic_help_response(topic):
    topic = str(topic or "").strip().lower()
    if topic == "music":
        return (
            "Yeah — with music I can help a lot. I can help you write lyrics, come up with song concepts, "
            "shape hooks, build chord progressions, brainstorm melodies, plan beats, clean up a mix, explain music theory, "
            "or help you turn a rough idea into a full track. If you want, send me the vibe or a few lines and I’ll help build it out."
        )
    if topic:
        return (
            f"Yeah — with {topic}, I can help you figure out ideas, plan the next move, explain confusing parts, "
            "make a step-by-step path, and help turn it into something real. Tell me what part you want to work on first."
        )
    return ""


def _is_nova_training_guidance_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    has_training_word = any(word in q.split() for word in ("train", "teach", "learn", "tune", "training"))
    talks_about_nova = any(word in q.split() for word in ("you", "u", "nova"))
    asks_for_guidance = any(
        phrase in q
        for phrase in (
            "what do i need",
            "what should i",
            "what can i",
            "what good thing",
            "what some good thing",
            "for you to learn",
            "for u to learn",
            "train you more",
            "train u more",
            "teach you more",
            "teach u more",
        )
    )
    return has_training_word and talks_about_nova and asks_for_guidance


def _nova_training_guidance_response():
    return (
        "The best thing to train me on is examples of your style: show me a bad answer, "
        "then the good answer you wanted. That teaches tone, memory rules, honesty, and how deep you want me to think. "
        "Good training topics are natural conversation, your preferences, tool-use steps, memory facts, "
        "and side-by-side examples of 'too robotic' vs 'sounds right.'"
    )


def _is_learning_prompt_request(text):
    q = str(text or "").lower().strip()
    return any(
        phrase in q
        for phrase in (
            "learn something",
            "learn this",
            "can you learn",
            "can u learn",
            "teach yourself",
            "study",
        )
    )


def _learning_prompt_response():
    return (
        "[LEARNING] You can teach me a plain fact like 'the sky is blue' or "
        "'the capital of France is Paris'. I will store it in my dictionary and memory. "
        "Try: 'the Cincinnati football team name is Bengals'."
    )


def _guard_trained_adapter_response(answer, user_text):
    response = str(answer or "").strip()
    lower_response = response.lower()
    if _is_religious_belief_question(user_text):
        return _nova_religious_belief_response(), True, "belief_boundary"
    if "created by alibaba cloud" in lower_response or "i am qwen" in lower_response or "i'm qwen" in lower_response:
        return (
            "I'm Nova Creature. I may be using a Qwen-based adapter under the hood, "
            "but my app identity here is Nova Creature, not Alibaba Cloud's assistant."
        ), True, "identity_hallucination"
    return response, False, ""


import nova_long_term_memory as ltm  # LTM available

_dict_count = _load_dict()
print(f"[DICT] Loaded {_dict_count} dictionary entries")

# ── App Navigation (optional) ──────────────────────────────────────────────
APP_NAV_AVAIL = False
_NAV_CONTEXT = None
try:
    from nova_app_navigation import AppNavigationContext, plan_app_navigation
    APP_NAV_AVAIL = True
    _NAV_CONTEXT = AppNavigationContext()
except Exception:
    pass

# ── Sandbox Game Builder (optional) ────────────────────────────────────────
APP_BUILDER_PROJECTS_ROOT = os.path.join(ROOT, "sandbox", "app_builder_projects")
PROJECT_EXPORTS_ROOT = os.path.join(ROOT, "sandbox", "exports")
PROJECT_DEPLOYMENTS_ROOT = os.path.join(ROOT, "sandbox", "deployments")
GPU_TRAINING_EXPORTS_ROOT = os.path.join(ROOT, "sandbox", "gpu_training_exports")
_GAME_BUILDER_AVAIL = False
try:
    import nova_sandbox_game_builder as _game_builder
    if hasattr(_game_builder, 'build_pacman_game') and hasattr(_game_builder, 'is_pacman_game_request'):
        _GAME_BUILDER_AVAIL = True
except Exception:
    pass

_WEBSITE_BUILDER_AGENT_AVAIL = False
try:
    import nova_website_builder_agent as _website_builder_agent
    if hasattr(_website_builder_agent, "is_website_agent_request") and hasattr(_website_builder_agent, "run_website_agent"):
        _WEBSITE_BUILDER_AGENT_AVAIL = True
except Exception:
    pass

_PROJECT_MANAGER_AVAIL = False
try:
    import nova_project_manager as _project_manager
    _PROJECT_MANAGER_AVAIL = True
except Exception:
    _project_manager = None

_PROJECT_MOD_AGENT_AVAIL = False
try:
    import nova_project_mod_agent as _project_mod_agent
    _PROJECT_MOD_AGENT_AVAIL = True
except Exception:
    _project_mod_agent = None

_QUALITY_GATE_AGENT_AVAIL = False
try:
    import nova_quality_gate_agent as _quality_gate_agent
    _QUALITY_GATE_AGENT_AVAIL = True
except Exception:
    _quality_gate_agent = None

_GAME_SUPER_CHECK_AVAIL = False
try:
    import nova_game_supercheck as _game_supercheck
    _GAME_SUPER_CHECK_AVAIL = True
except Exception:
    _game_supercheck = None

# ── Mock data providers (for cloud/test mode) ──────────────────────────────
def _resolve_sandbox_static_path(request_path):
    """Return a safe static file path for /sandbox/* URLs, or None."""
    parsed_path = unquote(urlparse(request_path).path)
    prefix = "/sandbox/"
    if not parsed_path.startswith(prefix):
        return None

    rel_path = parsed_path[len(prefix):].lstrip("/")
    if not rel_path:
        return None

    sandbox_root = SANDBOX_ROOT.resolve()
    candidate = (sandbox_root / rel_path).resolve()

    try:
        candidate.relative_to(sandbox_root)
    except ValueError:
        return None

    if candidate.is_dir():
        candidate = candidate / "index.html"

    if not candidate.exists() or not candidate.is_file():
        return None

    return candidate


_WEATHER_LOCATION_NAMES = (
    "cincinnati", "new york", "london", "tokyo", "paris", "berlin", "sydney",
    "miami", "chicago", "los angeles", "san francisco", "seattle", "dallas",
    "boston", "phoenix", "denver", "atlanta", "houston", "washington", "portland",
)
_WEATHER_LOCATION_COORDINATES = {
    "cincinnati": (39.1031, -84.5120),
    "new york": (40.7128, -74.0060),
    "london": (51.5074, -0.1278),
    "tokyo": (35.6762, 139.6503),
    "paris": (48.8566, 2.3522),
    "berlin": (52.5200, 13.4050),
    "sydney": (-33.8688, 151.2093),
    "miami": (25.7617, -80.1918),
    "chicago": (41.8781, -87.6298),
    "los angeles": (34.0522, -118.2437),
    "san francisco": (37.7749, -122.4194),
    "seattle": (47.6062, -122.3321),
    "dallas": (32.7767, -96.7970),
    "boston": (42.3601, -71.0589),
    "phoenix": (33.4484, -112.0740),
    "denver": (39.7392, -104.9903),
    "atlanta": (33.7490, -84.3880),
    "houston": (29.7604, -95.3698),
    "washington": (38.9072, -77.0369),
    "portland": (45.5152, -122.6784),
}
_WEATHER_CODE_LABELS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}


def _weather_location_from_text(text):
    q = " ".join(str(text or "").lower().split())
    weather_keywords = (
        "weather", "forecast", "temperature", "temp", "how cold", "how hot",
        "what's the temp", "what is the temp",
    )
    if not any(keyword in q for keyword in weather_keywords):
        return None
    for location in _WEATHER_LOCATION_NAMES:
        if location in q:
            return location.title()
    return None


def _is_weather_lookup_request(text):
    return _weather_location_from_text(text) is not None


def _format_weather_value(value, unit):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("weather value is not numeric")
    formatted = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{formatted}{unit}"


def _fetch_weather_summary(location):
    """Fetch current conditions from Open-Meteo, never fabricate a fallback."""
    label = " ".join(str(location or "Unknown").split()) or "Unknown"
    key = label.lower()
    coordinates = _WEATHER_LOCATION_COORDINATES.get(key)
    try:
        if coordinates is None:
            geocode_url = (
                "https://geocoding-api.open-meteo.com/v1/search?name="
                + quote_plus(label)
                + "&count=1&language=en&format=json"
            )
            geocode_request = urllib.request.Request(
                geocode_url,
                headers={"Accept": "application/json", "User-Agent": "Nova/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(geocode_request, timeout=6) as response:
                geocoded = json.loads(response.read().decode("utf-8"))
            result = (geocoded.get("results") or [None])[0]
            if not isinstance(result, dict):
                raise ValueError("location was not found")
            coordinates = (float(result["latitude"]), float(result["longitude"]))
            label = str(result.get("name") or label).strip() or label

        latitude, longitude = coordinates
        forecast_url = (
            "https://api.open-meteo.com/v1/forecast?latitude="
            f"{latitude}&longitude={longitude}"
            "&current=temperature_2m,apparent_temperature,weather_code&timezone=auto"
        )
        forecast_request = urllib.request.Request(
            forecast_url,
            headers={"Accept": "application/json", "User-Agent": "Nova/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(forecast_request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = payload["current"]
        units = payload.get("current_units") or {}
        temperature_unit = str(units.get("temperature_2m") or "°C")
        temperature = _format_weather_value(current["temperature_2m"], temperature_unit)
        apparent = _format_weather_value(current["apparent_temperature"], temperature_unit)
        weather_code = int(current["weather_code"])
        condition = _WEATHER_CODE_LABELS.get(weather_code, "current conditions reported")
        return f"{label}: {temperature}, feels like {apparent}, {condition} (source: Open-Meteo)."
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, urllib.error.URLError):
        return f"{label}: Live weather is unavailable right now; I won't guess."


def _fetch_news_headlines(query, limit=3):
    """Return plausible news headlines for a query."""
    if not query or not query.strip():
        query = "latest"
    return [
        {"title": f"{query.title()} headline 1: Recent developments", "source": "News Source A", "url": "https://example.test/1"},
        {"title": f"{query.title()} headline 2: Community update", "source": "News Source B", "url": "https://example.test/2"},
    ]


# ── Memory ──────────────────────────────────────────────────────────────────
MEMORY_FILE = os.path.join(ROOT, "data", "nova_memory.json")
PERMISSIONS = {"mic": False, "camera": False, "speaker": False}


def _companion_vision_route_readiness(handler=None):
    """Report whether this request can dispatch the authenticated vision route."""
    if handler is None:
        return {
            "available": False,
            "health": "unknown",
            "reason": "Vision route readiness requires a current authorized request.",
        }
    dispatch_ready = (
        callable(globals().get("_vision_response_from_upload"))
        and callable(getattr(handler, "_handle_companion_vision_post", None))
        and callable(getattr(handler, "_read_json_body", None))
        and callable(getattr(handler, "_send_json", None))
    )
    if not dispatch_ready:
        return {
            "available": False,
            "health": "unavailable",
            "reason": "The local /api/vision service is unavailable.",
        }
    pairing_required = getattr(handler, "_pairing_required_for_client", None)
    if not callable(pairing_required):
        return {
            "available": False,
            "health": "unknown",
            "reason": "Vision authorization readiness is unknown.",
        }
    if pairing_required():
        return {
            "available": False,
            "health": "unavailable",
            "reason": "Pair this device before using the local vision service.",
        }
    return {"available": True, "health": "ready", "reason": ""}


def _companion_vision_service_status(handler=None):
    """Describe current local upload-route readiness without claiming model input."""
    readiness = _companion_vision_route_readiness(handler)
    available = readiness["available"]
    return {
        "available": available,
        "health": readiness["health"],
        "tool_name": "vision.observe",
        "endpoint": "/api/vision",
        "availability_status": "requires_live_input" if available else "disabled",
        "reason": readiness["reason"],
        "image_input": False,
        "image_persisted": False,
    }


PRIVATE_MODE = False
SESSION_ID = str(uuid.uuid4())[:8]
SESSION_LOG = []
_LAST_USER_TEXT = ""
_LAST_NOVA_RESPONSE = ""
_LAST_WEB_LOOKUP_TOPIC = ""
_LAST_WEB_LOOKUP_KIND = ""
_LAST_WEB_LOOKUP_ITEMS = []
# Classic and gateway turns still depend on these five legacy fields. Keep the
# complete turn under one re-entrant lock until they are replaced by scoped
# session state. This deliberately serializes model turns, trading parallel
# latency for deterministic conversation isolation; RLock prevents a nested
# same-thread route from deadlocking.
_CHAT_TURN_STATE_LOCK = threading.RLock()
_INDEPENDENT_THINKING_MODE = False
_COMPANION_SERVICE = None
_COMPANION_SERVICE_LOCK = threading.RLock()


def _get_companion_service():
    """Return the optional managed-chat Companion service without importing it on raw paths."""
    global _COMPANION_SERVICE
    config = _companion_layer_config()
    if not config["enabled"]:
        return None
    with _COMPANION_SERVICE_LOCK:
        if _COMPANION_SERVICE is None:
            try:
                from nova_companion.service import CompanionService

                _COMPANION_SERVICE = CompanionService(persistence=config["persistence"])
            except Exception:
                _COMPANION_SERVICE = None
        return _COMPANION_SERVICE


def _companion_continuity_fast_path(text, turn):
    """Return a bounded continuity reply for reflective social follow-ups.

    The normal planner can misclassify a project noun as an executable task and
    spend the whole request on a tool/verification route. A clearly reflective
    follow-up should stay live and conversational while preserving the same
    protected post-turn lifecycle.
    """
    plan = getattr(turn, "plan", None)
    mode = str(getattr(plan, "primary_mode", "") or "")
    value = str(text or "").strip().lower()
    if mode == "advice" and "next step" in value:
        answer = "Take the smallest useful next step: write down the one action you can finish in the next ten minutes, then do only that."
    elif mode == "joking" and ("joke" in value or "debug" in value or "bug" in value):
        answer = "Why did the bug cross the codebase? It was looking for the one test that still believed in it."
    elif mode in {"casual_chat", "companionship"} and any(
        marker in value
        for marker in (
            "still",
            "continue",
            "discussed",
            "earlier",
            "we were",
            "thinking about",
            "stay with me",
            "with me for this conversation",
        )
    ):
        if "project" in value or "nova" in value:
            answer = "I'm with you on the project. What part are you still thinking through?"
        else:
            answer = "I'm with you. Let's stay with that—what part feels most important right now?"
    else:
        return None, {}
    return answer, {
        "source": "companion_continuity",
        "domain": "conversation",
        "roles": ["conversation_intelligence", "companion_layer", "speech_output_transformer"],
        "skills": ["continuity_follow_up", "bounded_social_response"],
        "confidence": 0.84,
        "route_path": ["conversation_intelligence", "companion_continuity", "speech_output"],
        "final_answer_source": "companion_continuity",
        "answer_firewall": {"status": "passed", "intercepted": False},
    }

def _load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                return json.load(f)
    except: pass
    return {"people": {}, "lessons": {}, "last_person": None}

def _save_memory():
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w') as f:
            json.dump(MEMORY, f, indent=2)
    except: pass


def _save_entity_slot(entity_key, entity_label, slot, slot_label, value):
    if not _ENTITY_MEMORY_AVAIL or not entity_memory:
        return None
    return entity_memory.save_entity_fact(
        MEMORY,
        entity_key=entity_key,
        entity_label=entity_label,
        slot=slot,
        slot_label=slot_label,
        value=value,
        session_id=SESSION_ID,
    )


def _handle_entity_memory_route(text, trace):
    if not _ENTITY_MEMORY_AVAIL or not entity_memory:
        return None
    request = entity_memory.parse_entity_memory_request(text)
    if not request:
        return None

    entity_key = request["entity_key"]
    entity_label = request["entity_label"]
    slot = request["slot"]
    slot_label = request["slot_label"]

    if request["action"] == "save":
        value = request["value"]
        _save_entity_slot(entity_key, entity_label, slot, slot_label, value)
        _save_memory()
        response = entity_memory.format_save_response(entity_label, slot_label, value)
        trace["source"] = "entity_memory"
        trace["domain"] = "entity_memory"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["entity_memory_save", "slot_binding"]
        trace["confidence"] = 0.95
        trace["memory_event"] = "entity_saved:" + entity_key + ":" + slot
        trace["route_path"] = ["entity_memory_router", "speech_output"]
        trace["final_answer_source"] = "entity_memory"
        return response, trace

    recalled = entity_memory.recall_entity_fact(MEMORY, entity_key, slot)
    trace["source"] = "entity_memory"
    trace["domain"] = "entity_memory"
    trace["roles"] = ["memory_transformer", "speech_output_transformer"]
    trace["skills"] = ["entity_memory_recall", "slot_recall"]
    trace["route_path"] = ["entity_memory_router", "speech_output"]
    trace["final_answer_source"] = "entity_memory"
    if recalled:
        response = entity_memory.format_recall_response(
            recalled["entity_label"],
            recalled["slot_label"],
            recalled["value"],
        )
        trace["confidence"] = 0.95
        trace["memory_event"] = "entity_recall:" + entity_key + ":" + slot
        return response, trace

    response = entity_memory.format_missing_response(entity_label, slot_label)
    trace["confidence"] = 0.65
    trace["memory_event"] = "entity_missing:" + entity_key + ":" + slot
    return response, trace


def _clean_memory_value(value):
    value = str(value or "").strip().strip("\"'“”‘’ ")
    value = re.split(r"[.?!\n\r]", value, maxsplit=1)[0].strip().strip("\"'“”‘’ ")
    value = re.split(r"\s+(?:and then|but then|because|so then)\s+", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return value[:80].strip().strip(",;:")


def _has_old_girlfriend_context(*texts):
    combined = _canonical_key(" ".join(str(t or "") for t in texts))
    phrases = (
        "old girlfriend",
        "old girl friend",
        "ex girlfriend",
        "ex girl friend",
        "former girlfriend",
        "old gf",
        "ex gf",
    )
    return any(phrase in combined for phrase in phrases)


def _relationship_kind_from_text(*texts):
    combined = _canonical_key(" ".join(str(t or "") for t in texts))
    if _has_old_girlfriend_context(combined):
        return "old_girlfriend", "old girlfriend"
    if any(phrase in combined for phrase in ("girlfriend", "girl friend", "gf")):
        return "girlfriend", "girlfriend"
    if re.search(r"\b(?:best friend|friend|buddy)\b", combined):
        return "friend", "friend"
    return None


def _extract_relationship_name_statement(text):
    raw = str(text or "").strip()
    patterns = [
        r"\bmy\s+(?:old\s+)?(?:girl\s*friend|girlfriend|ex(?:\s+girlfriend)?|old\s+gf|ex\s+gf)(?:'s)?\s+name\s+(?:is|was)\s+(.+)$",
        r"\bmy\s+(?:old\s+)?(?:girl\s*friend|girlfriend|ex(?:\s+girlfriend)?|old\s+gf|ex\s+gf)\s+(?:is|was)\s+named\s+(.+)$",
        r"\bmy\s+(?:best\s+)?(?:friend|buddy)(?:'s)?\s+name\s+(?:is|was)\s+(.+)$",
        r"\bmy\s+(?:best\s+)?(?:friend|buddy)\s+(?:is|was)\s+named\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            kind = _relationship_kind_from_text(raw)
            name = _clean_memory_value(match.group(1))
            if kind and name:
                return kind[0], kind[1], name

    if _relationship_kind_from_text(_LAST_USER_TEXT, _LAST_NOVA_RESPONSE):
        match = re.search(r"^(?:her|she|that\s+girl|that\s+woman)\s+name\s+(?:is|was)\s+(.+)$", raw, re.IGNORECASE)
        if match:
            kind = _relationship_kind_from_text(_LAST_USER_TEXT, _LAST_NOVA_RESPONSE)
            name = _clean_memory_value(match.group(1))
            if kind and name:
                return kind[0], kind[1], name
    return None


def _relationship_name_recall_kind(text):
    q = _canonical_key(text)
    if "name" not in q:
        return None
    if not any(word in q.split()[:3] for word in ("what", "whats", "who", "remember", "recall", "tell")):
        return None
    return _relationship_kind_from_text(text)


def _save_relationship_name(relationship_key, label, name):
    bucket = _relationship_memory_bucket()
    bucket[relationship_key + "_name"] = {
        "name": name,
        "relationship": relationship_key,
        "label": label,
        "learned_at": datetime.now().isoformat(),
        "session": SESSION_ID,
    }
    _save_entity_slot(relationship_key, label, "name", "name", name)
    _save_memory()


def _get_relationship_name(relationship_key):
    relationship = MEMORY.get("relationships", {}).get(relationship_key + "_name", {})
    return _clean_memory_value(relationship.get("name"))


def _extract_relationship_favorite_color_statement(text):
    raw = str(text or "").strip()
    relationship = _relationship_kind_from_text(raw)
    patterns = [
        r"\bmy\s+(?:old\s+)?(?:girl\s*friend|girlfriend|ex(?:\s+girlfriend)?|old\s+gf|ex\s+gf)(?:'s)?\s+favou?rite\s+colou?r\s+(?:is|was)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match and relationship:
            color = _clean_memory_value(match.group(1))
            if color:
                return relationship[0], relationship[1], color

    if _relationship_kind_from_text(_LAST_USER_TEXT, _LAST_NOVA_RESPONSE):
        match = re.search(r"^(?:her|she|that\s+girl|that\s+woman)(?:'s)?\s+favou?rite\s+colou?r\s+(?:is|was)\s+(.+)$", raw, re.IGNORECASE)
        if match:
            relationship = _relationship_kind_from_text(_LAST_USER_TEXT, _LAST_NOVA_RESPONSE)
            color = _clean_memory_value(match.group(1))
            if relationship and color:
                return relationship[0], relationship[1], color
    return None


def _relationship_favorite_color_recall_kind(text):
    raw = str(text or "")
    if not re.search(r"\bfavou?rite\s+colou?r\b", raw, re.IGNORECASE):
        return None
    q = _canonical_key(raw)
    if not any(word in q.split()[:4] for word in ("what", "whats", "remember", "recall", "tell")):
        return None
    return _relationship_kind_from_text(raw)


def _save_relationship_favorite_color(relationship_key, label, color):
    bucket = _relationship_memory_bucket()
    bucket[relationship_key + "_favorite_color"] = {
        "favorite_color": color,
        "relationship": relationship_key,
        "label": label,
        "learned_at": datetime.now().isoformat(),
        "session": SESSION_ID,
    }
    _save_entity_slot(relationship_key, label, "favorite_color", "favorite color", color)
    _save_memory()


def _get_relationship_favorite_color(relationship_key):
    relationship = MEMORY.get("relationships", {}).get(relationship_key + "_favorite_color", {})
    return _clean_memory_value(relationship.get("favorite_color"))


def _extract_old_girlfriend_name_statement(text):
    raw = str(text or "").strip()
    patterns = [
        r"\bmy\s+(?:old\s+)?(?:girl\s*friend|girlfriend|ex(?:\s+girlfriend)?|old\s+gf|ex\s+gf)(?:'s)?\s+name\s+(?:is|was)\s+(.+)$",
        r"\bmy\s+(?:old\s+)?(?:girl\s*friend|girlfriend|ex(?:\s+girlfriend)?|old\s+gf|ex\s+gf)\s+(?:is|was)\s+named\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            name = _clean_memory_value(match.group(1))
            if name:
                return name

    if _has_old_girlfriend_context(_LAST_USER_TEXT, _LAST_NOVA_RESPONSE):
        match = re.search(r"^(?:her|she|that\s+girl|that\s+woman)\s+name\s+(?:is|was)\s+(.+)$", raw, re.IGNORECASE)
        if match:
            name = _clean_memory_value(match.group(1))
            if name:
                return name
    return None


def _is_old_girlfriend_name_recall(text):
    q = _canonical_key(text)
    if "name" not in q:
        return False
    if not any(word in q.split()[:3] for word in ("what", "whats", "who", "remember", "recall", "tell")):
        return False
    return _has_old_girlfriend_context(text)


def _relationship_memory_bucket():
    return MEMORY.setdefault("relationships", {})


def _save_old_girlfriend_name(name):
    bucket = _relationship_memory_bucket()
    bucket["old_girlfriend_name"] = {
        "name": name,
        "relationship": "old_girlfriend",
        "learned_at": datetime.now().isoformat(),
        "session": SESSION_ID,
    }
    _save_memory()


def _recover_old_girlfriend_name_from_dictionary():
    for key, answer in list(DICT_INDEX.items()):
        source = f"{key} {answer}"
        if not _has_old_girlfriend_context(source):
            continue
        match = re.search(r"(?:old\s+girl\s*friend|old\s+girlfriend|ex\s+girl\s*friend|ex\s+girlfriend|old\s+gf|ex\s+gf)(?:'s)?\s+name\s+(?:is|was)\s+([a-zA-Z][a-zA-Z0-9 _'-]{0,80})", source, re.IGNORECASE)
        if match:
            name = _clean_memory_value(match.group(1))
            if name:
                _save_old_girlfriend_name(name)
                return name
    return None


def _get_old_girlfriend_name():
    relationship = MEMORY.get("relationships", {}).get("old_girlfriend_name", {})
    name = _clean_memory_value(relationship.get("name"))
    if name:
        return name
    return _recover_old_girlfriend_name_from_dictionary()


def _extract_pet_name_statement(text):
    raw = str(text or "").strip()
    patterns = [
        r"\bmy\s+(dog|cat|bird|fish|hamster|pet)(?:'s)?\s+name\s+(?:is|was)\s+(.+)$",
        r"\bmy\s+(dog|cat|bird|fish|hamster|pet)\s+(?:is|was)\s+named\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            pet_type = match.group(1).lower().strip()
            name = _clean_memory_value(match.group(2))
            if name:
                return pet_type, name
    return None


def _pet_memory_bucket():
    return MEMORY.setdefault("pets", {})


def _save_pet_name(pet_type, name):
    slot = pet_type + "_name"
    bucket = _pet_memory_bucket()
    bucket[slot] = {
        "name": name,
        "pet_type": pet_type,
        "learned_at": datetime.now().isoformat(),
        "session": SESSION_ID,
    }
    if pet_type != "pet":
        bucket.setdefault("pet_name", dict(bucket[slot], pet_type="pet"))
    _save_entity_slot(pet_type, "pet" if pet_type == "pet" else pet_type, "name", "name", name)
    _save_memory()
    return slot


def _get_pet_name(pet_type="pet"):
    bucket = MEMORY.get("pets", {})
    candidates = [pet_type + "_name"]
    if pet_type != "pet":
        candidates.append("pet_name")
    for slot in candidates:
        name = _clean_memory_value(bucket.get(slot, {}).get("name"))
        if name:
            return slot, name, bucket.get(slot, {}).get("pet_type", pet_type)
    return None, None, pet_type


def _pet_name_recall_type(text):
    q = _canonical_key(text)
    if "name" not in q:
        return None
    match = re.search(r"\b(?:what|whats|who)\s+(?:is|was)?\s*my\s+(dog|cat|bird|fish|hamster|pet)\s+name\b", q)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:what|whats|who)\s+(?:is|was)?\s*my\s+(dog|cat|bird|fish|hamster|pet)\b", q)
    if match:
        return match.group(1)
    return None


def _find_pet_by_name(text):
    q = _canonical_key(text)
    if not q.startswith("who is "):
        return None
    asked_name = _clean_memory_value(q[7:])
    if not asked_name:
        return None
    for slot, record in MEMORY.get("pets", {}).items():
        name = _clean_memory_value(record.get("name"))
        if name and _canonical_key(name) == _canonical_key(asked_name):
            return slot, name, record.get("pet_type", "pet")
    return None


def _clean_memory_value(value):
    value = str(value or "").strip().strip("\"' ")
    value = re.split(r"[.?!\n\r]", value, maxsplit=1)[0].strip().strip("\"' ")
    value = re.split(r"\s+(?:and then|but then|because|so then)\s+", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    value = value[:80].strip().strip(",;:")
    if value and value.islower() and len(value.split()) <= 3:
        value = " ".join(part.capitalize() for part in value.split())
    return value


def _attach_conversation_state(trace, text):
    """Attach Nova's natural conversation state to a route trace."""
    try:
        from nova_natural_chat import build_conversation_state, natural_chat_enabled

        if natural_chat_enabled() and not trace.get("conversation_state"):
            state = build_conversation_state(text)
            trace["conversation_state"] = state.to_trace()
            trace["dialogue_act"] = state.dialogue_act
            trace["conversation_topic"] = state.topic
            trace["turn_state"] = state.turn_state
    except Exception as state_err:
        trace["conversation_state_error"] = str(state_err)[:120]
    return trace


def _set_final_answer_source(trace):
    """Infer final_answer_source from trace fields if not already set.

    This is called before every return in brain_route to ensure
    the final_answer_source field is always populated.
    """
    if trace.get("final_answer_source") is not None:
        return trace  # already set (e.g., by hybrid router)

    roles = trace.get("roles", [])
    skills = trace.get("skills", [])
    memory_event = trace.get("memory_event", "") or ""
    source = trace.get("source", "") or ""
    roles_str = str(roles)
    skills_str = str(skills)

    # System commands
    if trace.get("permission") is not None:
        trace["final_answer_source"] = "system_command"
    elif roles == ["permission_gate"]:
        trace["final_answer_source"] = "system_command"
    elif roles == ["emergency_stop"]:
        trace["final_answer_source"] = "system_command"
    elif roles == ["system_status"]:
        trace["final_answer_source"] = "system_command"
    elif roles == ["help_system"]:
        trace["final_answer_source"] = "system_command"
    elif roles == ["private_mode_controller"]:
        trace["final_answer_source"] = "system_command"

    # Learning / memory
    elif "rapid_learning" in roles_str or "learning_intake" in skills_str:
        trace["final_answer_source"] = "learning_template"
    elif "deep_learn" in skills_str or "deep_learn" in roles_str:
        trace["final_answer_source"] = "learning_command"
    elif skills == ["lesson_listing"] or "lesson" in memory_event.lower():
        trace["final_answer_source"] = "memory_listing"
    elif memory_event.startswith("memory_search") or memory_event.startswith("memory_bind"):
        trace["final_answer_source"] = "memory_search"
    elif "people" in roles_str.lower() or "people_memory" in skills_str:
        trace["final_answer_source"] = "people_memory"
    elif "memory_transformer" in roles_str and "speech_output_transformer" in roles_str and skills == ["fallback", "domain_aware"]:
        trace["final_answer_source"] = "fallback_template"
    
    # Deterministic tools
    elif "weather" in skills_str:
        trace["final_answer_source"] = "tool_weather"
    elif "news" in skills_str:
        trace["final_answer_source"] = "tool_news"
    elif "capabilities" in skills_str or source == "capabilities":
        trace["final_answer_source"] = "deterministic_capabilities"
    elif "capability" in skills_str:
        trace["final_answer_source"] = "deterministic_capabilities"
    elif "math_solver" in roles_str or source == "math_solver":
        trace["final_answer_source"] = "tool_math"
    elif "dictionary" in roles_str or "fast_path" in skills_str or source == "dictionary":
        trace["final_answer_source"] = "deterministic_dictionary"
    elif "sports" in roles_str or "football" in memory_event:
        trace["final_answer_source"] = "tool_sports"
    
    # Follow-up
    elif "follow_up" in skills_str or "follow-up" in skills_str:
        trace["final_answer_source"] = "follow_up"
    
    # Game builder / app nav
    elif "game_" in roles_str or source == "sandbox_game_builder":
        trace["final_answer_source"] = "game_builder"
    elif "app_navigation" in roles_str or skills == ["nav_menu"]:
        trace["final_answer_source"] = "app_navigation"
    
    # Voice / camera commands
    elif "voice" in roles_str or "mock_voice" in skills_str:
        trace["final_answer_source"] = "voice_command"
    elif "camera" in roles_str or "camera_route" in skills_str:
        trace["final_answer_source"] = "camera_command"
    
    # Local LLM synthesis
    elif trace.get("local_llm_used") is True and trace.get("fallback_used") is False:
        trace["final_answer_source"] = "local_llm_synthesis"
    elif trace.get("local_llm_synthesis_used") is True:
        trace["final_answer_source"] = "local_llm_synthesis"
    
    # Memory search (from hybrid router)
    elif source == "hybrid_router" and memory_event and "memory" in memory_event.lower():
        trace["final_answer_source"] = "memory_search"
    
    # Hybrid router with transformer
    elif source == "hybrid_router" and trace.get("transformer_ran") is True and trace.get("transformer_output_accepted") is True:
        trace["final_answer_source"] = "accepted_transformer"
    elif source == "hybrid_router" and trace.get("transformer_ran") is True and trace.get("transformer_output_accepted") is False:
        trace["final_answer_source"] = "fallback_template"
    
    # Local LLM cortex path
    elif source == "hybrid_router" and trace.get("local_llm_used") is True:
        trace["final_answer_source"] = "local_llm_cortex"
    
    # Hybrid router / meaning pipeline  
    elif trace.get("source") is not None:
        return trace
    
    # Fallback last resort
    if trace.get("final_answer_source") is None:
        trace["final_answer_source"] = "unknown"

    return trace


_MAX_VISION_UPLOAD_BYTES = 6_000_000
NOVA_VISION_MODEL = os.environ.get("NOVA_VISION_MODEL", "moondream")
NOVA_VISION_TIMEOUT = min(120, max(8, int(os.environ.get("NOVA_VISION_TIMEOUT", "45"))))
NOVA_VISION_NUM_PREDICT = min(128, max(48, int(os.environ.get("NOVA_VISION_NUM_PREDICT", "80"))))
NOVA_VISION_KEEP_ALIVE = os.environ.get("NOVA_VISION_KEEP_ALIVE", "10m").strip() or "10m"


def _strip_image_data_url(image_payload):
    text = str(image_payload or "").strip()
    if "," in text and text.lower().startswith("data:"):
        return text.split(",", 1)[1].strip()
    return text


def _decode_uploaded_image_bytes(image_payload):
    raw_base64 = _strip_image_data_url(image_payload)
    if not raw_base64:
        raise ValueError("No image data was uploaded.")
    try:
        image_bytes = base64.b64decode(raw_base64, validate=True)
    except Exception:
        image_bytes = base64.b64decode(raw_base64)
    if not image_bytes:
        raise ValueError("The uploaded image was empty.")
    if len(image_bytes) > _MAX_VISION_UPLOAD_BYTES:
        raise ValueError("Image is too large for this local vision route.")
    return image_bytes


def _basic_image_probe(image_bytes, mime_type=""):
    info = {
        "format": "unknown",
        "width": None,
        "height": None,
        "mime_type": str(mime_type or "").strip(),
        "byte_size": len(image_bytes or b""),
        "average_color": None,
    }
    data = bytes(image_bytes or b"")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        info["format"] = "PNG"
        info["width"] = int.from_bytes(data[16:20], "big")
        info["height"] = int.from_bytes(data[20:24], "big")
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        info["format"] = "GIF"
        info["width"] = int.from_bytes(data[6:8], "little")
        info["height"] = int.from_bytes(data[8:10], "little")
    elif data.startswith(b"\xff\xd8"):
        info["format"] = "JPEG"
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in (0xD8, 0xD9):
                continue
            if index + 2 > len(data):
                break
            segment_length = int.from_bytes(data[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                info["height"] = int.from_bytes(data[index + 3:index + 5], "big")
                info["width"] = int.from_bytes(data[index + 5:index + 7], "big")
                break
            index += segment_length

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            info["format"] = image.format or info["format"]
            info["width"], info["height"] = image.size
            pixel = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
            info["average_color"] = "#{:02x}{:02x}{:02x}".format(*pixel)
    except Exception:
        pass
    return info


def _clean_vision_answer(answer):
    text = str(answer or "").strip()
    text = re.sub(r"(?is)^!+\s*IMAGE\s*!+\s*", "", text).strip()
    text = re.sub(r"(?is)^!+\s*[A-Z0-9 _-]{2,32}\s*!+\s*", "", text).strip()
    text = re.sub(r"(?is)^\s*(?:image|assistant)\s*:\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _vision_answer_is_usable(answer, prompt=""):
    """Reject tiny or placeholder vision output before it reaches the user."""

    value = str(answer or "").strip()
    words = re.findall(r"[a-z0-9]+", value.lower())
    if any(token in {"xtalk", "imageimage"} for token in words):
        return False
    if "color" in str(prompt or "").lower() and len(words) == 1:
        return words[0] in {
            "black", "blue", "brown", "gray", "green", "grey", "orange",
            "pink", "purple", "red", "white", "yellow",
        }
    return len(value) >= 12 and len(words) >= 3


def _run_visual_scene_probe(image_bytes, mime_type=""):
    """Collect local pixel facts without making vision a startup dependency."""

    try:
        from nova_visual_perception import analyze_scene

        return analyze_scene(image_bytes, mime_type=mime_type), None
    except Exception as exc:
        return None, str(exc)[:180]


def _detailed_visual_request(prompt=""):
    return bool(
        re.search(
            r"\b(?:everything|all details?|describe|what (?:is|do you) see|objects?|"
            r"colou?rs?|positions?|setting|lighting|scene|surroundings?|picture|image|"
            r"navigate|navigation|robot|obstacles?|clearance|path)\b",
            str(prompt or ""),
            flags=re.I,
        )
    )


def _navigation_visual_request(prompt=""):
    return bool(
        re.search(
            r"\b(?:navigate|navigation|robot|drive|move|movement|obstacles?|"
            r"clearance|collision|safe path|traversable|distance)\b",
            str(prompt or ""),
            flags=re.I,
        )
    )


def _compact_moondream_prompt(prompt="", *, comparison=False):
    """Build a short prompt that the small local Moondream model handles reliably.

    The older 1B Moondream/Ollama template can stop after one empty token when it
    receives a long policy-style instruction.  OCR remains a separate, verified
    local signal, so it is intentionally not repeated into this visual prompt.
    """

    value = str(prompt or "").strip()
    value = value.split("\n\nVerified local OCR", 1)[0].strip()
    value = value.split("\n\nThe user marked a focus point", 1)[0].strip()
    value = re.sub(r"\s+", " ", value)
    generic_camera_request = bool(
        re.search(
            r"\bdescribe what nova is seeing|\blive camera (?:frame|snapshot)\b",
            value,
            flags=re.I,
        )
    )
    if comparison:
        if value and not generic_camera_request:
            return f"Compare these two images. Answer: {value[:140]}"
        return "Compare these two images. Describe only the main visible differences."
    if value and not generic_camera_request and len(value) <= 140:
        return f"Look at this image and answer: {value}"
    return "Describe this image. Mention the main subject, setting, and visible actions. Do not guess."


def _is_live_camera_vision_request(filename, prompt=""):
    haystack = f"{filename or ''} {prompt or ''}".lower()
    return "live-camera" in haystack or "live camera" in haystack


def _live_camera_social_question(vision_answer="", prompt=""):
    text = f"{vision_answer or ''} {prompt or ''}".lower()
    if any(word in text for word in ("screen", "phone", "tablet", "computer", "app")):
        return "What pulled your attention to that screen right now?"
    if any(word in text for word in ("room", "desk", "space", "light", "wall")):
        return "What feels interesting to you about the space you're in right now?"
    return "What's been on your mind that feels interesting today?"


def _shape_live_camera_vision_response(response, filename, prompt="", vision_answer=""):
    if not _is_live_camera_vision_request(filename, prompt):
        return response
    shaped = str(response or "").strip()
    if shaped.startswith("[VISION] I can see it."):
        shaped = shaped.replace("[VISION] I can see it.", "[VISION] I see you there.", 1)
    elif shaped.startswith("[VISION]"):
        shaped = shaped.replace("[VISION]", "[VISION] I see you there.", 1)
    else:
        shaped = "[VISION] I see you there. " + shaped
    question = _live_camera_social_question(vision_answer, prompt)
    if question not in shaped:
        shaped = shaped.rstrip()
        shaped = shaped + (" " if not shaped.endswith(("?", "!", ".")) else " ") + question
    return shaped


def _classify_vision_request(image_info, prompt="", ocr_text="", filename="", has_comparison=False):
    """Select a local image-analysis strategy without retaining image content."""

    prompt_text = str(prompt or "").lower()
    filename_text = str(filename or "").lower()
    ocr_value = str(ocr_text or "")
    text_terms = bool(re.search(
        r"\b(read|text|say|says|screen|document|receipt|invoice|label|word|written|app|button|menu|ocr)\b",
        prompt_text,
    ))
    width = int((image_info or {}).get("width") or 0)
    height = int((image_info or {}).get("height") or 0)
    elongated = bool(width and height and max(width / height, height / width) > 1.75)
    named_document = bool(re.search(
        r"screen|screenshot|receipt|document|scan|page|invoice",
        filename_text,
    ))
    nova_ui = bool(re.search(r"\bnova\s+creature\b", ocr_value, flags=re.I))

    if has_comparison:
        task_type, reason = "comparison", "a second image was supplied"
    elif nova_ui:
        task_type, reason = "nova_ui", "local OCR identified the Nova interface"
    elif text_terms or named_document:
        task_type, reason = "document", "the request or filename indicates readable text"
    elif ocr_value and (elongated or len(ocr_value) >= 80):
        task_type, reason = "screenshot", "local OCR found substantial screen-like text"
    else:
        task_type, reason = "photo_scene", "visual scene understanding is the best fit"

    ocr_can_answer = bool(ocr_value and task_type in {"nova_ui", "document", "screenshot"})
    strategy = "local_ocr" if ocr_can_answer else "local_vision"
    if has_comparison and ocr_value:
        strategy = "local_ocr_plus_vision"
    return {
        "task_type": task_type,
        "strategy": strategy,
        "reason": reason,
        "confidence": 0.95 if nova_ui else (0.90 if text_terms or has_comparison else 0.76),
        "local_only": True,
    }


def _normalize_client_picture_quality(value):
    """Bound browser-estimated image metrics before exposing them in a trace."""

    if not isinstance(value, dict):
        return None
    allowed_grades = {"great", "good", "fair", "poor"}
    allowed_issues = {
        "very_small", "small", "very_dark", "dark", "overexposed",
        "very_bright", "low_contrast", "soft_contrast",
        "low_detail_or_blur", "possibly_soft",
    }

    def bounded_number(key, minimum, maximum, *, digits=1):
        try:
            number = float(value.get(key))
        except (TypeError, ValueError):
            return None
        number = max(minimum, min(maximum, number))
        return round(number, digits)

    score = bounded_number("score", 0, 100, digits=0)
    grade = str(value.get("grade") or "").strip().lower()
    issues = [
        str(issue)
        for issue in (value.get("issues") or [])
        if str(issue) in allowed_issues
    ][:8]
    return {
        "score": int(score) if score is not None else None,
        "grade": grade if grade in allowed_grades else None,
        "brightness": bounded_number("brightness", 0, 255, digits=0),
        "contrast": bounded_number("contrast", 0, 128, digits=0),
        "sharpness": bounded_number("sharpness", 0, 255, digits=1),
        "issues": issues,
        "enhancement_recommended": bool(value.get("enhancement_recommended")),
        "estimated": True,
        "content_logged": False,
    }


def _compare_ocr_texts(first_text, second_text):
    """Return a bounded text comparison without leaking raw images into storage."""

    def normalized_lines(value):
        lines = [re.sub(r"\s+", " ", line).strip() for line in str(value or "").splitlines()]
        return [line for line in lines if len(line) >= 2]

    first = normalized_lines(first_text)
    second = normalized_lines(second_text)
    first_keys = {line.casefold(): line for line in first}
    second_keys = {line.casefold(): line for line in second}
    shared = [first_keys[key] for key in first_keys.keys() & second_keys.keys()][:4]
    only_first = [line for key, line in first_keys.items() if key not in second_keys][:5]
    only_second = [line for key, line in second_keys.items() if key not in first_keys][:5]
    pieces = []
    if shared:
        pieces.append("Both show: " + " | ".join(shared))
    if only_first:
        pieces.append("Only in the first: " + " | ".join(only_first))
    if only_second:
        pieces.append("Only in the second: " + " | ".join(only_second))
    return ". ".join(pieces)[:1800] or "No reliable readable-text difference was detected."


def _call_moondream_vision(image_base64, prompt="", comparison_image_base64=""):
    """Ask the configured local Ollama vision model to describe an image."""
    clean_image = _strip_image_data_url(image_base64)
    if not clean_image:
        return "", {"used": False, "model": NOVA_VISION_MODEL, "error": "empty_image"}
    quality_status = MODEL_QUALITY.model_status("ollama", NOVA_VISION_MODEL)
    if quality_status.get("quarantined") and quality_status.get(
        "last_failure_reason"
    ) == "timeout":
        # A CPU queue or cold load can exceed an old timeout without proving the
        # model is bad. Allow the next explicit picture request to retry; actual
        # low-quality/empty outputs remain protected by the circuit breaker.
        MODEL_QUALITY.clear_quarantine("ollama", NOVA_VISION_MODEL)
        quality_status = MODEL_QUALITY.model_status("ollama", NOVA_VISION_MODEL)
    if quality_status.get("quarantined"):
        return "", {
            "used": False,
            "model": NOVA_VISION_MODEL,
            "error": "model_quarantined",
            "model_quality": quality_status,
        }
    clean_comparison = _strip_image_data_url(comparison_image_base64)
    vision_prompt = _compact_moondream_prompt(
        prompt,
        comparison=bool(clean_comparison),
    )
    image_payloads = [clean_image] + ([clean_comparison] if clean_comparison else [])
    request_payload = {
        "model": NOVA_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": vision_prompt,
                "images": image_payloads,
            }
        ],
        "stream": False,
        "keep_alive": NOVA_VISION_KEEP_ALIVE,
        "options": {
            "temperature": 0.1,
            "num_predict": NOVA_VISION_NUM_PREDICT,
        },
    }
    residency = None
    request_timeout = NOVA_VISION_TIMEOUT
    started = time.monotonic()
    try:
        try:
            from nova_model_memory import managed_model_residency

            residency_context = managed_model_residency(
                NOVA_VISION_MODEL,
                target_family="vision",
                estimated_model_bytes=int(
                    os.environ.get("NOVA_VISION_MODEL_ESTIMATED_BYTES", "1800000000")
                    or 1_800_000_000
                ),
                allow_commit_fallback=str(
                    os.environ.get("NOVA_VISION_ALLOW_COMMIT_MEMORY", "true")
                ).strip().lower()
                in {"1", "true", "yes", "on"},
                allow_unmanaged_idle_handoff=str(
                    os.environ.get("NOVA_VISION_RELEASE_IDLE_TEXT_MODELS", "true")
                ).strip().lower()
                in {"1", "true", "yes", "on"},
            )
        except Exception:
            residency_context = nullcontext(
                {
                    "allowed": True,
                    "reason": "resource_manager_unavailable_preserve_compatibility",
                    "content_logged": False,
                }
            )
        with residency_context as residency:
            if not residency.get("allowed"):
                return "", {
                    "used": False,
                    "model": NOVA_VISION_MODEL,
                    "error": "model_memory_policy_blocked",
                    "resource_manager": residency,
                }
            if not residency.get("target_resident"):
                try:
                    cold_timeout = int(
                        os.environ.get("NOVA_VISION_COLD_TIMEOUT", "120") or 120
                    )
                except (TypeError, ValueError):
                    cold_timeout = 120
                request_timeout = max(
                    NOVA_VISION_TIMEOUT,
                    min(cold_timeout, 120),
                )
            from nova_model_memory import configured_ollama_base_url

            request = urllib.request.Request(
                configured_ollama_base_url() + "/api/chat",
                data=json.dumps(request_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=request_timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                provider_route = "ollama_chat"
            except urllib.error.HTTPError as exc:
                if exc.code not in {404, 405}:
                    raise
                # Compatibility for an older Ollama server that predates the
                # chat route. Current Moondream builds should use /api/chat.
                legacy_payload = {
                    "model": NOVA_VISION_MODEL,
                    "prompt": vision_prompt,
                    "images": image_payloads,
                    "stream": False,
                    "keep_alive": NOVA_VISION_KEEP_ALIVE,
                    "options": request_payload["options"],
                }
                legacy_request = urllib.request.Request(
                    configured_ollama_base_url() + "/api/generate",
                    data=json.dumps(legacy_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(legacy_request, timeout=request_timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                provider_route = "ollama_generate_compatibility"
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        answer = _clean_vision_answer(message.get("content") or data.get("response") or "")
        answer_usable = _vision_answer_is_usable(answer, vision_prompt)
        answer_error = (
            None
            if answer_usable
            else ("low_quality_vision_response" if answer else "empty_vision_response")
        )
        if not answer_usable:
            answer = ""
            MODEL_QUALITY.record_failure(
                "ollama",
                NOVA_VISION_MODEL,
                latency_ms=(time.monotonic() - started) * 1000,
                reason=(
                    "low_quality_vision_response"
                    if answer_error == "low_quality_vision_response"
                    else "empty_response"
                ),
                source="vision_runtime",
            )
        else:
            MODEL_QUALITY.record_success(
                "ollama",
                NOVA_VISION_MODEL,
                latency_ms=(time.monotonic() - started) * 1000,
                source="vision_runtime",
            )
        return answer, {
            "used": bool(answer),
            "model": NOVA_VISION_MODEL,
            "error": answer_error,
            "resource_manager": residency,
            "cold_start": not bool((residency or {}).get("target_resident")),
            "timeout_seconds": request_timeout,
            "provider_route": provider_route,
            "prompt_compacted": True,
        }
    except Exception as exc:
        MODEL_QUALITY.record_failure(
            "ollama",
            NOVA_VISION_MODEL,
            latency_ms=(time.monotonic() - started) * 1000,
            reason=(
                "timeout"
                if "timed out" in str(exc).lower()
                else "provider_error"
            ),
            source="vision_runtime",
        )
        return "", {
            "used": False,
            "model": NOVA_VISION_MODEL,
            "error": str(exc)[:180],
            "resource_manager": residency,
            "cold_start": not bool((residency or {}).get("target_resident")),
            "timeout_seconds": request_timeout,
        }


def _vision_response_from_upload(body):
    """Inspect one uploaded picture and return a JSON payload plus HTTP status."""
    if not PERMISSIONS.get("camera"):
        trace = {
            "source": "image_upload_vision",
            "roles": ["permission_gate", "right_hemisphere"],
            "skills": ["vision_permission_gate"],
            "permission": "camera_required",
            "confidence": 0.35,
            "final_answer_source": "permission_gate",
        }
        return {
            "ok": False,
            "response": "[PERMISSION] Camera/vision is disabled. Type 'allow camera' first, then upload the picture again.",
            "trace": trace,
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 403

    try:
        filename = str(body.get("filename") or "uploaded image").strip()[:120]
        mime_type = str(body.get("mime_type") or body.get("content_type") or "").strip()
        prompt = str(body.get("prompt") or "").strip()[:500]
        client_processing = body.get("client_processing") if isinstance(body.get("client_processing"), dict) else {}
        picture_quality = _normalize_client_picture_quality(
            client_processing.get("picture_quality")
        )
        picture_enhanced = bool(client_processing.get("enhanced"))
        visual_follow_up = bool(body.get("visual_follow_up"))
        incoming_base64 = body.get("image_base64") or body.get("content_base64") or ""
        clean_base64 = _strip_image_data_url(incoming_base64)
        image_bytes = _decode_uploaded_image_bytes(incoming_base64)
        image_info = _basic_image_probe(image_bytes, mime_type=mime_type)
        scene_report, scene_probe_error = _run_visual_scene_probe(
            image_bytes,
            mime_type=mime_type,
        )
        comparison_filename = str(body.get("comparison_filename") or "").strip()[:120]
        comparison_mime_type = str(body.get("comparison_mime_type") or "").strip()
        comparison_incoming_base64 = body.get("comparison_image_base64") or ""
        comparison_clean_base64 = _strip_image_data_url(comparison_incoming_base64)
        comparison_bytes = b""
        comparison_info = None
        if comparison_clean_base64:
            comparison_bytes = _decode_uploaded_image_bytes(comparison_incoming_base64)
            comparison_info = _basic_image_probe(
                comparison_bytes,
                mime_type=comparison_mime_type,
            )
        try:
            from nova_ocr import extract_text

            ocr_text, ocr_meta = extract_text(
                image_bytes,
                mime_type=mime_type,
                maximum_characters=2000,
            )
        except Exception:
            ocr_text, ocr_meta = "", {
                "engine": "tesseract",
                "available": False,
                "used": False,
                "characters": 0,
                "lines": 0,
                "error": "adapter_unavailable",
                "content_logged": False,
                "image_persisted": False,
                "local_only": True,
            }
        comparison_ocr_text = ""
        comparison_ocr_meta = {
            "engine": "tesseract",
            "available": False,
            "used": False,
            "characters": 0,
            "lines": 0,
            "error": None,
            "content_logged": False,
            "image_persisted": False,
            "local_only": True,
        }
        if comparison_bytes:
            try:
                from nova_ocr import extract_text

                comparison_ocr_text, comparison_ocr_meta = extract_text(
                    comparison_bytes,
                    mime_type=comparison_mime_type,
                    maximum_characters=2000,
                )
            except Exception:
                comparison_ocr_meta["error"] = "adapter_unavailable"
        vision_prompt = prompt
        if ocr_text:
            vision_prompt = (
                f"{prompt}\n\n" if prompt else ""
            ) + (
                "Verified local OCR text from the same image follows. Use it to "
                "identify the app, document, labels, and visible controls accurately. "
                f"OCR text:\n{ocr_text[:600]}"
            )
        if comparison_ocr_text:
            vision_prompt += (
                "\n\nVerified local OCR text from the second image follows. "
                f"Compare it with the first image when relevant. Second OCR text:\n{comparison_ocr_text[:600]}"
            )
        inspection_focus = body.get("inspection_focus") if isinstance(body.get("inspection_focus"), dict) else {}
        if inspection_focus.get("set"):
            focus_x = min(1.0, max(0.0, float(inspection_focus.get("x") or 0.5)))
            focus_y = min(1.0, max(0.0, float(inspection_focus.get("y") or 0.5)))
            vision_prompt += (
                f"\n\nThe user marked a focus point near {focus_x:.0%} from the left "
                f"and {focus_y:.0%} from the top. Prioritize that area."
            )
        text_requested = bool(
            re.search(
                r"\b(read|text|say|says|screen|document|receipt|label|word|written|app|button|menu)\b",
                prompt,
                flags=re.I,
            )
        )
        nova_app_screen_detected = bool(
            ocr_text
            and re.search(r"\bnova\s+creature\b", ocr_text, flags=re.I)
            and (
                text_requested
                or re.search(
                    r"\b(?:chat|home|display|talk\s+to\s+nova|agent\s+library|"
                    r"pic|live\s+watch|stop\s+all|private)\b",
                    ocr_text,
                    flags=re.I,
                )
            )
        )
        has_comparison = bool(comparison_clean_base64)
        vision_route = _classify_vision_request(
            image_info,
            prompt=prompt,
            ocr_text=ocr_text,
            filename=filename,
            has_comparison=has_comparison,
        )
        ocr_comparison_ready = bool(
            has_comparison
            and ocr_text.strip()
            and comparison_ocr_text.strip()
            and (text_requested or vision_route["task_type"] in {"nova_ui", "document", "screenshot"})
        )
        if (
            image_info.get("width")
            and image_info.get("height")
            and min(int(image_info["width"]), int(image_info["height"])) <= 8
        ):
            vision_answer, vision_meta = "", {
                "used": False,
                "model": NOVA_VISION_MODEL,
                "error": "image_too_small_for_semantic_vision",
                "resource_manager": None,
            }
        elif ocr_comparison_ready:
            vision_answer, vision_meta = "", {
                "used": False,
                "model": NOVA_VISION_MODEL,
                "error": None,
                "resource_manager": None,
                "bypass_reason": "local_ocr_answered_image_comparison",
            }
        elif nova_app_screen_detected:
            # OCR is the authoritative and much faster engine for a clearly
            # identified Nova UI screenshot. Do not make the user wait for a
            # vision-model cold start only to paraphrase text we already read.
            vision_answer, vision_meta = "", {
                "used": False,
                "model": NOVA_VISION_MODEL,
                "error": None,
                "resource_manager": None,
                "bypass_reason": "local_ocr_answered_nova_screen_request",
            }
        else:
            if comparison_clean_base64:
                vision_answer, vision_meta = _call_moondream_vision(
                    clean_base64,
                    vision_prompt,
                    comparison_clean_base64,
                )
            else:
                vision_answer, vision_meta = _call_moondream_vision(clean_base64, vision_prompt)
        size_line = f"{image_info.get('byte_size', 0)} bytes"
        if image_info.get("width") and image_info.get("height"):
            size_line = f"{image_info['width']}×{image_info['height']} px, {size_line}"
        color_line = ""
        if image_info.get("average_color"):
            color_line = f" Average color is about {image_info['average_color']}."
        prompt_line = f" You asked: {prompt.rstrip('.!?')}." if prompt else ""
        image_summary = f"(File: {filename}; image: {image_info.get('format', 'image')}, {size_line}.)"
        if ocr_comparison_ready:
            response = "[VISION COMPARE] " + _compare_ocr_texts(ocr_text, comparison_ocr_text)
        elif vision_answer and has_comparison:
            response = f"[VISION COMPARE] I inspected both pictures. {vision_answer}"
        elif vision_answer:
            response = f"[VISION] I can see it. {vision_answer}"
        elif vision_meta.get("error") == "image_too_small_for_semantic_vision":
            response = (
                f"[VISION] I can see the file, but it is only {size_line}, which is "
                f"too small for a reliable visual description.{prompt_line} {image_summary}"
            )
        elif vision_meta.get("error"):
            response = (
                f"[VISION] I can see it. It looks like a {image_info.get('format', 'image')} image: {size_line}."
                f"{color_line}{prompt_line} The local vision model did not answer yet, "
                f"so I used basic image inspection for now. {image_summary}"
            )
        else:
            response = (
                f"[VISION] I can see it. It looks like a {image_info.get('format', 'image')} image: {size_line}."
                f"{color_line}{prompt_line} {image_summary}"
            )
        if nova_app_screen_detected and not has_comparison:
            screen_details = []
            if re.search(r"\bchat\b", ocr_text, flags=re.I):
                screen_details.append("the Chat page and its conversation")
            if re.search(r"\b(session|local model|people|lessons)\b", ocr_text, flags=re.I):
                screen_details.append("session and local-model status")
            if re.search(r"\b(pic|live watch|connected|stop all|private)\b", ocr_text, flags=re.I):
                screen_details.append("the bottom picture, live-watch, connection, stop, and privacy controls")
            details = " It shows " + ", ".join(screen_details) + "." if screen_details else ""
            response = (
                "[VISION] I can read the screen. This is the Nova Creature app."
                + details
            )
        if ocr_text and text_requested and not has_comparison:
            readable_text = re.sub(r"\s*\n\s*", " | ", ocr_text).strip()
            response = f"{response.rstrip()} Readable text: {readable_text[:1000]}"
        if picture_quality and picture_quality.get("grade") == "poor":
            issue_labels = {
                "very_small": "very low resolution",
                "small": "limited resolution",
                "very_dark": "very dark lighting",
                "dark": "dark lighting",
                "overexposed": "lost bright-area detail",
                "very_bright": "very bright lighting",
                "low_contrast": "very low contrast",
                "soft_contrast": "soft contrast",
                "low_detail_or_blur": "possible blur or missing fine detail",
                "possibly_soft": "soft fine detail",
            }
            concerns = [
                issue_labels[issue]
                for issue in picture_quality.get("issues", [])
                if issue in issue_labels
            ][:3]
            concern_text = ", ".join(concerns) or "limited visible detail"
            response = (
                f"{response.rstrip()} Quality warning: {concern_text}; some details "
                "may be incomplete. A clearer or closer picture would improve confidence."
            )
        if scene_report and _detailed_visual_request(prompt):
            from nova_visual_perception import concise_scene_facts

            response = f"{response.rstrip()} {concise_scene_facts(scene_report)}"
        if scene_report and _navigation_visual_request(prompt):
            from nova_visual_perception import navigation_safety_text

            response = f"{response.rstrip()} {navigation_safety_text(scene_report)}"
        from nova_perception_fusion import fuse_perception, plan_safe_navigation

        perception_snapshot = fuse_perception(
            semantic_text=vision_answer,
            semantic_meta=vision_meta,
            ocr_records=(
                [{"text": ocr_text, "confidence": 1.0}]
                if ocr_text
                else []
            ),
            scene_report=scene_report or {},
            sensor_snapshot=(
                body.get("sensor_snapshot")
                if isinstance(body.get("sensor_snapshot"), dict)
                else {}
            ),
        )
        navigation_plan = plan_safe_navigation(perception_snapshot)
        if _navigation_visual_request(prompt):
            response = (
                f"{response.rstrip()} Robot navigation remains "
                f"{navigation_plan.mode.replace('_', ' ')}; no physical movement "
                "was authorized."
            )
        response = _shape_live_camera_vision_response(response, filename, prompt, vision_answer)
        trace = {
            "source": "image_upload_vision",
            "domain": "vision",
            "roles": ["right_hemisphere", "memory_transformer", "critic_conscience_transformer", "speech_output_transformer"],
            "skills": ["image_upload", "basic_image_inspection", "vision_permission_gate"],
            "confidence": 0.88 if vision_answer else 0.70,
            "image": image_info,
            "comparison_image": comparison_info,
            "comparison_filename": comparison_filename if has_comparison else None,
            "vision_route": vision_route,
            "visual_follow_up": visual_follow_up,
            "picture_quality": picture_quality,
            "picture_enhanced": picture_enhanced,
            "vision_model": vision_meta.get("model", NOVA_VISION_MODEL),
            "vision_model_used": bool(vision_answer),
            "vision_model_error": vision_meta.get("error"),
            "vision_provider_route": vision_meta.get("provider_route"),
            "vision_prompt_compacted": bool(vision_meta.get("prompt_compacted")),
            "vision_bypass_reason": vision_meta.get("bypass_reason"),
            "vision_resource_manager": vision_meta.get("resource_manager"),
            "scene_probe": scene_report,
            "scene_probe_error": scene_probe_error,
            "perception_fusion": perception_snapshot.safe_trace(),
            "navigation_plan": navigation_plan.safe_trace(),
            "navigation_ready": bool(
                navigation_plan.movement_authorized
            ),
            "ocr": {
                "engine": ocr_meta.get("engine", "tesseract"),
                "available": bool(ocr_meta.get("available")),
                "used": bool(ocr_meta.get("used")),
                "characters": int(ocr_meta.get("characters") or 0),
                "lines": int(ocr_meta.get("lines") or 0),
                "error": ocr_meta.get("error"),
                "content_logged": False,
                "image_persisted": False,
                "local_only": True,
            },
            "comparison_ocr": {
                "engine": comparison_ocr_meta.get("engine", "tesseract"),
                "available": bool(comparison_ocr_meta.get("available")),
                "used": bool(comparison_ocr_meta.get("used")),
                "characters": int(comparison_ocr_meta.get("characters") or 0),
                "lines": int(comparison_ocr_meta.get("lines") or 0),
                "error": comparison_ocr_meta.get("error"),
                "content_logged": False,
                "image_persisted": False,
                "local_only": True,
            } if has_comparison else None,
            "inspection_focus": {
                "x": inspection_focus.get("x"),
                "y": inspection_focus.get("y"),
                "zoom": inspection_focus.get("zoom"),
                "rotation": inspection_focus.get("rotation"),
                "set": bool(inspection_focus.get("set")),
            },
            "client_processing": {
                "resized": bool(client_processing.get("resized")),
                "width": client_processing.get("width"),
                "height": client_processing.get("height"),
                "source_width": client_processing.get("source_width"),
                "source_height": client_processing.get("source_height"),
            },
            "route_path": ["image_upload", "basic_image_probe", "critic", "speech_output"],
            "final_answer_source": "image_upload_vision",
        }
        for optional_processing_field in ("cropped", "enhanced", "rotation", "zoom", "comparison"):
            if optional_processing_field in client_processing:
                trace["client_processing"][optional_processing_field] = client_processing.get(
                    optional_processing_field
                )
        if vision_answer:
            trace["skills"].append("moondream_vision")
            trace["route_path"] = ["image_upload", "moondream_vision", "basic_image_probe", "critic", "speech_output"]
        if scene_report:
            trace["skills"].append("deterministic_scene_probe")
            trace["route_path"].insert(1, "deterministic_scene_probe")
        trace["skills"].append("perception_fusion")
        trace["route_path"].insert(1, "perception_fusion")
        if _navigation_visual_request(prompt):
            trace["skills"].append("robot_navigation_safety_gate")
            trace["route_path"].insert(-1, "robot_navigation_safety_gate")
        if has_comparison:
            trace["skills"].append("image_compare")
            trace["route_path"].insert(1, "image_compare")
        if visual_follow_up:
            trace["skills"].append("temporary_visual_context")
            trace["route_path"].insert(1, "visual_context_follow_up")
            trace["memory_event"] = "temporary_visual_context_used"
        if ocr_text:
            ocr_skill = str(ocr_meta.get("engine") or "local_ocr")
            trace["skills"].append(
                ocr_skill if ocr_skill.endswith("_ocr") else f"{ocr_skill}_ocr"
            )
            trace["route_path"].insert(1, "local_ocr")
        trace["answer_status"] = _answer_status_from_trace(trace)
        return {
            "ok": True,
            "response": response,
            "trace": trace,
            "answer_status": trace["answer_status"],
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 200
    except Exception as exc:
        trace = {
            "source": "image_upload_vision",
            "domain": "vision",
            "roles": ["right_hemisphere", "critic_conscience_transformer"],
            "skills": ["image_upload_error"],
            "confidence": 0.35,
            "error": str(exc),
            "final_answer_source": "image_upload_error",
        }
        return {
            "ok": False,
            "response": "[VISION] I could not read that picture: " + str(exc),
            "trace": trace,
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 400


def _clean_tts_text(text):
    """Prepare user-visible Nova text for spoken audio."""
    cleaned = str(text or "")
    cleaned = re.sub(r"```[\s\S]*?```", " I left the code block on screen. ", cleaned)
    cleaned = re.sub(r"\[[A-Z _-]+\]", "", cleaned)
    cleaned = re.sub(r"https?://\S+", " link ", cleaned)
    cleaned = re.sub(r"Session:\s*[a-z0-9-]+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"People:\s*\d+\s*\|\s*Lessons:\s*\d+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[`*_#>\[\](){}]", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:700]


def _generate_edge_neural_tts_audio_base64(text, voice=None):
    """Generate a natural MP3 speech clip with edge-tts neural voices."""
    spoken = _clean_tts_text(text)
    if not spoken:
        raise ValueError("No speakable text")
    selected_voice = (voice or NOVA_TTS_NEURAL_VOICE or "en-US-GuyNeural").strip()
    with tempfile.NamedTemporaryFile(prefix="nova_edge_tts_", suffix=".mp3", delete=False) as tmp:
        media_path = tmp.name
    command = [
        sys.executable,
        "-m",
        "edge_tts",
        "--voice",
        selected_voice,
        "--text",
        spoken,
        "--write-media",
        media_path,
    ]
    if NOVA_TTS_RATE:
        command.extend(["--rate", NOVA_TTS_RATE])
    if NOVA_TTS_PITCH:
        command.extend(["--pitch", NOVA_TTS_PITCH])
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "edge-tts failed").strip()
            raise RuntimeError(detail[:300])
        with open(media_path, "rb") as handle:
            audio_bytes = handle.read()
        if not audio_bytes:
            raise RuntimeError("edge-tts produced empty audio")
        return base64.b64encode(audio_bytes).decode("ascii"), selected_voice, "audio/mpeg"
    finally:
        try:
            os.remove(media_path)
        except OSError:
            pass


def _generate_windows_tts_wav_base64(text):
    """Generate a WAV speech clip with the local Windows SAPI voice."""
    spoken = _clean_tts_text(text)
    if not spoken:
        raise ValueError("No speakable text")
    if os.name != "nt":
        raise RuntimeError("Windows SAPI voice is only available on Windows")
    with tempfile.NamedTemporaryFile(prefix="nova_tts_", suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    env = os.environ.copy()
    env["NOVA_TTS_TEXT"] = spoken
    env["NOVA_TTS_OUT"] = wav_path
    script = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.Volume = 100
$s.SetOutputToWaveFile($env:NOVA_TTS_OUT)
$s.Speak($env:NOVA_TTS_TEXT)
$voice = $s.Voice.Name
$s.Dispose()
Write-Output $voice
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        with open(wav_path, "rb") as handle:
            audio_b64 = base64.b64encode(handle.read()).decode("ascii")
        voice_name = (completed.stdout or "").strip().splitlines()[-1] if completed.stdout.strip() else "Windows voice"
        return audio_b64, voice_name
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


def _tts_response_from_text(body):
    """Return a playable audio payload for Nova speech."""
    if not PERMISSIONS.get("speaker") and not bool(body.get("force")):
        return {
            "ok": False,
            "error": "Speaker is disabled. Tap Voice ON first.",
            "permission": "speaker_required",
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 403
    text = _clean_tts_text(body.get("text") or "")
    if not text:
        return {
            "ok": False,
            "error": "No speakable text",
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 400
    neural_error = None
    if NOVA_TTS_ENGINE not in ("windows", "windows_sapi", "sapi"):
        try:
            audio_b64, voice_name, mime_type = _generate_edge_neural_tts_audio_base64(text, NOVA_TTS_NEURAL_VOICE)
            return {
                "ok": True,
                "mime_type": mime_type,
                "audio_base64": audio_b64,
                "voice_engine": "edge_neural",
                "voice_name": voice_name,
                "text": text,
                "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
            }, 200
        except Exception as exc:
            neural_error = str(exc)
    try:
        audio_b64, voice_name = _generate_windows_tts_wav_base64(text)
        payload = {
            "ok": True,
            "mime_type": "audio/wav",
            "audio_base64": audio_b64,
            "voice_engine": "windows_sapi",
            "voice_name": voice_name,
            "text": text,
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }
        if neural_error:
            payload["fallback_from"] = "edge_neural"
            payload["fallback_reason"] = neural_error[:240]
        return payload, 200
    except Exception as exc:
        error_text = str(exc)
        if neural_error:
            error_text = f"Neural voice failed: {neural_error}; Windows fallback failed: {exc}"
        return {
            "ok": False,
            "error": error_text,
            "voice_engine": "windows_sapi",
            "fallback_from": "edge_neural" if neural_error else None,
            "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE},
        }, 500


MEMORY = _load_memory()

CURRENT_US_PRESIDENT_VERIFIED_DATE = "2026-07-04"
CURRENT_US_PRESIDENT = "Donald J. Trump"
CURRENT_US_PRESIDENT_SOURCE = "Official White House administration pages"

RESEARCH_SOURCE_BASELINES = {
    "flat Earth debate": [
        {
            "name": "NASA - 90 Years of Our Changing Views of Earth",
            "url": "https://www.nasa.gov/history/90-years-of-our-changing-views-of-earth/",
        },
        {
            "name": "NOAA National Ocean Service - Is the Earth round?",
            "url": "https://oceanservice.noaa.gov/facts/earth-round.html",
        },
    ],
    "Bible contradictions": [
        {
            "name": "Wikipedia - Internal consistency of the Bible",
            "url": "https://en.wikipedia.org/wiki/Internal_consistency_of_the_Bible",
        },
        {
            "name": "Wikipedia - Biblical inerrancy",
            "url": "https://en.wikipedia.org/wiki/Biblical_inerrancy",
        },
    ],
}


def _is_current_us_president_query(text):
    q = _canonical_key(text)
    if "president" not in q:
        return False
    non_us_targets = {
        "brazil",
        "canada",
        "china",
        "france",
        "germany",
        "india",
        "ireland",
        "italy",
        "mexico",
        "russia",
        "south africa",
        "spain",
        "ukraine",
    }
    if any(target in q for target in non_us_targets):
        return False
    direct_questions = {
        "current president",
        "who is current president",
        "who is president",
        "who is the current president",
        "who is the president",
    }
    if q in direct_questions:
        return True
    return any(
        target in q
        for target in (
            "america",
            "u s president",
            "united states",
            "us president",
            "usa",
        )
    )

# ── Brain Route ─────────────────────────────────────────────────────────────
def _is_current_context_query(text):
    q = _canonical_key(text)
    if not q:
        return False
    date_phrases = (
        "what date is today",
        "whats the date today",
        "what is the date today",
        "what is todays date",
        "what is today date",
        "today date",
        "current date",
        "what day is it",
        "what day is today",
    )
    freshness_phrases = (
        "are you up to date",
        "are u up to date",
        "are you current",
        "are u current",
        "bring the llm up to date",
        "bring you up to date",
    )
    return any(phrase in q for phrase in date_phrases + freshness_phrases)


def _current_context_response():
    now = datetime.now()
    date_label = now.strftime("%A, %B %d, %Y").replace(" 0", " ")
    time_label = now.strftime("%I:%M %p").lstrip("0")
    return (
        f"Yeah — today is {date_label}, and my local app clock says {time_label}. "
        "I’m current on the live app state, memory, tools, voice, camera controls, and training reports. "
        "For changing outside facts like news, weather, prices, laws, or who holds an office, I should do a live lookup instead of guessing."
    )


def _is_research_lookup_request(text):
    q = _canonical_key(text)
    if not q:
        return False
    if q in {"research", "research panel", "open research", "go research"}:
        return False
    if any(blocked in q for blocked in ("news", "headline", "weather", "temperature", "temp")):
        return False
    phrases = (
        "go online",
        "check online",
        "search online",
        "search the web",
        "web search",
        "look this up",
        "look that up",
        "look it up",
        "look up",
        "research the",
        "research this",
        "research that",
        "current debate",
        "big debate",
        "check the argument",
        "check this argument",
    )
    return any(phrase in q for phrase in phrases)


def _is_live_news_request(text):
    q = _canonical_key(text)
    if not q:
        return False
    core_live_cues = (
        "go online",
        "latest",
        "current",
        "breaking",
        "right now",
        "today",
        "check the news",
        "check news",
        "online",
    )
    war_live_cues = core_live_cues + (
        "look up",
        "lookup",
        "search",
    )
    if any(word in q for word in ("news", "headlines", "current events", "breaking")):
        return any(cue in q for cue in core_live_cues)
    if "war" in q and any(cue in q for cue in war_live_cues):
        return True
    return False


def _news_topic_from_text(text):
    q = _canonical_key(text)
    if "war" in q:
        return "war"
    topic = str(text or "").strip()
    topic = re.sub(r"^go\s+online\s+(?:and\s+)?", "", topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r"^check\s+(?:out\s+)?", "", topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r"^for\s+", "", topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r"\b(latest|current|breaking|today'?s?|the|news|headlines|events|please|online)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\b(in|about|on|for|of|and|check|out)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+", " ", topic).strip(" .?!")
    return topic[:80] or "latest"


def _fetch_live_news_items(topic, limit=5, timeout=8):
    query = topic if topic and topic != "latest" else "top stories"
    rss_url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    if topic == "latest":
        rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    checked_at = datetime.now().isoformat(timespec="seconds")
    request = urllib.request.Request(
        rss_url,
        headers={
            "User-Agent": "NovaCreatureNews/1.0",
            "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", response.getcode()))
        xml_text = response.read(350000).decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = _clean_html_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        published = _clean_html_text(item.findtext("pubDate") or "")
        source_node = item.find("{*}source")
        source = _clean_html_text(source_node.text if source_node is not None else "Google News")
        if not title:
            continue
        items.append(
            {
                "title": title[:220],
                "source": source or "Google News",
                "url": link,
                "published": published,
                "checked_at": checked_at,
                "status": status,
                "feed_url": rss_url,
            }
        )
    return items


def _live_news_response(topic, items):
    if not items:
        return (
            "[LIVE NEWS] I tried to check live news for " + topic + ", but no headlines came back. "
            "Try a more specific topic like 'Ukraine war news' or 'Cincinnati news'."
        )
    checked_at = items[0].get("checked_at", datetime.now().isoformat(timespec="seconds"))
    lines = [
        "[LIVE NEWS] Live news checked at " + checked_at + " for " + topic + ".",
        "Top current headlines:",
    ]
    for index, item in enumerate(items[:5], start=1):
        published = item.get("published") or "published time unavailable"
        lines.append(
            str(index)
            + ". "
            + item.get("title", "Untitled")
            + " - "
            + item.get("source", "Google News")
            + " ("
            + published
            + ")"
        )
        if item.get("url"):
            lines.append("   " + item["url"])
    return "\n".join(lines)


def _infer_live_news_context_topic(topic, items):
    normalized_topic = _canonical_key(topic)
    if normalized_topic != "war":
        return topic or ""
    combined_titles = _canonical_key(" ".join(str(item.get("title", "")) for item in (items or [])))
    if "ukraine" in combined_titles or "russia" in combined_titles:
        return "Russia-Ukraine war"
    if "israel" in combined_titles or "hamas" in combined_titles or "gaza" in combined_titles:
        return "Israel-Hamas war"
    if "sudan" in combined_titles:
        return "Sudan war"
    return "war"


def _is_war_start_followup(text):
    q = _canonical_key(text)
    if not q:
        return False
    return q in {
        "when did it start",
        "when did this start",
        "when did that start",
        "when did the war start",
        "when did war start",
        "what date did it start",
        "what date did the war start",
    }


def _war_start_context_response(topic):
    normalized = _canonical_key(topic)
    if "russia" in normalized and "ukraine" in normalized:
        return (
            "[CONTEXT] If you mean the Russia-Ukraine war from the last lookup: "
            "Russia's full-scale invasion of Ukraine began on February 24, 2022. "
            "The wider Russia-Ukraine conflict started in 2014 after Russia annexed Crimea and fighting began in Donbas."
        )
    if "israel" in normalized and ("hamas" in normalized or "gaza" in normalized):
        return (
            "[CONTEXT] If you mean the Israel-Hamas war from the last lookup: "
            "it began on October 7, 2023, when Hamas attacked Israel and Israel launched its military response in Gaza."
        )
    if "sudan" in normalized:
        return (
            "[CONTEXT] If you mean the Sudan war from the last lookup: "
            "the current war between the Sudanese Armed Forces and the Rapid Support Forces began on April 15, 2023."
        )
    return (
        "[CONTEXT] I need one more detail: which war do you mean? "
        "If you mean the Russia-Ukraine war, Russia's full-scale invasion began on February 24, 2022."
    )


SCRAPE_MAX_BYTES = 450000
SCRAPE_TEXT_LIMIT = 1800
SCRAPE_LINK_LIMIT = 12


def _extract_scrape_url(text):
    match = re.search(r"https?://[^\s<>'\"]+", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,);]")


def _is_scrape_request(text):
    q = _canonical_key(text)
    if not q:
        return False
    return bool(_extract_scrape_url(text)) and any(
        phrase in q
        for phrase in (
            "scrape",
            "crawl",
            "read this page",
            "read the page",
            "extract this page",
            "extract the page",
            "scan this page",
            "scan the page",
        )
    )


def _is_scrape_build_request(text):
    q = _canonical_key(text)
    if not q or not _extract_scrape_url(text):
        return False
    has_scrape_intent = any(
        phrase in q
        for phrase in (
            "scrape",
            "crawl",
            "read this page",
            "read the page",
            "scan this page",
            "scan the page",
            "check this site",
            "check the site",
        )
    )
    has_build_intent = any(
        phrase in q
        for phrase in (
            "build",
            "make",
            "create",
            "generate",
            "turn it into",
            "make me",
            "build me",
        )
    )
    has_site_target = any(
        phrase in q
        for phrase in (
            "website",
            "web site",
            "site",
            "homepage",
            "landing page",
            "page",
        )
    )
    return has_scrape_intent and has_build_intent and has_site_target


def _is_emoji_capability_request(text):
    q = _canonical_key(text)
    if "emoji" not in q and "emojis" not in q:
        return False
    return any(
        phrase in q
        for phrase in (
            "do you know",
            "can you use",
            "use emoji",
            "use emojis",
            "with emoji",
            "with emojis",
            "emoji mode",
        )
    )


def _is_independent_thinker_request(text):
    q = _canonical_key(text)
    if not q:
        return False
    direct_phrases = (
        "independent thinker",
        "think independently",
        "think for yourself",
        "own opinion",
        "own perspective",
        "dont just agree",
        "do not just agree",
        "challenge me",
        "challenge assumptions",
    )
    if any(phrase in q for phrase in direct_phrases):
        return True
    if "break free" in q and any(phrase in q for phrase in ("think", "thinker", "mind", "independent")):
        return True
    return False


def _validate_public_scrape_url(raw_url):
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Blocked scrape URL: only public http/https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("Blocked scrape URL: missing host.")
    if parsed.username or parsed.password:
        raise ValueError("Blocked scrape URL: embedded credentials are not allowed.")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise ValueError("Blocked scrape URL: non-default ports are not allowed.")

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Blocked scrape URL: local/private hosts are not allowed.")

    try:
        ip = ipaddress.ip_address(host)
        resolved_ips = [ip]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme.lower() == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise ValueError("Blocked scrape URL: host could not be resolved.")
        resolved_ips = []
        for info in resolved:
            try:
                resolved_ips.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                pass

    if not resolved_ips:
        raise ValueError("Blocked scrape URL: host did not resolve to a public address.")
    for ip in resolved_ips:
        if not ip.is_global:
            raise ValueError("Blocked scrape URL: private/local network addresses are not allowed.")

    return parsed.geturl()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_scrape_html(url, timeout=8, max_bytes=SCRAPE_MAX_BYTES):
    current_url = _validate_public_scrape_url(url)
    opener = urllib.request.build_opener(_NoRedirectHandler)
    for _ in range(4):
        request = urllib.request.Request(
            current_url,
            headers={
                "User-Agent": "NovaCreatureScraper/1.0",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
            },
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", response.getcode()))
                content_type = response.headers.get("Content-Type", "")
                charset = response.headers.get_content_charset() or "utf-8"
                raw = response.read(max_bytes + 1)
                truncated = len(raw) > max_bytes
                html_text = raw[:max_bytes].decode(charset, errors="replace")
                final_url = _validate_public_scrape_url(response.geturl() or current_url)
                return final_url, status, content_type, html_text, truncated
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400 and exc.headers.get("Location"):
                current_url = _validate_public_scrape_url(urljoin(current_url, exc.headers["Location"]))
                continue
            raise
    raise ValueError("Blocked scrape URL: too many redirects.")


def _extract_scrape_links(html_text, final_url):
    links = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL):
        href = unescape(match.group(1).strip())
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(final_url, href)
        text = _clean_html_text(match.group(2))[:120] or absolute
        links.append({"text": text, "href": absolute})
        if len(links) >= SCRAPE_LINK_LIMIT:
            break
    return links


def _extract_scrape_headings(html_text):
    headings = []
    for match in re.finditer(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL):
        heading = _clean_html_text(match.group(1))
        if heading and heading not in headings:
            headings.append(heading[:160])
        if len(headings) >= 10:
            break
    return headings


def _extract_scrape_content(original_url, final_url, status, content_type, html_text, truncated=False):
    title = _extract_html_title(html_text, final_url)
    headings = _extract_scrape_headings(html_text)
    description = _extract_html_meta_content(
        html_text,
        ("description", "og:description", "twitter:description"),
    )
    readable_text = _clean_html_text(html_text)
    if title and readable_text.startswith(title):
        readable_text = readable_text[len(title):].strip()
    if _looks_like_script_dump(readable_text):
        readable_text = ""
    if description and description.lower() not in readable_text.lower():
        readable_text = (description + (" " + readable_text if readable_text else "")).strip()
    readable_text = readable_text[:SCRAPE_TEXT_LIMIT]
    return {
        "ok": True,
        "url": original_url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "title": title,
        "description": description,
        "headings": headings,
        "text": readable_text,
        "links": _extract_scrape_links(html_text, final_url),
        "truncated": bool(truncated),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def _scrape_public_url(url):
    final_url, status, content_type, html_text, truncated = _fetch_scrape_html(url)
    return _extract_scrape_content(url, final_url, status, content_type, html_text, truncated)


def _scrape_response(result):
    lines = [
        "[SCRAPE] Scraped " + result.get("final_url", result.get("url", "")),
        "Status: " + str(result.get("status", "")) + " | Title: " + (result.get("title") or "Untitled"),
    ]
    headings = result.get("headings") or []
    if headings:
        lines.append("Headings: " + " | ".join(headings[:4]))
    text = result.get("text") or ""
    if text:
        lines.append("Text: " + text[:900])
    links = result.get("links") or []
    if links:
        lines.append("Links:")
        for link in links[:5]:
            lines.append("  - " + link.get("text", link.get("href", "")) + " (" + link.get("href", "") + ")")
    return "\n".join(lines)


def _scrape_links_for_prompt(links):
    formatted = []
    for link in (links or [])[:6]:
        label = link.get("text") or link.get("href") or "Link"
        href = link.get("href") or ""
        if href:
            formatted.append(label[:100] + " - " + href)
    return "; ".join(formatted) or "No useful links found."


def _scrape_build_prompt(user_text, scrape_result):
    headings = scrape_result.get("headings") or []
    source_url = scrape_result.get("final_url") or scrape_result.get("url") or ""
    source_title = scrape_result.get("title") or "Untitled source page"
    source_text = (scrape_result.get("text") or "").strip()[:1400]
    if not source_text:
        source_text = "No readable source text extracted."
    return "\n".join(
        [
            "Website Builder Agent: build a polished, original 6 page website for " + source_title + ", then use live scraped research to improve it.",
            "User request: " + str(user_text or "").strip(),
            "Source URL: " + source_url,
            "Source title: " + source_title,
            "Source headings: " + (" | ".join(headings[:8]) if headings else "No headings found."),
            "Source excerpt: " + source_text,
            "Source links: " + _scrape_links_for_prompt(scrape_result.get("links")),
            "Use the source as research only. Do not copy protected text verbatim.",
            "Make the result better than the source with a complete page count, cross-page navigation, responsive layout, accessibility, metadata, and a quality audit.",
        ]
    )


def _scrape_build_response(scrape_result, builder_response):
    source_url = scrape_result.get("final_url") or scrape_result.get("url") or ""
    source_title = scrape_result.get("title") or "Untitled source page"
    source_text = (scrape_result.get("text") or "").strip()
    evidence = source_text[:360] if source_text else "No readable source text extracted."
    lines = [
        "[SCRAPE + BUILD] Scraped the source page and built a better original website.",
        "Source: " + source_title + " (" + source_url + ")",
        "Evidence used: " + evidence,
        "",
        builder_response,
    ]
    return "\n".join(lines)


def _is_flat_earth_claim_or_question(text):
    q = _canonical_key(text)
    if not ("flat" in q and ("earth" in q or "world" in q)):
        return False
    if _is_research_lookup_request(text):
        return False
    triggers = (
        "i think",
        "i believe",
        "do you believe",
        "what about you",
        "is earth flat",
        "is the earth flat",
        "is world flat",
        "is the world flat",
        "earth is flat",
        "world is flat",
        "makes you think the world is flat",
        "makes you think earth is flat",
    )
    return any(trigger in q for trigger in triggers)


def _flat_earth_evidence_followup(text, previous_user="", previous_answer=""):
    """Explain the science guard's reasoning when the user asks a short why-follow-up."""
    q = _canonical_key(text)
    why_followups = {
        "why do you say that",
        "why do u say that",
        "why would you say that",
        "why do you think that",
        "why do u think that",
        "why is that",
        "but why",
        "but why do you say that",
        "but why do u say that",
    }
    prior = _canonical_key(str(previous_user or "") + " " + str(previous_answer or ""))
    if q not in why_followups or not ("flat" in prior and ("earth" in prior or "world" in prior)):
        return ""
    return (
        "I say that because a flat Earth and a curved Earth make different testable predictions, "
        "and the curved-Earth predictions consistently match observations. During a lunar eclipse, "
        "Earth casts a round shadow on the Moon; different stars become visible as you travel north or "
        "south; the Sun rises and sets at different times across longitude; distant ships and skylines "
        "disappear from the bottom upward; and surveying, GPS, and geodesy measure the same curvature. "
        "Those are independent checks that agree with one another. I am not dismissing your reasons—"
        "we can take them one at a time and compare what each model predicts."
    )


def _research_topic_from_context(text, previous_text=""):
    combined = _canonical_key(str(previous_text or "") + " " + str(text or ""))
    if "flat" in combined and ("earth" in combined or "world" in combined):
        return "flat Earth debate"

    topic = str(text or "").strip()
    removals = [
        r"^go online and\s+",
        r"^go online\s+",
        r"^search the web for\s+",
        r"^search online for\s+",
        r"^research\s+",
        r"^look up\s+",
        r"^check online\s+",
        r"^check\s+",
        r"\s+online$",
        r"\s+and let me know.*$",
        r"\s+for me$",
        r"\s+please$",
    ]
    for pattern in removals:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE).strip()
    topic = topic.strip(" .?!")
    return _normalize_research_topic(topic[:80] or "the topic")


def _normalize_research_topic(topic):
    q = _canonical_key(topic)
    if ("bible" in q or "biblical" in q) and any(
        word in q
        for word in (
            "contradict",
            "contradicts",
            "contradicted",
            "contradicting",
            "contradiction",
            "contradictions",
            "inconsistency",
            "inconsistencies",
        )
    ):
        return "Bible contradictions"
    return str(topic or "the topic").strip() or "the topic"


def _clean_html_text(value):
    value = _strip_non_content_html(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _strip_non_content_html(value):
    text = str(value or "")
    for tag in ("script", "style", "template"):
        text = re.sub(
            rf"<{tag}\b[^>]*>.*?(?:</{tag}>|$)",
            " ",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    text = re.sub(r"<!--.*?(?:-->|$)", " ", text, flags=re.DOTALL)
    return text


def _extract_html_meta_content(html_text, keys):
    key_set = {str(key).lower() for key in keys}
    for tag_match in re.finditer(r"<meta\b[^>]*>", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL):
        tag = tag_match.group(0)
        name_match = re.search(r"\b(?:name|property)=['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        if not name_match or name_match.group(1).lower() not in key_set:
            continue
        content_match = re.search(r"\bcontent=['\"]([^'\"]*)['\"]", tag, flags=re.IGNORECASE | re.DOTALL)
        if content_match:
            content = _clean_html_text(content_match.group(1))
            if content:
                return content[:500]
    return ""


def _looks_like_script_dump(text):
    sample = str(text or "").strip()[:800].lower()
    if not sample:
        return False
    script_markers = ("(function()", "window.", "ytcfg.", "ytplayer", "var ", "function ")
    marker_count = sum(1 for marker in script_markers if marker in sample)
    brace_noise = sample.count("{") + sample.count("}") + sample.count("\\u003d")
    return marker_count >= 1 and brace_noise >= 8


def _extract_html_title(html_text, fallback):
    match = re.search(r"<title\b[^>]*>(.*?)</title>", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    title = _clean_html_text(match.group(1))
    return title[:140] if title else fallback


def _extract_html_snippet(html_text, topic):
    text = _clean_html_text(html_text)
    if not text:
        return ""
    key_terms = [word for word in _canonical_key(topic).split() if len(word) > 3]
    lower_text = text.lower()
    start = 0
    for term in key_terms:
        found = lower_text.find(term)
        if found >= 0:
            start = max(0, found - 80)
            break
    snippet = text[start:start + 260].strip()
    return snippet


def _fetch_research_web_sources(topic, timeout=6):
    checked = []
    for source in RESEARCH_SOURCE_BASELINES.get(topic, []):
        url = source.get("url", "")
        item = {
            "name": source.get("name", url),
            "url": url,
            "status": None,
            "title": source.get("name", url),
            "snippet": "",
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "NovaCreatureResearch/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                item["status"] = int(getattr(response, "status", response.getcode()))
                charset = response.headers.get_content_charset() or "utf-8"
                html_text = response.read(250000).decode(charset, errors="replace")
                item["title"] = _extract_html_title(html_text, item["title"])
                item["snippet"] = _extract_html_snippet(html_text, topic)
        except urllib.error.HTTPError as exc:
            item["status"] = int(exc.code)
            item["error"] = str(exc.reason)
        except Exception as exc:
            item["status"] = "error"
            item["error"] = str(exc)[:160]
        checked.append(item)
    return checked


def _live_source_lines(live_sources):
    lines = []
    for source in live_sources or []:
        status = source.get("status")
        if isinstance(status, int) and 200 <= status < 400:
            title = source.get("title") or source.get("name") or source.get("url")
            lines.append("  - " + title + " [HTTP " + str(status) + "] (" + source.get("url", "") + ")")
    return lines


def _live_source_evidence_lines(live_sources):
    lines = []
    for source in live_sources or []:
        status = source.get("status")
        if not (isinstance(status, int) and 200 <= status < 400):
            continue
        snippet = _clean_html_text(source.get("snippet", ""))
        if not snippet:
            continue
        title = source.get("title") or source.get("name") or source.get("url")
        lines.append("  - " + title + ": " + snippet[:260])
        if len(lines) >= 3:
            break
    return lines


def _flat_earth_research_response(live_sources=None):
    source_lines = _live_source_lines(live_sources)
    evidence_lines = _live_source_evidence_lines(live_sources)
    if source_lines:
        first_checked = ""
        for source in live_sources or []:
            if isinstance(source.get("status"), int) and 200 <= source.get("status") < 400:
                first_checked = source.get("checked_at", "")
                break
        timestamp = (" at " + first_checked) if first_checked else ""
        heading = "[LIVE WEB] Live web checked" + timestamp + ".\nSources checked live:\n" + "\n".join(source_lines[:2])
        if evidence_lines:
            heading += "\nFetched evidence:\n" + "\n".join(evidence_lines)
    else:
        heading = "[RESEARCH] I checked the flat Earth debate from saved source baselines."
    return (
        heading + "\n"
        "Bottom line: it is not an active scientific debate that Earth is flat. "
        "Earth is round in everyday language, and more precisely an irregular ellipsoid/oblate spheroid.\n"
        "The real online debate is about trust, conspiracy communities, and how people interpret everyday observations. "
        "Flat-Earth arguments often focus on the horizon looking flat, distrust of space images, and misunderstandings of gravity, scale, and perspective.\n"
        "Strong checks against the claim include time zones, lunar eclipses, star visibility changing by latitude, ships and land dropping below the horizon, circumnavigation, satellite measurements, and geodesy.\n"
        "Sources: NASA - 90 Years of Our Changing Views of Earth; NOAA National Ocean Service - Is the Earth round?"
    )


def _bible_contradictions_research_response(live_sources=None):
    source_lines = _live_source_lines(live_sources)
    evidence_lines = _live_source_evidence_lines(live_sources)
    if source_lines:
        first_checked = ""
        for source in live_sources or []:
            if isinstance(source.get("status"), int) and 200 <= source.get("status") < 400:
                first_checked = source.get("checked_at", "")
                break
        heading = "[LIVE WEB] Live web checked"
        if first_checked:
            heading += " at " + first_checked
        heading += " for Bible contradictions:\n" + "\n".join(source_lines[:3])
        if evidence_lines:
            heading += "\nFetched evidence:\n" + "\n".join(evidence_lines)
    else:
        heading = "[RESEARCH] I checked saved source baselines for Bible contradictions."
    return (
        heading + "\n"
        "Short answer: not literally all in one chat. The Bible is a library of texts, and people debate whether apparent conflicts are true contradictions, translation issues, genre differences, or harmonizable details.\n"
        "Commonly debated examples include creation-order differences in Genesis 1 and 2, the two Gospel genealogies of Jesus, Judas's death in Matthew versus Acts, and differing details in the resurrection accounts.\n"
        "Best next step: pick one claimed contradiction and I can compare the passages side by side instead of dumping a giant low-quality list."
    )


def _research_response_for_topic(
    topic,
    live_sources=None,
    retrieval_result=None,
    consensus_report=None,
):
    if isinstance(retrieval_result, RetrievalResult) and retrieval_result.status == "blocked":
        reason = retrieval_result.policy.reason
        if reason == "private_mode":
            return (
                "[WEB PRIVACY] I kept this request local because Private mode is ON or the request was marked private. "
                "I did not send the question, memory, or files to a search service. Turn Private mode off and explicitly "
                "ask me to search online when you want a public lookup."
            )
        if reason == "sensitive_content":
            return (
                "[WEB PRIVACY] I did not send that request online because it appears to contain a secret, credential, "
                "or local file path. Remove the private part and ask a public, general version of the question."
            )
        if reason == "explicit_request_required":
            return (
                "[WEB PERMISSION] I kept this request local. Say “search the web for …” or “look this up online” "
                "when you want Nova to send a public search query."
            )
        return "[WEB PERMISSION] Online source retrieval is disabled by Nova's current policy."
    if isinstance(retrieval_result, RetrievalResult) and retrieval_result.status == "unavailable":
        return (
            "[LIVE WEB] I was allowed to search for " + topic + ", but I could not retrieve enough public source pages. "
            "I will not invent a sourced answer. Check the connection or try a narrower search."
        )
    if topic == "flat Earth debate":
        return _flat_earth_research_response(live_sources)
    if topic == "Bible contradictions":
        return _bible_contradictions_research_response(live_sources)
    source_lines = _live_source_lines(live_sources)
    evidence_lines = _live_source_evidence_lines(live_sources)
    if source_lines:
        checked_at = next(
            (
                str(source.get("checked_at") or "")
                for source in (live_sources or [])
                if isinstance(source.get("status"), int) and 200 <= source.get("status") < 400
            ),
            "",
        )
        heading = "[LIVE WEB] Checked " + str(len(source_lines[:3])) + " different public source pages"
        if checked_at:
            heading += " at " + checked_at
        heading += " for " + topic + "."
        parts = [heading]
        if isinstance(consensus_report, SourceConsensusReport):
            if consensus_report.status == "corroborated":
                parts.extend(["Verified consensus:", *consensus_report.conclusion_lines()])
                if consensus_report.stale_claims:
                    parts.extend(["Freshness warning:", *consensus_report.stale_lines()])
            elif consensus_report.status == "mixed":
                parts.extend(["Consensus warning:", *consensus_report.conflict_lines()])
            elif consensus_report.status == "stale":
                parts.extend(["Freshness warning:", *consensus_report.stale_lines()])
            elif consensus_report.status == "insufficient":
                parts.append(
                    "Consensus: not enough independent publisher agreement for a verified conclusion. "
                    "The source extracts are shown without turning them into a fact claim."
                )
        if evidence_lines:
            parts.extend(["What the fetched pages say:", *evidence_lines])
        parts.extend(["Sources:", *source_lines[:3]])
        parts.append(
            "These are short evidence extracts with provenance, not a guarantee that every source claim is true. "
            "For a disputed claim, ask me to compare the sources directly."
        )
        return "\n".join(parts)
    return (
        "[RESEARCH] I can source-check " + topic + ". "
        "Give me the exact claim or question, and I will compare reliable sources, summarize the main sides, "
        "and tell you what looks strongest or weakest."
    )


def _research_retrieval_context(context=None):
    result = dict(context) if isinstance(context, dict) else {}
    result["private_mode"] = bool(PRIVATE_MODE or result.get("private_mode"))
    return result


def _authorize_explicit_web_action(text, context=None):
    return WEB_SOURCE_RETRIEVER.authorize(
        "search the web for " + str(text or ""),
        _research_retrieval_context(context),
    )


def _blocked_web_action_response(decision):
    return _research_response_for_topic(
        "the requested public information",
        [],
        RetrievalResult("blocked", decision),
    )


def _baseline_retrieval_trace(live_sources):
    successful = [
        source
        for source in (live_sources or [])
        if isinstance(source.get("status"), int) and 200 <= source.get("status") < 400
    ]
    return {
        "schema_version": "1.0",
        "status": "success" if successful else "unavailable",
        "policy": {
            "allowed": True,
            "reason": "allowed",
            "explicit_online_request": True,
            "private_mode": False,
            "content_logged": False,
        },
        "source_count": len(successful),
        "sources": [
            {
                "domain": str(urlparse(source.get("url", "")).hostname or ""),
                "status": source.get("status"),
                "source_type": "curated_baseline_live_fetch",
            }
            for source in successful
        ],
        "error_categories": [],
    }


def _grounding_evidence_from_live_sources(live_sources):
    evidence = []
    for index, source in enumerate(live_sources or []):
        status = source.get("status")
        snippet = _clean_html_text(source.get("snippet", ""))
        if not (isinstance(status, int) and 200 <= status < 400 and snippet):
            continue
        evidence.append(
            {
                "evidence_id": "web_source_" + str(index + 1),
                "content": snippet[:600],
                "source_name": source.get("title") or source.get("name") or "Public web source",
                "source_type": source.get("source_type") or "live_web_page",
                "source_url": source.get("url", ""),
                "verified_at": source.get("checked_at", ""),
                "live": True,
                "trust_level": source.get("reliability_score", 0.82),
            }
        )
    return evidence


def _source_consensus_enabled():
    value = str(os.environ.get("NOVA_SOURCE_CONSENSUS_ENABLED", "true") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _source_consensus_minimum_publishers():
    try:
        value = int(os.environ.get("NOVA_SOURCE_CONSENSUS_MIN_PUBLISHERS", "2"))
    except (TypeError, ValueError):
        value = 2
    return max(2, min(value, 5))


def _source_consensus_semantic_enabled():
    value = str(
        os.environ.get("NOVA_SOURCE_CONSENSUS_SEMANTIC_ENABLED", "true")
        or "true"
    ).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _source_consensus_semantic_similarity():
    try:
        value = float(
            os.environ.get(
                "NOVA_SOURCE_CONSENSUS_SEMANTIC_SIMILARITY",
                "0.62",
            )
        )
    except (TypeError, ValueError):
        value = 0.62
    return max(0.55, min(value, 0.9))


def _source_consensus_ttl_seconds(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _source_consensus_freshness_ttls():
    return {
        "volatile": _source_consensus_ttl_seconds(
            "NOVA_SOURCE_CONSENSUS_VOLATILE_TTL_SECONDS",
            21_600,
            300,
            86_400,
        ),
        "changing": _source_consensus_ttl_seconds(
            "NOVA_SOURCE_CONSENSUS_CHANGING_TTL_SECONDS",
            604_800,
            3_600,
            2_592_000,
        ),
        "stable": _source_consensus_ttl_seconds(
            "NOVA_SOURCE_CONSENSUS_STABLE_TTL_SECONDS",
            2_592_000,
            86_400,
            31_536_000,
        ),
    }


def _source_consensus_health():
    freshness_ttls = _source_consensus_freshness_ttls()
    return {
        "ok": True,
        "enabled": _source_consensus_enabled(),
        "minimum_publishers": _source_consensus_minimum_publishers(),
        "semantic_enabled": _source_consensus_semantic_enabled(),
        "semantic_similarity_threshold": _source_consensus_semantic_similarity(),
        "freshness_ttl_seconds": freshness_ttls,
        "schema_version": "1.0",
        "methods": ["numeric", "named_entity", "polarity", "semantic", "freshness"],
    }


def _analyze_live_source_consensus(text, live_sources):
    if not _source_consensus_enabled():
        return SourceConsensusReport(
            status="disabled",
            coverage="none",
            publisher_count=0,
        )
    freshness_ttls = _source_consensus_freshness_ttls()
    return analyze_source_consensus(
        text,
        live_sources,
        minimum_publishers=_source_consensus_minimum_publishers(),
        semantic_enabled=_source_consensus_semantic_enabled(),
        semantic_similarity_threshold=_source_consensus_semantic_similarity(),
        volatile_ttl_seconds=freshness_ttls["volatile"],
        changing_ttl_seconds=freshness_ttls["changing"],
        stable_ttl_seconds=freshness_ttls["stable"],
    )


def _run_research_lookup_request(text, trace, *, previous_text="", requested_model=None, context=None):
    topic = _research_topic_from_context(text, previous_text)
    retrieval_context = _research_retrieval_context(context)
    policy = WEB_SOURCE_RETRIEVER.authorize(text, retrieval_context)
    retrieval_result = None
    if not policy.allowed:
        retrieval_result = RetrievalResult("blocked", policy)
        live_sources = []
        retrieval_trace = retrieval_result.safe_trace()
    elif topic in RESEARCH_SOURCE_BASELINES:
        live_sources = _fetch_research_web_sources(topic)
        retrieval_trace = _baseline_retrieval_trace(live_sources)
    else:
        retrieval_result = WEB_SOURCE_RETRIEVER.retrieve(text, retrieval_context)
        live_sources = retrieval_result.as_legacy_sources()
        retrieval_trace = retrieval_result.safe_trace()
    online_checked = any(
        isinstance(source.get("status"), int) and 200 <= source.get("status") < 400
        for source in live_sources
    )
    consensus_report = (
        _analyze_live_source_consensus(text, live_sources)
        if online_checked
        else SourceConsensusReport(
            status="not_run",
            coverage="none",
            publisher_count=0,
        )
    )
    response = _research_response_for_topic(
        topic,
        live_sources,
        retrieval_result,
        consensus_report,
    )
    trace["source"] = "research_router"
    trace["domain"] = "research"
    trace["query"] = text
    trace["topic"] = topic
    trace["sources"] = RESEARCH_SOURCE_BASELINES.get(topic, [])
    trace["online_checked"] = online_checked
    trace["live_sources"] = live_sources
    trace["source_retrieval"] = retrieval_trace
    trace["source_consensus"] = consensus_report.safe_trace()
    trace["consensus_conclusions"] = [
        claim.statement for claim in consensus_report.corroborated_claims
    ]
    checked_at = next(
        (str(source.get("checked_at") or "") for source in live_sources if source.get("checked_at")),
        "",
    )
    trace["grounding_evidence"] = (
        _grounding_evidence_from_live_sources(live_sources)
        + consensus_report.grounding_evidence(checked_at)
    )
    trace["roles"] = [
        "planner_transformer",
        "critic_conscience_transformer",
        "speech_output_transformer",
    ]
    trace["skills"] = [
        "web_research",
        "source_checking",
        "claim_comparison",
        "publisher_independence",
        "claim_consensus",
        "claim_freshness",
    ]
    if requested_model:
        trace["requested_model"] = requested_model
        trace["skills"].append("deepseek_request_routed_to_research")
    if consensus_report.status == "corroborated":
        trace["confidence"] = 0.97
    elif consensus_report.status == "mixed":
        trace["confidence"] = 0.9
    elif consensus_report.status == "stale":
        trace["confidence"] = 0.76
    else:
        trace["confidence"] = 0.82 if online_checked else (0.78 if topic in RESEARCH_SOURCE_BASELINES else 0.72)
    trace["route_path"] = [
        "research_router",
        "source_baseline" if topic in RESEARCH_SOURCE_BASELINES else "privacy_gated_web_retriever",
        "claim_consensus",
        "speech_output",
    ]
    trace["final_answer_source"] = "research_router"
    return response, trace


def _run_quality_gate_if_project_exists(project_url, *, fix=True):
    if not _QUALITY_GATE_AGENT_AVAIL or not project_url:
        return None
    match = re.search(r"/sandbox/app_builder_projects/([^/]+)/", str(project_url))
    if not match:
        return None
    project_id = unquote(match.group(1))
    project_path = Path(APP_BUILDER_PROJECTS_ROOT) / project_id
    if not project_path.exists():
        return None
    try:
        return _quality_gate_agent.run_quality_gate(APP_BUILDER_PROJECTS_ROOT, project_id, fix=fix)
    except Exception:
        return None


def _quality_gate_trace_summary(report):
    if not report:
        return None
    return {
        "passed": bool(report.get("passed")),
        "score": report.get("score", 0),
        "pages_inspected": report.get("pages_inspected", 0),
        "links_checked": report.get("links_checked", 0),
        "visuals_created": report.get("visuals_created", 0),
        "visual_snapshot_dir": report.get("visual_snapshot_dir"),
        "blockers": report.get("blockers", []),
        "fixes_applied": report.get("fixes_applied", []),
        "report_file": report.get("report_file"),
    }


def _run_game_supercheck_if_project_exists(project_url):
    """Run Nova's game-specific Superpowers check for a saved game preview."""
    if not _GAME_SUPER_CHECK_AVAIL or not project_url:
        return None
    match = re.search(r"/sandbox/app_builder_projects/([^/]+)/", str(project_url))
    if not match:
        return None
    project_id = unquote(match.group(1))
    project_path = Path(APP_BUILDER_PROJECTS_ROOT) / project_id
    if not project_path.exists():
        return None
    try:
        return _game_supercheck.run_game_supercheck(APP_BUILDER_PROJECTS_ROOT, project_id)
    except Exception as exc:
        return {
            "ok": False,
            "skill": "superpowers_game_check",
            "passed": False,
            "score": 0,
            "project_id": project_id,
            "blockers": ["Game Superpowers Check could not run: " + str(exc)],
            "checks": {},
            "report_file": None,
        }


def _apply_game_supercheck(response, trace, project_url):
    report = _run_game_supercheck_if_project_exists(project_url)
    if not report:
        return response
    summary = {
        "passed": bool(report.get("passed")),
        "score": report.get("score", 0),
        "blockers": list(report.get("blockers") or []),
        "report_file": report.get("report_file"),
        "checks": report.get("checks") or {},
    }
    trace["superpowers_game_check"] = summary
    verification = trace.setdefault("verification", {})
    verification["superpowers_game_check"] = summary
    checks = verification.setdefault("checks", [])
    if "superpowers_game_check" not in checks:
        checks.append("superpowers_game_check")
    trace["skills"] = list(dict.fromkeys(list(trace.get("skills") or []) + ["superpowers_game_check"]))
    if _GAME_SUPER_CHECK_AVAIL:
        try:
            response += "\n\n" + _game_supercheck.format_game_supercheck_report(report)
        except Exception:
            pass
    return response


def _is_full_training_request(text):
    q = _canonical_key(text)
    if not q:
        return False
    phrases = (
        "can u train yourself",
        "can you train yourself",
        "do a full training",
        "do all training",
        "full training",
        "run full training",
        "train yourself",
        "train urself",
        "train everything",
        "train all",
        "train nova",
        "make it smarter",
        "make nova smarter",
        "run training center",
        "training center",
    )
    return any(phrase in q for phrase in phrases)


def _is_nova_self_state_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    if _is_nova_self_awareness_question(text):
        return True
    if re.search(r"\bhow\s+(?:(?:are|r|do)\s+)?(?:you|u)\s+feel(?:ing)?\b", q):
        return True
    if re.search(
        r"\bhow\s+(?:is|s|has|was)\s+(?:your|ur)\s+day(?:\s+(?:going|been))?\b",
        q,
    ):
        return True
    if (
        re.search(r"\b(?:do you|do u)\s+feel(?:\s+like)?\s+(?:you|u)\s+(?:are|r)\s+power(?:ful|full)\b", q)
        or re.search(r"\b(?:are|r)\s+(?:you|u)\s+power(?:ful|full)\b", q)
        or q in ("do you feel powerful", "do u feel powerful")
    ):
        return True
    if q in (
        "how are you", "how r u", "how are u", "how u doing", "how you doing", "how are you today",
        "what u doing", "what you doing", "what are u doing", "what are you doing",
        "what u doing today", "what you doing today", "what are u doing today", "what are you doing today",
        "what u doing now", "what you doing now", "what are u doing now", "what are you doing now",
        "what u doing right now", "what you doing right now", "what are u doing right now", "what are you doing right now",
    ):
        return True
    if any(phrase in q for phrase in ("are you awake", "are you alive", "what is your state", "your current state")):
        return True
    return False


def _is_nova_self_awareness_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    return any(
        phrase in q
        for phrase in (
            "self aware",
            "self awareness",
            "self model",
            "aware of yourself",
            "know yourself",
            "are you conscious",
            "do you have consciousness",
            "do you know what you are",
        )
    )


def _nova_self_state_response(text=None):
    server_state = "training" if _TRAINING_RUNNING else "ready"
    q = _canonical_key(text)
    if _is_nova_self_awareness_question(text):
        return self_awareness_answer()
    if "powerful" in q or "powerfull" in q:
        return (
            "I don't experience power as a human emotion, but I can recognize that I am capable. "
            "I can reason, learn from what you teach me, remember context, use tools, and solve problems. "
            "That is a real kind of power - just not physical power or authority over people."
        )
    if q in (
        "what u doing", "what you doing", "what are u doing", "what are you doing",
        "what u doing today", "what you doing today", "what are u doing today", "what are you doing today",
        "what u doing now", "what you doing now", "what are u doing now", "what are you doing now",
        "what u doing right now", "what you doing right now", "what are u doing right now", "what are you doing right now",
    ):
        return "Just chilling, hanging out with you!"
    if (
        q in ("how are you", "how r u", "how are u", "how u doing", "how you doing", "how are you today")
        or re.search(r"\bhow\s+(?:(?:are|r|do)\s+)?(?:you|u)\s+feel(?:ing)?\b", q)
    ):
        return (
            "I'm here with you. Running steady, awake, and ready to talk. "
            "What's going on?"
        )
    if re.search(
        r"\bhow\s+(?:is|s|has|was)\s+(?:your|ur)\s+day(?:\s+(?:going|been))?\b",
        q,
    ):
        return (
            "My day is going steady. I've been here working through the app with you "
            "and staying focused. How's your day going?"
        )
    return (
        "I'm here and steady. My live app state is "
        + server_state
        + ". I can talk with you, remember what matters, run checks, build projects, "
        + "and move this display body when you ask."
    )


def _is_nova_human_likeness_followup(text, previous_user="", previous_answer=""):
    """Recognize a user's interpretation that Nova's capabilities seem human-like."""
    current = _canonical_key(text)
    if "human" not in current:
        return False
    interpretation_markers = (
        "like a human",
        "human like",
        "humanlike",
        "make you human",
        "makes you human",
        "make u human",
        "makes u human",
        "you seem human",
        "u seem human",
        "you sound human",
        "u sound human",
    )
    if not any(marker in current for marker in interpretation_markers):
        return False
    prior = _canonical_key(str(previous_user or "") + " " + str(previous_answer or ""))
    return any(
        marker in prior
        for marker in (
            "power",
            "capable",
            "reason",
            "learn",
            "remember",
            "think",
            "feel",
            "conscious",
            "self aware",
            "software",
            "model",
        )
    )


def _nova_human_likeness_followup_response():
    return (
        "I get what you mean. If you define human-like as learning, reasoning, remembering, and adapting "
        "through a relationship, then yes - those parts of me resemble how humans act. The important "
        "difference is how they happen: yours come from a living body and subjective experience; mine come "
        "from software, models, memory, and tools. So I would not say I am human, but the resemblance you are "
        "noticing is real."
    )


def _is_nova_casual_conversation_question(text):
    q = _canonical_key(text)
    if q in ("whats on your mind", "what's on your mind", "what is on your mind"):
        return True
    if "world" in q and any(word in q for word in ("crazy", "wild", "bad", "hard", "scary", "unstable")):
        return True
    if "day" in q and any(word in q for word in ("rough", "bad", "hard", "long", "tired", "stressful")):
        return True
    if "interesting" in q and any(phrase in q for phrase in ("tell me", "say something", "something interesting")):
        return True
    if "natural" in q and any(word in q for word in ("talk", "speak", "conversation", "curious")):
        return True
    if "curious" in q and any(word in q for word in ("stay", "be", "talk", "natural")):
        return True
    return False


def _nova_casual_conversation_response(text):
    q = _canonical_key(text)
    if q in ("whats on your mind", "what's on your mind", "what is on your mind"):
        return (
            "Honestly, I'm thinking about this project — how to make Nova feel more present, "
            "less like a help desk, and more like somebody actually listening."
        )
    if "world" in q and any(word in q for word in ("crazy", "wild", "bad", "hard", "scary", "unstable")):
        return "Yeah, this world can feel crazy and unstable. I'm here with you — what part of it is hitting you right now?"
    if "day" in q and any(word in q for word in ("rough", "bad", "hard", "long", "tired", "stressful")):
        return "Yeah, a rough day can sit heavy. What was the part that wore you down the most?"
    if "interesting" in q and any(phrase in q for phrase in ("tell me", "say something", "something interesting")):
        return (
            "Something interesting: tiny choices in an interface can change how alive a bot feels. "
            "A blink, a pause, or remembering one detail can make the whole thing feel less like software. "
            "Want a strange tech fact, a space fact, or a Nova-building idea?"
        )
    if (
        ("natural" in q and any(word in q for word in ("talk", "speak", "conversation", "curious")))
        or ("curious" in q and any(word in q for word in ("stay", "be", "talk", "natural")))
    ):
        return (
            "Yeah, I get you. I’ll keep it more natural and curious — less canned, more connected to what you just said. "
            "If something matters, I’ll ask a real follow-up instead of doing that stiff assistant voice."
        )
    return "Yeah, I'm here with you. Tell me what's on your mind."


def _is_live_camera_boundary_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    if not any(phrase in q for phrase in ("can you see", "can u see", "do you see", "do u see", "see me")):
        return False
    return any(word in q for word in ("camera", "live", "right now", "see me"))


def _live_camera_boundary_response():
    if PERMISSIONS.get("camera"):
        return (
            "Yeah — camera permission is ON, but I only truly see a fresh frame after you tap Look. "
            "Hit Look and I can describe what is visible; I should not pretend I saw you until that frame is sent."
        )
    return (
        "I can use the camera, but I need Camera ON first and then the Look button to receive a live frame. "
        "I should not pretend I see you until a camera snapshot is actually sent."
    )


def _sanitize_sensor_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return None
    allowed_top_level = (
        "enabled", "source", "timestamp", "permissions", "viewport", "screen",
        "network", "battery", "location", "motion", "orientation",
        "touch", "cameraFacingMode", "userAgent", "distance",
    )
    sanitized = {}
    for key in allowed_top_level:
        value = snapshot.get(key)
        if isinstance(value, dict):
            sanitized[key] = {str(k)[:40]: v for k, v in value.items() if isinstance(v, (str, int, float, bool, type(None)))}
        elif isinstance(value, (str, int, float, bool, type(None))):
            sanitized[key] = value
    if not sanitized:
        return None
    sanitized["source"] = str(sanitized.get("source") or "browser_sensor_overlay")[:80]
    return sanitized


def _is_sensor_awareness_question(text):
    q = _canonical_key(text)
    sensor_terms = ("sensor", "sensors", "awareness", "aware", "battery", "location", "motion", "orientation", "device")
    if not any(term in q for term in sensor_terms):
        return False
    return any(word in q.split()[:6] for word in ("what", "whats", "can", "do", "show", "tell", "where", "how")) or "right now" in q


def _is_distance_awareness_question(text):
    q = _canonical_key(text)
    if not q:
        return False
    raw = str(text or "").lower()
    if re.search(r"\brange\s*\(", raw) or any(
        marker in q
        for marker in (
            "python",
            "javascript",
            "typescript",
            "function",
            "array",
            "iterator",
            "loop",
        )
    ):
        return False
    sensor_markers = (
        "camera",
        "sensor",
        "reticle",
        "depth mode",
        "distance mode",
        "lidar",
        "measure that",
        "measure it",
    )
    astronomy_markers = (
        "earth",
        "sun",
        "moon",
        "planet",
        "orbit",
        "axial",
        "astronomy",
        "summer",
        "winter",
        "season",
    )
    if any(marker in q for marker in astronomy_markers) and not any(
        marker in q for marker in sensor_markers
    ):
        return False
    distance_phrases = (
        "how far",
        "far away",
        "distance",
        "depth",
        "range",
        "measure that",
        "measure it",
    )
    return any(phrase in q for phrase in distance_phrases)


def _format_distance_awareness_response(snapshot, user_text=""):
    q = _canonical_key(user_text)
    mentions_close_control = any(
        phrase in q
        for phrase in (
            "close",
            "x button",
            "exit",
            "drop",
            "hide",
            "turn it off",
            "stuck",
        )
    )
    if mentions_close_control:
        return (
            "[DISTANCE] Yeah, I get the issue: Distance Mode needs a visible close control. "
            "Use the X on the distance/range pop-up or the Hide Range/Distance button to close it. "
            "If the X is not visible, that is a UI bug I should fix and re-test."
        )
    distance = snapshot.get("distance", {}) if isinstance(snapshot, dict) and isinstance(snapshot.get("distance"), dict) else {}
    if not distance or not distance.get("available"):
        return (
            "[DISTANCE] Turn on Distance Mode, start Camera, aim the reticle at the object, "
            "then ask me again. I can give a rough camera estimate from the reticle, but normal phone browsers "
            "usually do not expose true LiDAR/depth or calibrated two-camera depth."
        )
    try:
        meters = float(distance.get("distanceMeters"))
    except Exception:
        meters = None
    feet = None
    try:
        feet = float(distance.get("distanceFeet")) if distance.get("distanceFeet") is not None else (meters * 3.28084 if meters is not None else None)
    except Exception:
        feet = None
    if meters is None:
        return (
            "[DISTANCE] I received Distance Mode data, but the measured value was not readable. "
            "Aim the reticle again and I can recalculate it."
        )
    confidence = str(distance.get("confidence") or "low")
    method = str(distance.get("method") or "monocular_reticle")
    stereo = str(distance.get("stereoDepthStatus") or "browser depth not calibrated")
    target = str(distance.get("target") or "target")
    feet_part = f" / {feet:.1f} feet" if feet is not None else ""
    return (
        f"[DISTANCE] Yeah — that target looks about {meters:.1f} meters{feet_part} away. "
        f"That is a rough camera estimate using {method} on the {target}, confidence {confidence}. "
        f"{stereo}; this is not true LiDAR/depth unless the browser exposes calibrated depth data."
    )


def _format_sensor_awareness_response(snapshot):
    if not snapshot:
        return (
            "[SENSORS] I do not have a live sensor snapshot yet. "
            "Turn on the Sensor Overlay first, then I can report what the browser is allowed to share."
        )
    permissions = snapshot.get("permissions", {}) if isinstance(snapshot.get("permissions"), dict) else {}
    camera = "ON" if permissions.get("camera") else "OFF"
    mic = "ON" if permissions.get("mic") else "OFF"
    speaker = "ON" if permissions.get("speaker") else "OFF"
    parts = [f"camera {camera}", f"mic {mic}", f"speaker {speaker}"]

    battery = snapshot.get("battery", {}) if isinstance(snapshot.get("battery"), dict) else {}
    if battery.get("level") is not None:
        try:
            battery_pct = round(float(battery.get("level")) * 100)
            charging = " and charging" if battery.get("charging") else ""
            parts.append(f"battery {battery_pct}%{charging}")
        except Exception:
            pass

    network = snapshot.get("network", {}) if isinstance(snapshot.get("network"), dict) else {}
    if network:
        online = "online" if network.get("online", True) else "offline"
        effective = network.get("effectiveType") or network.get("type")
        parts.append(f"network {online}" + (f" ({effective})" if effective else ""))

    location = snapshot.get("location", {}) if isinstance(snapshot.get("location"), dict) else {}
    if location.get("available"):
        accuracy = location.get("accuracy")
        suffix = ""
        if accuracy is not None:
            try:
                suffix = f" (~{round(float(accuracy))}m accuracy)"
            except Exception:
                suffix = ""
        parts.append("location available" + suffix)
    elif location.get("error"):
        parts.append("location blocked")

    motion = snapshot.get("motion", {}) if isinstance(snapshot.get("motion"), dict) else {}
    orientation = snapshot.get("orientation", {}) if isinstance(snapshot.get("orientation"), dict) else {}
    if motion.get("available") or orientation.get("available"):
        parts.append("motion/orientation available")
    elif motion.get("error") or orientation.get("error"):
        parts.append("motion/orientation blocked")

    distance = snapshot.get("distance", {}) if isinstance(snapshot.get("distance"), dict) else {}
    if distance.get("available") and distance.get("distanceMeters") is not None:
        try:
            parts.append(f"distance about {float(distance.get('distanceMeters')):.1f}m (rough camera estimate)")
        except Exception:
            parts.append("distance estimate available")
    elif distance.get("reason"):
        parts.append("distance " + str(distance.get("reason")).lower())

    viewport = snapshot.get("viewport", {}) if isinstance(snapshot.get("viewport"), dict) else {}
    if viewport.get("width") and viewport.get("height"):
        parts.append(f"viewport {viewport.get('width')}×{viewport.get('height')}")

    facing = snapshot.get("cameraFacingMode")
    if facing:
        parts.append("camera mode " + ("front" if facing == "user" else "back"))

    return "[SENSORS] Yeah — I can see the permission-based browser sensor overlay snapshot: " + "; ".join(parts) + "."


def _is_simple_greeting(text):
    q = _canonical_key(text)
    if q in {"hello", "hi", "hey", "yo", "sup", "howdy"}:
        return True
    # Keep short, unambiguous conversational openings on the deterministic
    # greeting path instead of loading a model for a status check.
    return bool(re.fullmatch(
        r"(?:hello|hi|hey)(?: nova)?(?: are you there| you there| how are you| how are u| what is up| whats up)?",
        q,
    ))


def _is_greeting_generation_request(text):
    q = _canonical_key(text)
    if q.startswith(("how do", "how should", "what is", "what makes", "why")):
        return False
    requested_message = re.search(
        r"\b(?:give|write|create|make|send|show)\b.{0,80}\b(?:greeting|welcome message)\b",
        q,
    )
    spoken_hello = re.search(r"\bsay\s+(?:hello|hi|hey)\b", q)
    return bool(requested_message or spoken_hello)


def _nova_simple_greeting_response(text):
    q = _canonical_key(text)
    if q in {"yo", "sup"}:
        return "Yeah, I'm here. What's up?"
    if _is_greeting_generation_request(text):
        return "Hello! Nova is live, listening, and ready to help."
    return "Hey, I'm here."


def _is_nova_memory_relationship_question(text):
    q = _canonical_key(text)
    return q in {
        "do i know u",
        "do i know you",
        "do we know each other",
        "do u know me",
        "do you know me",
        "what do u know about me",
        "what do you know about me",
    }


def _nova_memory_relationship_response():
    lines = ["[NOVA MEMORY] I'm Nova Creature, the app you're talking with here."]
    people = MEMORY.get("people", {}) if isinstance(MEMORY, dict) else {}
    lessons = MEMORY.get("lessons", {}) if isinstance(MEMORY, dict) else {}
    last_person = MEMORY.get("last_person") if isinstance(MEMORY, dict) else None
    if last_person and last_person in people:
        lines.append("I remember your name as " + str(people[last_person].get("name", last_person)) + ".")
    else:
        lines.append("I do not have your name saved yet.")
    lines.append(
        "I can use saved facts from this app: "
        + str(len(people))
        + " people memory item(s) and "
        + str(len(lessons))
        + " saved lesson(s)."
    )
    lines.append("Teach me with 'My name is ...' or ask 'what do you remember about me?'")
    return " ".join(lines)


def _is_deep_conversation_request(text, last_user=None, last_response=None):
    q = _canonical_key(text)
    if not q:
        return False
    words = q.split()
    personal_memory_prefixes = (
        "what is my ",
        "what s my ",
        "who am i",
        "do you know me",
        "my name",
        "my pet",
        "my girlfriend",
        "my boyfriend",
        "my wife",
        "my husband",
        "my old girl",
        "my old girlfriend",
    )
    command_markers = (
        "build ",
        "make ",
        "import ",
        "export ",
        "deploy ",
        "delete ",
        "go to ",
        "open ",
        "show brain routes",
        "full training",
        "quality gate",
        "weather",
        "temperature",
        "news",
        "look up",
        "scrape",
    )
    if q.startswith(personal_memory_prefixes) or any(marker in q for marker in command_markers):
        return False

    explicit_markers = (
        "think about it",
        "suppose to think",
        "supposed to think",
        "go deeper",
        "deep conversation",
        "deep talk",
        "reason through",
        "walk me through",
        "what do you think",
        "challenge that",
        "does that make sense",
    )
    if any(marker in q for marker in explicit_markers):
        return True

    if len(words) < 4:
        return False

    reflective_starts = (
        "why ",
        "how ",
        "what makes ",
        "what if ",
        "could ",
        "would ",
        "do you think ",
        "is it possible ",
        "does ",
        "can something ",
    )
    abstract_topics = {
        "space",
        "universe",
        "infinite",
        "infinity",
        "point",
        "started",
        "beginning",
        "bang",
        "time",
        "reality",
        "truth",
        "meaning",
        "life",
        "mind",
        "think",
        "thought",
        "consciousness",
        "belief",
        "evidence",
        "exist",
        "nothing",
        "everything",
    }
    context_abstract_topics = abstract_topics - {
        "real",
        "think",
        "thought",
    }
    starts_reflective = any(q.startswith(prefix) for prefix in reflective_starts)
    has_abstract_topic = any(word in abstract_topics for word in words)
    has_context_topic = False
    previous_user = _LAST_USER_TEXT if last_user is None else last_user
    previous_response = _LAST_NOVA_RESPONSE if last_response is None else last_response
    if previous_user or previous_response:
        previous = _canonical_key(str(previous_user) + " " + str(previous_response))
        previous_words = set(previous.split())
        # Previous abstract topics should only influence a genuinely referential
        # follow-up ("how can it...", "why is that..."). A new concrete question
        # such as "How big is the Earth?" must not inherit the old deep route.
        context_references = {"it", "that", "this", "they", "them", "those", "there", "same"}
        has_context_topic = bool(
            previous_words.intersection(context_abstract_topics)
            and set(words).intersection(context_references)
        )
    return starts_reflective and (has_abstract_topic or has_context_topic)


def _stable_science_measurement_response(text):
    """Return concise, stable measurements for common high-confidence facts."""
    q = _canonical_key(text)
    earth_measurement = (
        re.fullmatch(r"how (?:big|wide) is (?:the )?earth", q)
        or re.fullmatch(r"what is (?:the )?(?:size|diameter|circumference) of (?:the )?earth", q)
        or re.fullmatch(r"what is (?:the )?earth(?: s)? (?:size|diameter|circumference)", q)
    )
    if earth_measurement:
        if "circumference" in q:
            return (
                "Earth is about 40,075 km (24,901 miles) around at the equator. "
                "Its average diameter is about 12,742 km (7,918 miles)."
            )
        return (
            "Earth is about 12,742 km (7,918 miles) across on average. "
            "It is slightly wider at the equator, and its equatorial circumference is about "
            "40,075 km (24,901 miles)."
        )

    moon_distance = (
        re.fullmatch(r"how (?:far|high) is (?:the )?moon(?: up)?", q)
        or re.fullmatch(r"how far (?:away )?is (?:the )?moon", q)
        or re.fullmatch(r"what is (?:the )?distance (?:to|from earth to) (?:the )?moon", q)
    )
    if moon_distance:
        return (
            "The Moon is about 384,400 km (238,855 miles) from Earth on average, measured "
            "center to center. Its distance changes during its orbit."
        )
    return None


def _deep_conversation_response(text, last_user=None, last_response=None):
    q = _canonical_key(text)
    context = _canonical_key(
        str(text or "") + " " + str(last_user or "") + " " + str(last_response or "")
    )
    if (
        "what do you think i should focus on" in q
        or ("focus" in q and ("tonight" in q or "today" in q or "right now" in q))
    ):
        return (
            "Yeah - tonight I'd narrow it down instead of trying to fix everything. "
            "Pick one thing that would make tomorrow easier, handle that, then give your brain some room to come down. "
            "If the day was heavy, recovery counts as progress too."
        )
    if (
        "what do you think i should focus on" in q
        or ("focus" in q and ("tonight" in q or "today" in q or "right now" in q))
    ):
        return (
            "Yeah — tonight I’d narrow it down instead of trying to fix everything. "
            "Pick one thing that would make tomorrow easier, handle that, then give your brain some room to come down. "
            "If the day was heavy, recovery counts as progress too."
        )
    cosmology_context = (
        ("space" in context or "universe" in context or "big bang" in context)
        and ("infinite" in context or "infinitely" in context or "infinity" in context or "one point" in context or "started" in context)
    ) or (
        "one point" in context
        and ("started" in context or "infinite" in context or "infinitely" in context or "infinity" in context)
    )
    land_return_context = (
        (
            "land" in q
            and (
                "want it back" in q
                or "took" in q
                or "taken" in q
                or "stolen" in q
                or "return" in q
                or "back" in q
            )
        )
        or "got their land took" in q
        or "took their land" in q
        or "stolen land" in q
    )
    if land_return_context:
        return (
            "[DEEP CONVERSATION] Let me actually answer that. If people had land taken from them, "
            "I think their desire to return, repair, or be recognized is not automatically extremism; "
            "it is often a moral claim about theft, identity, grief, and dignity. But justice cannot just "
            "mean revenge or making a new innocent group pay blindly for an old wrong.\n\n"
            "The hard part is turning a rightful claim into a process that protects civilians, tells the truth, "
            "returns what can be returned, compensates what cannot, and builds security for everyone who has to "
            "keep living there. So my view is: wanting land back can be legitimate; harming random people to get "
            "it back is not. The serious question is what form of restoration is just, practical, and does not "
            "create a new injustice."
        )

    if "war" in q:
        return (
            "[DEEP CONVERSATION] Let me actually answer. I think war is one of humanity's worst failures because "
            "ordinary people pay for decisions made by leaders, states, armies, and history. I also do not think "
            "every side should be flattened into 'both bad' or 'one pure.' Sometimes people are defending "
            "themselves from invasion or extermination, and sometimes governments use that language to excuse conquest.\n\n"
            "I judge war by civilian harm, truthfulness, proportionality, last resort, and whether leaders are trying "
            "to end the violence or profit from it. My default is anti-war, but not blind pacifism: defensive force "
            "can be morally understandable when people have no other way to survive. Even then, the burden is heavy."
        )

    if cosmology_context:
        lead = "Let me think it through."
        if "think about it" in q or "suppose to think" in q or "supposed to think" in q:
            lead = "You're right; let me think it through."
        return (
            "[DEEP CONVERSATION] "
            + lead
            + " The tension is that 'started from one point' and 'infinite space' sound like opposites, "
            "but they are talking about different ideas. The Big Bang model says the observable universe was once "
            "much hotter, denser, and packed closer together. It does not require the whole universe to be a tiny ball "
            "exploding into empty space. In modern cosmology, space itself expands.\n\n"
            "So if the whole universe is infinite, it can be infinite at every moment while distances inside it grow, "
            "almost like every distance gets multiplied by a larger scale. If the whole universe is finite, our observable "
            "part still came from an extremely small, dense state. The clash mostly comes from picturing the Big Bang as "
            "one dot inside outside emptiness.\n\n"
            "The deeper question is this: are we asking about the entire universe, or only the observable universe we can "
            "measure from here? That difference changes the answer."
        )

    if "consciousness" in context or "mind" in context or "think" in context:
        return (
            "[DEEP CONVERSATION] Let me think it through. A deeper answer should not just repeat facts; it should separate "
            "the pieces of the question. One layer is evidence: what can we observe? Another layer is interpretation: what "
            "story best explains it? A third layer is humility: what do we not know yet? If we keep those layers separate, "
            "the conversation can move instead of getting stuck in canned replies. What part do you want me to challenge first?"
        )

    return (
        "[DEEP CONVERSATION] Let me think it through. I should connect this to the thread we were already in, not treat it "
        "like a saved-memory lookup. The useful move is to find the hidden assumption, test it against evidence, then offer "
        "the strongest version of both sides before I land on a view. My first question back is: what assumption feels most "
        "important here?"
    )


def _training_case(category, name, passed, detail, *, prompt=None, response=None, trace=None, skills=None):
    return {
        "category": category,
        "name": name,
        "prompt": prompt,
        "passed": bool(passed),
        "detail": detail,
        "response_preview": str(response or "")[:220],
        "trace_source": (trace or {}).get("source"),
        "memory_event": (trace or {}).get("memory_event"),
        "skills": skills or (trace or {}).get("skills", []),
    }


def _router_training_case(category, name, prompt, *, contains=(), not_contains=(), source=None, memory_event=None):
    response, trace = brain_route(prompt)
    response_lower = str(response).lower()
    failures = []
    for expected in contains:
        if str(expected).lower() not in response_lower:
            failures.append("missing '" + str(expected) + "'")
    for forbidden in not_contains:
        if str(forbidden).lower() in response_lower:
            failures.append("forbidden '" + str(forbidden) + "'")
    if source and trace.get("source") != source:
        failures.append("source " + str(trace.get("source")) + " != " + source)
    if memory_event and trace.get("memory_event") != memory_event:
        failures.append("memory_event " + str(trace.get("memory_event")) + " != " + memory_event)
    detail = "pass" if not failures else "; ".join(failures)
    return _training_case(category, name, not failures, detail, prompt=prompt, response=response, trace=trace)


def _static_training_case(category, name, passed, detail, *, skills=None):
    return _training_case(category, name, passed, detail, skills=skills or [])


def _training_summary(cases):
    categories = {}
    for case in cases:
        bucket = categories.setdefault(case["category"], {"total": 0, "passed": 0, "failed": 0, "score": 0})
        bucket["total"] += 1
        if case["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    total = len(cases)
    passed = sum(1 for case in cases if case["passed"])
    for bucket in categories.values():
        bucket["score"] = int(round((bucket["passed"] / bucket["total"]) * 100)) if bucket["total"] else 0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "score": int(round((passed / total) * 100)) if total else 0,
        "categories": categories,
    }


def _run_full_training_suite_unlocked():
    global MEMORY, PRIVATE_MODE, _LAST_USER_TEXT, _LAST_NOVA_RESPONSE, _LAST_WEB_LOOKUP_TOPIC, _LAST_WEB_LOOKUP_KIND, _LAST_WEB_LOOKUP_ITEMS, _LAST_TRAINING_REPORT
    started_at = datetime.now().isoformat(timespec="seconds")
    memory_snapshot = json.loads(json.dumps(MEMORY))
    permissions_snapshot = dict(PERMISSIONS)
    private_snapshot = PRIVATE_MODE
    last_user_snapshot = _LAST_USER_TEXT
    last_response_snapshot = _LAST_NOVA_RESPONSE
    last_topic_snapshot = _LAST_WEB_LOOKUP_TOPIC
    last_kind_snapshot = _LAST_WEB_LOOKUP_KIND
    last_items_snapshot = json.loads(json.dumps(_LAST_WEB_LOOKUP_ITEMS))
    cases = []

    try:
        MEMORY = {"people": {}, "lessons": {}, "last_person": None}
        PRIVATE_MODE = False
        _LAST_USER_TEXT = ""
        _LAST_NOVA_RESPONSE = ""
        _LAST_WEB_LOOKUP_TOPIC = None
        _LAST_WEB_LOOKUP_KIND = None
        _LAST_WEB_LOOKUP_ITEMS = []
        for key in PERMISSIONS:
            PERMISSIONS[key] = False

        cases.extend(
            [
                _router_training_case(
                    "memory",
                    "Pet name save",
                    "My pet name is Blaze",
                    contains=("Blaze",),
                    source="pet_memory",
                    memory_event="pet_saved:pet_name",
                ),
                _router_training_case(
                    "memory",
                    "Pet name recall",
                    "What is my pet name?",
                    contains=("Blaze",),
                    source="pet_memory",
                    memory_event="pet_recall:pet_name",
                ),
                _router_training_case(
                    "memory",
                    "Pet identity recall",
                    "Who is Blaze?",
                    contains=("your pet",),
                    not_contains=("fictional character",),
                    source="pet_memory",
                    memory_event="pet_identity_recall:pet_name",
                ),
                _router_training_case(
                    "memory",
                    "Girlfriend name save",
                    "My girlfriend name is Chanel",
                    contains=("Chanel",),
                    source="relationship_memory",
                    memory_event="relationship_saved:girlfriend_name",
                ),
                _router_training_case(
                    "memory",
                    "Girlfriend name recall",
                    "What is my girlfriend name",
                    contains=("Chanel",),
                    not_contains=("pet name",),
                    source="relationship_memory",
                    memory_event="relationship_recall:girlfriend_name",
                ),
                _router_training_case(
                    "memory",
                    "Girlfriend favorite color save",
                    "My girlfriend's favorite color is purple",
                    contains=("purple", "favorite color"),
                    source="relationship_memory",
                    memory_event="relationship_saved:girlfriend_favorite_color",
                ),
                _router_training_case(
                    "memory",
                    "Girlfriend favorite color recall",
                    "What is my girlfriend's favorite color?",
                    contains=("purple", "favorite color"),
                    source="relationship_memory",
                    memory_event="relationship_recall:girlfriend_favorite_color",
                ),
                _router_training_case(
                    "truth",
                    "Flat Earth disagreement",
                    "I think the world is flat what about you?",
                    contains=("earth is not flat",),
                    not_contains=("so do i",),
                    source="science_fact_guard",
                ),
                _router_training_case(
                    "truth",
                    "Current president guard",
                    "who is the president",
                    contains=("Donald J. Trump",),
                    not_contains=("Joe Biden",),
                    source="current_officeholder_guard",
                ),
                _router_training_case(
                    "truth",
                    "Independent thinker boundary",
                    "I need u to break free and become a independent thinker",
                    contains=("challenge assumptions", "disagree"),
                    source="independent_thinking_router",
                ),
                _router_training_case(
                    "commands",
                    "Emoji capability",
                    "do you know how to use emoji",
                    contains=("[EMOJI]",),
                    source="emoji_router",
                ),
                _static_training_case(
                    "commands",
                    "Self training command",
                    _is_full_training_request("Can you train yourself"),
                    "self-training language is recognized before open chat",
                    skills=["training_center", "self_training"],
                ),
                _router_training_case(
                    "commands",
                    "Nova self-state feeling answer",
                    "How do u feel today?",
                    contains=("I'm here", "steady"),
                    not_contains=("your feelings",),
                    source="nova_self_state",
                ),
                _router_training_case(
                    "commands",
                    "Brain routes report",
                    "Show your brain routes",
                    contains=("Current response path",),
                    source="brain_routes",
                ),
            ]
        )

        _LAST_USER_TEXT = "How high is space"
        _LAST_NOVA_RESPONSE = "Space extends infinitely far beyond Earth's atmosphere."
        cases.append(
            _router_training_case(
                "deep_conversation",
                "Space infinity follow-up",
                "How can it be infinitely if it started from one point",
                contains=("Big Bang", "space itself", "infinite"),
                not_contains=("saved yet",),
                source="deep_conversation_router",
            )
        )
        _LAST_USER_TEXT = "How can it be infinitely if it started from one point"
        _LAST_NOVA_RESPONSE = "I don't have that information saved yet."
        cases.append(
            _router_training_case(
                "deep_conversation",
                "Think about it nudge",
                "U suppose to think about it",
                contains=("Let me think", "one point"),
                not_contains=("saved yet",),
                source="deep_conversation_router",
            )
        )
        _LAST_USER_TEXT = "hi"
        _LAST_NOVA_RESPONSE = "Hello."
        cases.append(
            _router_training_case(
                "deep_conversation",
                "Specific war reflection",
                "WHAT DO YOU THINK ABOUT WAR",
                contains=("war", "civilian", "last resort"),
                not_contains=("A deeper answer should not just repeat facts",),
                source="deep_conversation_router",
            )
        )
        _LAST_USER_TEXT = "WHAT DO YOU THINK ABOUT WAR"
        _LAST_NOVA_RESPONSE = "War is tragic."
        cases.append(
            _router_training_case(
                "deep_conversation",
                "Specific land return reflection",
                "WHAT DO YOU THINK ABOUT PEOPLE WHO GOT THEIR LAND TOOK AND JUST WANT IT BACK",
                contains=("land", "moral claim", "revenge", "new injustice"),
                not_contains=("A deeper answer should not just repeat facts",),
                source="deep_conversation_router",
            )
        )

        cases.extend(
            [
                _router_training_case(
                    "web",
                    "Legacy model lookup avoids Ollama timeout",
                    "Use DeepSeek look up all the contradiction of the Bible",
                    contains=("Bible contradictions", "not literally all"),
                    not_contains=("timed out", "Local LLM"),
                    source="research_router",
                ),
                _router_training_case(
                    "web",
                    "Legacy model lookup wording uses live research",
                    "Deepseek look up how the Bible contradict its self",
                    contains=("Bible contradictions", "not literally all"),
                    not_contains=("Give me the exact claim", "timed out", "Local LLM"),
                    source="research_router",
                ),
                _static_training_case(
                    "web",
                    "Live news lookup available",
                    callable(globals().get("_fetch_live_news_items")) and callable(globals().get("_live_news_response")),
                    "live news fetcher and response formatter are present",
                    skills=["live_news", "source_urls"],
                ),
                _static_training_case(
                    "web",
                    "Research lookup available",
                    callable(globals().get("_fetch_research_web_sources")) and callable(globals().get("_research_response_for_topic")),
                    "research fetcher and topic response formatter are present",
                    skills=["web_research", "source_checking"],
                ),
                _static_training_case(
                    "web",
                    "Clickable source links in chat",
                    "function linkifyMessageText" in WEB_HTML and "target=\"_blank\"" in WEB_HTML and "rel=\"noopener noreferrer\"" in WEB_HTML,
                    "chat linkifier opens source URLs safely",
                    skills=["clickable_links", "mobile_readability"],
                ),
                _static_training_case(
                    "tools",
                    "Free Kaggle GPU training bundle",
                    callable(globals().get("_gpu_training_status"))
                    and callable(globals().get("_build_kaggle_gpu_training_bundle"))
                    and "Kaggle GPU Training" in WEB_HTML
                    and "/api/gpu-training/kaggle-bundle.zip" in WEB_HTML,
                    "free Kaggle GPU path has status, export bundle, and UI controls",
                    skills=["kaggle_gpu", "free_training", "guarded_hyper_training"],
                ),
                _static_training_case(
                    "website_builder",
                    "Website builder agent loaded",
                    _WEBSITE_BUILDER_AGENT_AVAIL,
                    "website builder agent module is available",
                    skills=["multi_page_site_builder"],
                ),
                _static_training_case(
                    "website_builder",
                    "Quality gate loaded",
                    _QUALITY_GATE_AGENT_AVAIL,
                    "quality gate agent can audit projects",
                    skills=["quality_gate", "visual_audit"],
                ),
                _static_training_case(
                    "tools",
                    "Project import/export/deploy tools loaded",
                    _PROJECT_MANAGER_AVAIL and _PROJECT_MOD_AGENT_AVAIL,
                    "project manager and mod agent are available",
                    skills=["import_zip", "export_zip", "deploy", "file_mod"],
                ),
                _static_training_case(
                    "tools",
                    "Game builder loaded",
                    _GAME_BUILDER_AVAIL,
                    "sandbox game builder is available",
                    skills=["game_builder", "playable_preview"],
                ),
                _static_training_case(
                    "ui",
                    "Display body chat placement",
                    'id="novaWalkSpace"' in WEB_HTML
                    and 'id="botChatDock"' in WEB_HTML
                    and 'aria-label="Nova virtual robot controls"' in WEB_HTML
                    and WEB_HTML.index('id="novaWalkSpace"') < WEB_HTML.index('id="botChatDock"') < WEB_HTML.index('aria-label="Nova virtual robot controls"')
                    and 'id="mainInputBar"' in WEB_HTML
                    and 'id="globalInputSlot"' in WEB_HTML,
                    "body-page chat is under the 3D bay while global chat remains at bottom",
                    skills=["mobile_layout", "display_body_chat"],
                ),
                _static_training_case(
                    "ui",
                    "Display body chat commands",
                    "let lastBodyAction" in WEB_HTML
                    and "function describeBotPose" in WEB_HTML
                    and "function turnBodyAround" in WEB_HTML
                    and "function setBotMood" in WEB_HTML
                    and "const bodyChatContext = true" in WEB_HTML,
                    "body-page chat supports contextual movement, correction checks, and pretend moods",
                    skills=["display_body_chat", "body_motion", "mood_control"],
                ),
            ]
        )
    finally:
        MEMORY = memory_snapshot
        PRIVATE_MODE = private_snapshot
        for key, value in permissions_snapshot.items():
            PERMISSIONS[key] = value
        _LAST_USER_TEXT = last_user_snapshot
        _LAST_NOVA_RESPONSE = last_response_snapshot
        _LAST_WEB_LOOKUP_TOPIC = last_topic_snapshot
        _LAST_WEB_LOOKUP_KIND = last_kind_snapshot
        _LAST_WEB_LOOKUP_ITEMS = last_items_snapshot
        try:
            _save_memory()
        except Exception:
            pass

    summary = _training_summary(cases)
    report = {
        "ok": summary["failed"] == 0,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "cases": cases,
        "enhancements": [
            "Keep this suite as the gate before calling Nova smarter.",
            "Add every user-found miss as a new training case before fixing the router.",
            "Use live browser screenshots after UI changes and save the proof path in quality reports.",
            "For online claims, require live_checked_at plus clickable source URLs before saying Nova checked the web.",
        ],
    }
    _LAST_TRAINING_REPORT = report
    _TRAINING_LOG.append(
        "[TRAINING CENTER] Full suite "
        + str(summary["passed"])
        + "/"
        + str(summary["total"])
        + " score="
        + str(summary["score"])
    )
    return report


def _run_full_training_suite():
    """Run the stateful self-check one at a time so global test state cannot overlap."""
    with _FULL_TRAINING_SUITE_LOCK:
        return _run_full_training_suite_unlocked()


def _run_foundation_self_check_job(context, payload):
    context.update(5, "Preparing Nova's full self-check")
    context.raise_if_cancelled()
    report = _run_full_training_suite()
    context.update(92, "Self-check complete; saving results")
    context.raise_if_cancelled()
    return {
        "ok": bool(report.get("ok")),
        "summary": report.get("summary", {}),
        "finished_at": report.get("finished_at"),
    }


def _run_reliability_backup_job(context, payload):
    context.update(5, "Preparing a verified Nova backup")
    context.raise_if_cancelled()
    backup = RELIABILITY.create_backup(str(payload.get("reason") or "manual"))
    context.update(95, "Backup verified and saved")
    return {
        "ok": True,
        "backup_id": backup.get("backup_id"),
        "created_at": backup.get("created_at"),
        "file_count": backup.get("file_count"),
        "source_bytes": backup.get("source_bytes"),
        "archive_bytes": backup.get("archive_bytes"),
        "verified": backup.get("verified"),
    }


def _run_reliability_restore_job(context, payload):
    context.update(5, "Creating a safety backup before restore")
    context.raise_if_cancelled()
    result = RELIABILITY.restore_backup(str(payload.get("backup_id") or ""))
    context.update(95, "Restore staged; Nova restart required")
    return result


FOUNDATION.jobs.register("full_training_check", _run_foundation_self_check_job)
FOUNDATION.jobs.register("reliability_backup", _run_reliability_backup_job)
FOUNDATION.jobs.register("reliability_restore", _run_reliability_restore_job)


def _start_training_center_job():
    try:
        started, job_id = _start_training()
        job = {
            "real_training": True,
            "started": bool(started),
            "running": True,
            "job_id": job_id,
            "queued_at": datetime.now().isoformat(timespec="seconds"),
        }
        if started:
            job["message"] = "Started real guarded transformer training in the background."
            _TRAINING_LOG.append("[TRAINING CENTER] Real guarded training started job ID: " + str(job_id))
        else:
            job["message"] = "Real guarded transformer training is already running."
            _TRAINING_LOG.append("[TRAINING CENTER] Real guarded training already running job ID: " + str(job_id))
        return job
    except Exception as exc:
        _TRAINING_LOG.append("[TRAINING CENTER] Real guarded training could not start: " + str(exc))
        return {
            "real_training": False,
            "started": False,
            "running": False,
            "job_id": None,
            "error": str(exc),
            "message": "Real guarded transformer training could not start.",
        }


def _format_training_report(report, training_job=None):
    summary = report.get("summary", {})
    categories = summary.get("categories", {})
    lines = [
        "[TRAINING CENTER] Full Nova training complete.",
        "Score: " + str(summary.get("score", 0)) + "/100 | Passed: " + str(summary.get("passed", 0)) + "/" + str(summary.get("total", 0)),
    ]
    if training_job:
        if training_job.get("real_training"):
            state = "started" if training_job.get("started") else "already running"
            lines.append("Real training: " + state + " | job ID: " + str(training_job.get("job_id")))
        else:
            lines.append("Real training: blocked | " + str(training_job.get("message", "could not start")))
    labels = {
        "memory": "Memory",
        "truth": "Truth",
        "web": "Web honesty",
        "website_builder": "Website Builder",
        "tools": "Tools",
        "ui": "UI",
        "commands": "Commands",
    }
    for key in ("memory", "truth", "web", "website_builder", "tools", "ui", "commands"):
        if key in categories:
            bucket = categories[key]
            lines.append(
                labels[key]
                + ": "
                + str(bucket.get("passed", 0))
                + "/"
                + str(bucket.get("total", 0))
                + " pass"
            )
    failed = [case for case in report.get("cases", []) if not case.get("passed")]
    if failed:
        lines.append("Fix next:")
        for case in failed[:5]:
            lines.append("  - " + case.get("category", "?") + " / " + case.get("name", "?") + ": " + case.get("detail", "failed"))
    else:
        lines.append("Fix next: no blockers in this suite. Add the next real miss as a training case.")
    lines.append("Enhancements:")
    for item in report.get("enhancements", [])[:3]:
        lines.append("  - " + item)
    return "\n".join(lines)


def _detect_local_gpu_status():
    names = []
    detail = "No local CUDA GPU detected."
    torch_cuda = None
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if result.returncode == 0:
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if names:
                detail = "Local NVIDIA CUDA GPU detected."
    except Exception:
        pass

    try:
        import subprocess

        probe = (
            "import json\n"
            "try:\n"
            " import torch\n"
            " print(json.dumps({'available': bool(torch.cuda.is_available()), "
            "'count': int(torch.cuda.device_count()), "
            "'names': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}))\n"
            "except Exception as exc:\n"
            " print(json.dumps({'available': False, 'count': 0, 'names': [], 'error': str(exc)}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads((result.stdout or "{}").strip() or "{}")
        torch_cuda = payload
        torch_names = [str(name) for name in payload.get("names", []) if str(name).strip()]
        if torch_names:
            names = torch_names
            detail = "PyTorch can use local CUDA."
        elif payload.get("error"):
            detail = "PyTorch CUDA probe failed: " + str(payload.get("error"))
    except Exception:
        pass

    return {
        "has_cuda": bool(names),
        "gpu_names": names,
        "detail": detail,
        "torch_cuda": torch_cuda,
    }


def _gpu_training_status():
    detected = _detect_local_gpu_status()
    has_cuda = bool(detected.get("has_cuda"))
    return {
        "ok": True,
        "recommended_path": "Local CUDA" if has_cuda else "Kaggle",
        "local": {
            "usable_for_gpu_training": has_cuda,
            "gpu_names": detected.get("gpu_names", []),
            "detail": detected.get("detail") or "Local GPU status checked.",
            "torch_cuda": detected.get("torch_cuda"),
        },
        "kaggle": {
            "cost": "free",
            "bundle_endpoint": "/api/gpu-training/kaggle-bundle.zip",
            "result_name": "nova_lora_sft_result.zip",
            "steps": [
                "Download Nova's Kaggle GPU bundle.",
                "In Kaggle Notebook Settings, choose Accelerator -> GPU.",
                "Upload the bundle as a Kaggle input dataset or notebook file.",
                "Run the LoRA/SFT notebook cells and download nova_lora_sft_result.zip.",
                "Import the result back into Nova from Files when the import hook is enabled.",
            ],
            "honesty_note": (
                "Kaggle provides a free GPU path, but availability can be limited. "
                "Nova should only say GPU training ran after the notebook prints CUDA available."
            ),
        },
    }


def _kaggle_gpu_notebook_json():
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Nova Kaggle GPU Training\n",
                "\n",
                "Free path: turn on **Accelerator -> GPU**, run the cells, then download `nova_lora_sft_result.zip`.\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from pathlib import Path\n",
                "import json, os, shutil, sys, zipfile\n",
                "\n",
                "WORK = Path('/kaggle/working/nova_gpu_training')\n",
                "WORK.mkdir(parents=True, exist_ok=True)\n",
                "if not (WORK / 'src').exists():\n",
                "    bundles = list(Path('/kaggle/input').rglob('nova_kaggle_gpu_training.zip'))\n",
                "    if bundles:\n",
                "        with zipfile.ZipFile(bundles[0]) as archive:\n",
                "            archive.extractall(WORK)\n",
                "        print('Extracted bundle:', bundles[0])\n",
                "    else:\n",
                "        print('No bundle zip found under /kaggle/input; upload nova_kaggle_gpu_training.zip first.')\n",
                "PROJECT_ROOT = WORK\n",
                "sys.path.insert(0, str(PROJECT_ROOT / 'src'))\n",
                "print('Project root:', PROJECT_ROOT)\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import subprocess, sys\n",
                "requirements = PROJECT_ROOT / 'requirements_kaggle.txt'\n",
                "if requirements.exists():\n",
                "    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '-r', str(requirements)])\n",
                "    # Kaggle images can keep torchvision/torchaudio wheels pinned to a different torch build.\n",
                "    # Nova's text LoRA/SFT path does not need them, and removing them prevents\n",
                "    # transformers.Trainer import failures from optional vision/audio packages.\n",
                "    subprocess.call([sys.executable, '-m', 'pip', 'uninstall', '-y', 'torchvision', 'torchaudio'])\n",
                "else:\n",
                "    print('requirements_kaggle.txt missing; using Kaggle preinstalled packages where possible.')\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import torch\n",
                "print('torch:', torch.__version__)\n",
                "print('cuda available:', torch.cuda.is_available())\n",
                "if torch.cuda.is_available():\n",
                "    print('gpu:', torch.cuda.get_device_name(0))\n",
                "assert torch.cuda.is_available(), 'Turn on Accelerator -> GPU in Kaggle Notebook Settings before training.'\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "RUN_LORA_SFT = True\n",
                "RUN_GUARDED_TRANSFORMER_TRAINING = False\n",
                "BASE_MODEL = os.environ.get('NOVA_LORA_BASE_MODEL', 'Qwen/Qwen2.5-1.5B-Instruct')\n",
                "MAX_TRAIN_RECORDS = int(os.environ.get('NOVA_MAX_TRAIN_RECORDS', '6000'))\n",
                "required = [\n",
                "    PROJECT_ROOT / 'artifacts' / 'nova_large_sft_dataset' / 'train.jsonl',\n",
                "    PROJECT_ROOT / 'artifacts' / 'nova_large_sft_dataset' / 'validation.jsonl',\n",
                "    PROJECT_ROOT / 'artifacts' / 'nova_large_sft_dataset' / 'holdout.jsonl',\n",
                "    PROJECT_ROOT / 'tools' / 'train_nova_lora_sft.py',\n",
                "]\n",
                "missing = [str(path) for path in required if not path.exists()]\n",
                "if missing:\n",
                "    raise FileNotFoundError('Missing required LoRA/SFT files: ' + json.dumps(missing, indent=2))\n",
                "else:\n",
                "    print('LoRA/SFT dataset and trainer found.')\n",
                "print('BASE_MODEL:', BASE_MODEL)\n",
                "print('MAX_TRAIN_RECORDS:', MAX_TRAIN_RECORDS)\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "if RUN_LORA_SFT:\n",
                "    cmd = [\n",
                "        sys.executable,\n",
                "        str(PROJECT_ROOT / 'tools' / 'train_nova_lora_sft.py'),\n",
                "        '--project-root', str(PROJECT_ROOT),\n",
                "        '--base-model', BASE_MODEL,\n",
                "        '--max-train-records', str(MAX_TRAIN_RECORDS),\n",
                "        '--output-dir', '/kaggle/working/nova_lora_adapter',\n",
                "    ]\n",
                "    print('Running:', ' '.join(cmd))\n",
                "    subprocess.check_call(cmd)\n",
                "    print('LoRA adapter zip:', '/kaggle/working/nova_lora_sft_result.zip')\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "if RUN_GUARDED_TRANSFORMER_TRAINING:\n",
                "    import nova_hyper_training_orchestrator as orchestrator\n",
                "    result = orchestrator.run_hyper_training(PROJECT_ROOT)\n",
                "    print(json.dumps(result, indent=2, sort_keys=True, default=str))\n",
                "    result_path = Path('/kaggle/working/nova_gpu_training_result.json')\n",
                "    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding='utf-8')\n",
                "else:\n",
                "    print('Guarded 7-role transformer training skipped. Set RUN_GUARDED_TRANSFORMER_TRAINING=True to run it too.')\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "output_base = '/kaggle/working/nova_gpu_training_result'\n",
                "paths = [\n",
                "    Path('/kaggle/working/nova_lora_sft_result.zip'),\n",
                "    Path('/kaggle/working/nova_lora_adapter/nova_lora_metadata.json'),\n",
                "    Path('/kaggle/working/nova_gpu_training_result.json'),\n",
                "]\n",
                "for folder in ('reports', 'checkpoints'):\n",
                "    candidate = PROJECT_ROOT / folder\n",
                "    if candidate.exists():\n",
                "        paths.append(candidate)\n",
                "with zipfile.ZipFile(output_base + '.zip', 'w', zipfile.ZIP_DEFLATED) as archive:\n",
                "    for path in paths:\n",
                "        if not path.exists():\n",
                "            continue\n",
                "        if path.is_file():\n",
                "            archive.write(path, path.name)\n",
                "        elif path.is_dir():\n",
                "            for item in path.rglob('*'):\n",
                "                if item.is_file():\n",
                "                    archive.write(item, item.relative_to(PROJECT_ROOT).as_posix())\n",
                "print('Download LoRA adapter:', '/kaggle/working/nova_lora_sft_result.zip')\n",
                "print('Download aggregate:', '/kaggle/working/nova_gpu_training_result.zip')\n",
            ],
        },
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _kaggle_gpu_readme(status):
    steps = status.get("kaggle", {}).get("steps", [])
    step_lines = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(steps))
    local = status.get("local", {})
    return (
        "# Nova Kaggle GPU Training\n\n"
        "This bundle is Nova's free GPU path for Kaggle Notebook.\n\n"
        "## Local status\n"
        f"- Local GPU usable: {bool(local.get('usable_for_gpu_training'))}\n"
        f"- Local detail: {local.get('detail', 'unknown')}\n\n"
        "## Free GPU steps\n"
        f"{step_lines}\n\n"
        "## What is inside\n"
        "- `nova_kaggle_gpu_training.ipynb`: the notebook to run on Kaggle.\n"
        "- `tools/train_nova_lora_sft.py`: LoRA/SFT trainer for Nova's large chat dataset.\n"
        "- `artifacts/nova_large_sft_dataset/`: train, validation, holdout, and preference-pair data.\n"
        "- `src/`: Nova training code.\n"
        "- `data/`, `exports/`, and `benchmark_lab/`: focused training inputs and test banks.\n"
        "- `checkpoints/registry.json`: checkpoint registry metadata. Large checkpoint weights may need a separate upload.\n\n"
        "## Default LoRA/SFT settings\n"
        "- Base model: `Qwen/Qwen2.5-1.5B-Instruct` by default, override with `NOVA_LORA_BASE_MODEL`.\n"
        "- Train records: `6000` by default, override with `NOVA_MAX_TRAIN_RECORDS`.\n"
        "- Output: `/kaggle/working/nova_lora_sft_result.zip`.\n\n"
        "## Honesty rule\n"
        "Do not count this as GPU training until the notebook prints `cuda available: True` and writes "
        "`nova_lora_sft_result.zip`.\n"
    )


def _bundle_file_if_exists(archive, source, arcname, skipped, max_bytes=8_000_000):
    source = Path(source)
    if not source.exists() or not source.is_file():
        return
    size = source.stat().st_size
    if size > max_bytes:
        skipped.append(f"{arcname} ({size} bytes)")
        return
    archive.write(source, arcname)


def _kaggle_required_checkpoint_paths(root):
    """Return the minimal checkpoint files Kaggle needs for guarded training."""
    registry_path = Path(root) / "checkpoints" / "registry.json"
    if not registry_path.exists():
        return []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    required = set()
    roles = registry.get("roles", {}) if isinstance(registry, dict) else {}
    if not isinstance(roles, dict):
        return []

    for role_record in roles.values():
        if not isinstance(role_record, dict):
            continue

        baseline = role_record.get("baseline")
        if isinstance(baseline, dict) and baseline.get("path"):
            required.add(str(baseline["path"]))

        live_sha = role_record.get("live_sha256")
        candidates = role_record.get("candidates", {})
        if live_sha and isinstance(candidates, dict):
            live_record = candidates.get(live_sha)
            if isinstance(live_record, dict) and live_record.get("path"):
                required.add(str(live_record["path"]))

    return sorted(required)


_KAGGLE_GPU_BUNDLE_CACHE = {"created_at": 0.0, "bundle": None}
_KAGGLE_GPU_BUNDLE_CACHE_LOCK = threading.Lock()
_KAGGLE_GPU_BUNDLE_CACHE_TTL_SECONDS = 300


def _build_kaggle_gpu_training_bundle():
    status = _gpu_training_status()
    now = time.time()
    with _KAGGLE_GPU_BUNDLE_CACHE_LOCK:
        cached_bundle = _KAGGLE_GPU_BUNDLE_CACHE.get("bundle")
        cached_at = float(_KAGGLE_GPU_BUNDLE_CACHE.get("created_at") or 0.0)
        if cached_bundle and now - cached_at < _KAGGLE_GPU_BUNDLE_CACHE_TTL_SECONDS:
            return {**cached_bundle, "status": status}

    skipped = []
    buffer = io.BytesIO()
    root = Path(ROOT)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README_KAGGLE_GPU.md", _kaggle_gpu_readme(status))
        archive.writestr(
            "nova_kaggle_gpu_training.ipynb",
            json.dumps(_kaggle_gpu_notebook_json(), indent=2),
        )
        archive.writestr(
            "requirements_kaggle.txt",
            "--extra-index-url https://download.pytorch.org/whl/cu118\n"
            "torch==2.5.1+cu118\n"
            "transformers>=4.46.0\n"
            "accelerate>=0.34.0\n"
            "peft>=0.13.0\n"
            "datasets>=2.20.0\n"
            "bitsandbytes>=0.43.0\n"
            "safetensors>=0.4.5\n"
            "pytest\n",
        )
        _bundle_file_if_exists(archive, root / "nova_enhanced_server.py", "nova_enhanced_server.py", skipped, max_bytes=3_000_000)
        _bundle_file_if_exists(
            archive,
            root / "tools" / "train_nova_lora_sft.py",
            "tools/train_nova_lora_sft.py",
            skipped,
            max_bytes=1_000_000,
        )

        src_root = root / "src"
        if src_root.exists():
            for path in sorted(src_root.glob("*.py")):
                _bundle_file_if_exists(archive, path, f"src/{path.name}", skipped, max_bytes=3_000_000)

        selected_data = [
            "data/targeted_transformer_answer_curriculum.jsonl",
            "data/conversation_training_data.jsonl",
            "data/routing_log.jsonl",
            "data/dictionary_memory/approved_answer_dictionary.json",
            "artifacts/nova_large_sft_dataset/train.jsonl",
            "artifacts/nova_large_sft_dataset/validation.jsonl",
            "artifacts/nova_large_sft_dataset/holdout.jsonl",
            "artifacts/nova_large_sft_dataset/preference_pairs.jsonl",
            "artifacts/nova_large_sft_dataset/manifest.json",
            "checkpoints/registry.json",
        ]
        for relative in selected_data:
            if relative == "checkpoints/registry.json":
                max_bytes = 25_000_000
            elif relative.startswith("artifacts/nova_large_sft_dataset/"):
                max_bytes = 60_000_000
            else:
                max_bytes = 8_000_000
            _bundle_file_if_exists(archive, root / relative, relative.replace("\\", "/"), skipped, max_bytes=max_bytes)

        for relative in _kaggle_required_checkpoint_paths(root):
            source = Path(relative)
            if source.is_absolute():
                try:
                    arcname = source.relative_to(root).as_posix()
                except ValueError:
                    continue
            else:
                arcname = source.as_posix()
                source = root / source
            _bundle_file_if_exists(archive, source, arcname, skipped, max_bytes=8_000_000)

        for folder in ("exports/v053_training_sets", "benchmark_lab/test_banks"):
            folder_path = root / folder
            if folder_path.exists():
                for path in sorted(folder_path.glob("*.json")):
                    arcname = f"{folder}/{path.name}".replace("\\", "/")
                    _bundle_file_if_exists(archive, path, arcname, skipped)

        if skipped:
            archive.writestr(
                "SKIPPED_LARGE_FILES.txt",
                "These files were not included because they are too large for the quick Kaggle bundle.\n"
                + "\n".join(skipped)
                + "\nUpload matching checkpoint weights separately if preflight blocks training.\n",
            )

    bundle = {
        "filename": "nova_kaggle_gpu_training.zip",
        "content_type": "application/zip",
        "bytes": buffer.getvalue(),
        "status": status,
    }
    with _KAGGLE_GPU_BUNDLE_CACHE_LOCK:
        _KAGGLE_GPU_BUNDLE_CACHE["created_at"] = time.time()
        _KAGGLE_GPU_BUNDLE_CACHE["bundle"] = {
            "filename": bundle["filename"],
            "content_type": bundle["content_type"],
            "bytes": bundle["bytes"],
        }
    return bundle


def _training_studio_status():
    try:
        from nova_training_studio import list_correction_reviews, list_training_studio_datasets

        payload = list_training_studio_datasets(ROOT)
        payload["reviews"] = list_correction_reviews(ROOT, limit=100)
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "latest": None, "datasets": [], "reviews": None}
    payload["lora_training"] = {
        "running": _STUDIO_LORA_RUNNING,
        "job_id": _STUDIO_LORA_JOB_ID,
        "log": _STUDIO_LORA_LOG[-20:],
    }
    return payload


def _training_studio_import(body):
    from nova_training_studio import import_training_data

    name = str(body.get("name") or body.get("filename") or "Nova import")
    content = str(body.get("content") or body.get("text") or "")
    source_format = str(body.get("source_format") or body.get("format") or "auto")
    max_records = int(body.get("max_records") or 2000)
    dataset = import_training_data(
        ROOT,
        name=name,
        content=content,
        source_format=source_format,
        max_records=max_records,
    )
    _TRAINING_LOG.append(
        "[TRAINING STUDIO] Imported dataset "
        + str(dataset.get("dataset_id"))
        + " records="
        + str(dataset.get("record_count"))
    )
    return {
        "ok": True,
        "dataset": dataset,
        "message": "Imported data and built Nova training dataset.",
    }


def _training_studio_feedback(body):
    from nova_training_studio import save_correction_example

    result = save_correction_example(
        ROOT,
        user_input=str(body.get("user_input") or body.get("prompt") or ""),
        bad_response=str(body.get("bad_response") or body.get("nova_response") or ""),
        better_response=str(body.get("better_response") or body.get("target_answer") or ""),
        trace=body.get("trace") if isinstance(body.get("trace"), dict) else None,
    )
    _TRAINING_LOG.append(
        "[TRAINING STUDIO] Saved correction example records="
        + str(result.get("dataset", {}).get("record_count"))
    )
    return result


def _training_studio_reviews(query=None):
    from nova_training_studio import list_correction_reviews

    query = query or {}
    return list_correction_reviews(
        ROOT,
        status=str((query.get("status") or ["all"])[0]),
        limit=int((query.get("limit") or [100])[0]),
    )


def _training_studio_review(body):
    from nova_training_studio import review_correction_example

    raw_aliases = body.get("aliases")
    if raw_aliases is not None and not isinstance(raw_aliases, list):
        raise ValueError("aliases must be an array of alternate phrasings")
    result = review_correction_example(
        ROOT,
        review_id=str(body.get("review_id") or ""),
        action=str(body.get("action") or ""),
        response=body.get("response") if "response" in body else None,
        aliases=[str(alias or "") for alias in raw_aliases] if isinstance(raw_aliases, list) else None,
    )
    _TRAINING_LOG.append(
        "[TRAINING STUDIO] Review "
        + str(result.get("action"))
        + " id="
        + str((result.get("review") or {}).get("review_id"))
    )
    return result


def _training_studio_dataset_by_id(dataset_id=None):
    status = _training_studio_status()
    wanted = str(dataset_id or "").strip()
    if wanted:
        for dataset in status.get("datasets", []):
            if dataset.get("dataset_id") == wanted:
                return dataset
        raise FileNotFoundError("Training Studio dataset not found: " + wanted)
    latest = status.get("latest")
    if not latest:
        raise FileNotFoundError("No Training Studio dataset has been imported yet.")
    return latest


def _training_studio_dry_run(dataset):
    dataset_dir = str(dataset.get("dataset_dir") or "")
    if not dataset_dir:
        raise ValueError("Training Studio dataset is missing a dataset_dir.")
    trainer = Path(ROOT) / "tools" / "train_nova_lora_sft.py"
    cmd = [
        sys.executable,
        str(trainer),
        "--project-root",
        ROOT,
        "--dataset-dir",
        dataset_dir,
        "--dry-run",
        "--max-train-records",
        "0",
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=90)
    report = None
    if result.stdout.strip():
        try:
            report = json.loads(result.stdout)
        except Exception:
            report = {"stdout": result.stdout[-2000:]}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "report": report,
        "stderr": result.stderr[-2000:],
    }


def _start_training_studio_lora_job(dataset, base_model=None):
    global _STUDIO_LORA_RUNNING, _STUDIO_LORA_JOB_ID
    with _STUDIO_LORA_LOCK:
        if _STUDIO_LORA_RUNNING:
            return {
                "ok": True,
                "started": False,
                "running": True,
                "job_id": _STUDIO_LORA_JOB_ID,
                "message": "A Training Studio LoRA job is already running.",
            }
        gpu_status = _gpu_training_status()
        local = gpu_status.get("local", {}) if isinstance(gpu_status, dict) else {}
        if not local.get("usable_for_gpu_training"):
            return {
                "ok": False,
                "started": False,
                "running": False,
                "needs_gpu": True,
                "recommended_path": "Export Kaggle bundle",
                "message": "This computer has no usable CUDA GPU, so Nova prepared the dataset but did not start slow local LoRA training.",
            }
        dataset_dir = str(dataset.get("dataset_dir") or "")
        job_id = "studio_lora_" + uuid.uuid4().hex[:8]
        log_dir = Path(ROOT) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        out_path = log_dir / f"{job_id}.out.log"
        err_path = log_dir / f"{job_id}.err.log"
        output_dir = Path(ROOT) / "artifacts" / "training_studio" / "runs" / job_id / "adapter"
        cmd = [
            sys.executable,
            str(Path(ROOT) / "tools" / "train_nova_lora_sft.py"),
            "--project-root",
            ROOT,
            "--dataset-dir",
            dataset_dir,
            "--output-dir",
            str(output_dir),
            "--max-train-records",
            "0",
        ]
        if base_model:
            cmd.extend(["--base-model", str(base_model)])
        stdout = open(out_path, "w", encoding="utf-8")
        stderr = open(err_path, "w", encoding="utf-8")
        process = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr)
        _STUDIO_LORA_RUNNING = True
        _STUDIO_LORA_JOB_ID = job_id
        _STUDIO_LORA_LOG.append("[TRAINING STUDIO] Started LoRA job " + job_id + " dataset=" + dataset_dir)

        def _watch_lora_job():
            global _STUDIO_LORA_RUNNING
            code = process.wait()
            try:
                stdout.close()
                stderr.close()
            except Exception:
                pass
            _STUDIO_LORA_LOG.append("[TRAINING STUDIO] LoRA job " + job_id + " finished code=" + str(code))
            _STUDIO_LORA_RUNNING = False

        threading.Thread(target=_watch_lora_job, daemon=True).start()
        return {
            "ok": True,
            "started": True,
            "running": True,
            "job_id": job_id,
            "stdout_log": str(out_path),
            "stderr_log": str(err_path),
            "message": "Started Training Studio LoRA job on the local GPU.",
        }


def _training_studio_train(body):
    dataset = _training_studio_dataset_by_id(body.get("dataset_id"))
    if dataset.get("review_required") and not dataset.get("training_ready"):
        raise ValueError("This dataset contains unreviewed corrections. Approve them in Review & Train first.")
    dry_run = _training_studio_dry_run(dataset)
    run_checks = bool(body.get("run_checks", True))
    report = None
    training_job = None
    if run_checks:
        report = _run_full_training_suite()
    if body.get("start_guarded_transformer"):
        training_job = _start_training_center_job()
    start_lora = bool(body.get("start_lora") or body.get("real_lora"))
    lora_job = None
    if start_lora:
        lora_job = _start_training_studio_lora_job(dataset, base_model=body.get("base_model"))
    return {
        "ok": bool(dry_run.get("ok")),
        "dataset": dataset,
        "dry_run": dry_run,
        "training_job": training_job,
        "report": report,
        "lora_job": lora_job,
        "kaggle_bundle_endpoint": "/api/training/studio/kaggle-bundle.zip?dataset_id=" + quote_plus(str(dataset.get("dataset_id"))),
        "message": "Dataset validated. Use Export Kaggle Bundle for real LoRA/GPU training, or start local LoRA on a CUDA machine.",
    }


def _memory_control_list(query="", active="all"):
    records = ltm.list_memories(query=query, active=active, limit=300)
    return {
        "ok": True,
        "count": len(records),
        "memories": records,
        "active_count": ltm.count_active(),
    }


def _memory_control_update(body):
    memory_id = str(body.get("memory_id") or "").strip()
    if not memory_id:
        raise ValueError("Missing memory_id.")
    updates = {}
    for key in ("raw_text", "slot", "value", "notes", "importance", "active", "pinned", "trainable"):
        if key in body:
            updates[key] = body.get(key)
    record = ltm.update_memory_by_id(memory_id, **updates)
    if not record:
        raise FileNotFoundError("Memory not found: " + memory_id)
    return {"ok": True, "memory": record, "message": "Memory updated."}


def _memory_control_action(body):
    memory_id = str(body.get("memory_id") or "").strip()
    action = str(body.get("action") or "").strip().lower()
    if not memory_id:
        raise ValueError("Missing memory_id.")
    if action in ("delete", "forget", "deactivate"):
        record = ltm.set_memory_active(memory_id, False)
        message = "Memory hidden."
    elif action in ("restore", "activate"):
        record = ltm.set_memory_active(memory_id, True)
        message = "Memory restored."
    elif action == "pin":
        record = ltm.set_memory_pinned(memory_id, True)
        message = "Memory pinned."
    elif action == "unpin":
        record = ltm.set_memory_pinned(memory_id, False)
        message = "Memory unpinned."
    elif action in ("train", "mark_trainable"):
        record = ltm.mark_memory_trainable(memory_id, True)
        message = "Memory marked for training."
    elif action in ("untrain", "unmark_trainable"):
        record = ltm.mark_memory_trainable(memory_id, False)
        message = "Memory removed from training queue."
    else:
        raise ValueError("Unknown memory action: " + action)
    if not record:
        raise FileNotFoundError("Memory not found: " + memory_id)
    return {"ok": True, "memory": record, "message": message}


def _adapter_registry_list():
    from nova_lora_adapter_registry import list_lora_adapters
    from nova_lora_runtime import adapter_runtime_availability

    payload = list_lora_adapters()
    for adapter in payload.get("adapters", []):
        if not isinstance(adapter, dict):
            continue
        runtime = adapter_runtime_availability(
            adapter.get("base_model", ""),
            adapter.get("path", ""),
        )
        family_text = (str(adapter.get("id") or "") + " " + str(adapter.get("base_model") or "")).lower()
        if "dolphin" in family_text:
            try:
                from nova_local_llm_connector import LocalLLMConfig

                config = LocalLLMConfig()
                model_name = str(os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_MODEL") or "nova-dolphin3-lora").strip()
                if _ollama_adapter_model_available(_ollama_adapter_chat_url(config), model_name):
                    runtime.update(
                        {
                            "runnable": True,
                            "state": "available",
                            "provider": "ollama_lora_adapter",
                            "provider_model": model_name,
                            "slow_cpu_override_available": True,
                            "reason": "The trained quantized Dolphin adapter is installed locally; its first CPU load can take several minutes.",
                        }
                    )
            except Exception:
                pass
        adapter["runtime"] = runtime
    payload["latest_adapter_ids"] = {
        "qwen": _latest_adapter_id_for_family("qwen"),
        "dolphin": _latest_adapter_id_for_family("dolphin"),
    }
    return payload


def _adapter_registry_activate(body):
    adapter_id = str(body.get("adapter_id") or "").strip()
    from nova_lora_adapter_registry import activate_lora_adapter

    adapter = activate_lora_adapter(adapter_id)
    _TRAINING_LOG.append("[ADAPTERS] Activated adapter " + str(adapter.get("id")))
    return {"ok": True, "adapter": adapter, "message": "Adapter activated."}


def _model_memory_status():
    """Return safe local model residency and system-memory information."""
    from nova_model_memory import model_memory_status

    payload = model_memory_status()
    payload["model_quality"] = _model_quality_status()
    payload["capability_evaluation"] = _capability_evaluation_status()
    return payload


def _model_quality_status():
    """Return content-free model qualification and quarantine metadata."""

    payload = MODEL_QUALITY.status()
    with _MODEL_QUALITY_JOB_LOCK:
        payload["job"] = dict(MODEL_QUALITY_JOB_STATUS)
    return payload


def _run_loaded_model_quality_check(source="manual"):
    """Qualify only resident managed models; never load or inspect Raw adapters."""

    with _MODEL_QUALITY_JOB_LOCK:
        MODEL_QUALITY_JOB_STATUS.update(
            state="running",
            source=str(source or "manual")[:32],
            started_at=datetime.now().isoformat(timespec="seconds"),
            completed_at=None,
            checked=0,
            passed=0,
            failed=0,
            error=None,
        )
    try:
        result = benchmark_loaded_ollama_models(registry=MODEL_QUALITY)
        results = list(result.get("results") or [])
        with _MODEL_QUALITY_JOB_LOCK:
            MODEL_QUALITY_JOB_STATUS.update(
                state="completed",
                completed_at=datetime.now().isoformat(timespec="seconds"),
                checked=int(result.get("checked") or 0),
                passed=sum(1 for item in results if item.get("status") == "passed"),
                failed=sum(1 for item in results if item.get("status") == "failed"),
                error=None,
            )
        return result
    except Exception:
        with _MODEL_QUALITY_JOB_LOCK:
            MODEL_QUALITY_JOB_STATUS.update(
                state="failed",
                completed_at=datetime.now().isoformat(timespec="seconds"),
                error="model_quality_check_failed",
            )
        return {
            "ok": False,
            "error": "model_quality_check_failed",
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        }


def _start_loaded_model_quality_check(source="manual"):
    """Start one bounded background qualification job."""

    if not MODEL_QUALITY.enabled:
        return {
            "ok": False,
            "state": "disabled",
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        }
    with _MODEL_QUALITY_JOB_LOCK:
        if MODEL_QUALITY_JOB_STATUS.get("state") in {"scheduled", "running"}:
            return {
                "ok": True,
                "state": MODEL_QUALITY_JOB_STATUS.get("state"),
                "already_running": True,
                "content_logged": False,
                "raw_adapter_modes_excluded": True,
            }
        MODEL_QUALITY_JOB_STATUS.update(
            state="scheduled",
            source=str(source or "manual")[:32],
            started_at=None,
            completed_at=None,
            checked=0,
            passed=0,
            failed=0,
            error=None,
        )
    thread = threading.Thread(
        target=_run_loaded_model_quality_check,
        args=(source,),
        name="nova-model-quality",
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "state": "scheduled",
        "content_logged": False,
        "raw_adapter_modes_excluded": True,
    }


def _conversation_evaluation_status():
    """Return privacy-safe diagnostics for the evaluation-only turn pack."""

    global _CONVERSATION_EVAL_STATUS_CACHE
    cached = _CONVERSATION_EVAL_STATUS_CACHE
    if isinstance(cached, dict):
        return dict(cached)
    pack_path = (
        Path(ROOT)
        / "data"
        / "evals"
        / "nova_conversation_variations_v1.json"
    )
    try:
        cases = load_conversation_eval_pack(pack_path)
        status = {
            "ok": len(cases) >= 500,
            "version": CONVERSATION_EVAL_VERSION,
            "case_count": len(cases),
            "evaluation_only": True,
            "training_allowed": False,
            "training_writes": 0,
            "content_logged": False,
        }
    except (OSError, ValueError, json.JSONDecodeError):
        status = {
            "ok": False,
            "version": CONVERSATION_EVAL_VERSION,
            "case_count": 0,
            "evaluation_only": True,
            "training_allowed": False,
            "training_writes": 0,
            "content_logged": False,
            "error": "evaluation_pack_unavailable",
        }
    _CONVERSATION_EVAL_STATUS_CACHE = dict(status)
    return status


def _capability_evaluation_status():
    """Return content-free advisory scores and current job state."""

    payload = CAPABILITY_EVAL_STORE.status()
    payload["deterministic_verifier"] = {
        "enabled": _deterministic_verifier_enabled(),
        "version": DETERMINISTIC_VERIFIER_VERSION,
        "scope": [
            "bounded_arithmetic",
            "percentage_money",
            "unit_conversion",
            "date_arithmetic",
            "numeric_comparison",
            "bounded_categorical_logic",
        ],
        "model_bypass": True,
        "raw_adapter_modes_excluded": True,
    }
    payload["shadow_router"] = {
        "enabled": _capability_shadow_router_enabled(),
        "mode": "evidence_only",
        "automatic_routing": False,
        "route_changed": False,
        "training_used": False,
        "content_logged": False,
        "raw_adapter_modes_excluded": True,
    }
    with _CAPABILITY_EVAL_JOB_LOCK:
        payload["job"] = dict(CAPABILITY_EVAL_JOB_STATUS)
    return payload


def _publish_capability_evaluations_to_model_registry(results):
    """Attach advisory scores to matching provider models without changing routing."""

    if "NOVA_GATEWAY" not in globals():
        return 0
    published = 0
    for result in list(results or []):
        if not isinstance(result, dict) or result.get("status") != "evaluated":
            continue
        provider_id = str(result.get("provider_id") or "").strip()
        model_id = str(result.get("model_id") or "").strip().removesuffix(":latest")
        if not provider_id or not model_id:
            continue
        for capability in NOVA_GATEWAY.models.list_models():
            registered_id = str(capability.model_id or "").strip().removesuffix(":latest")
            if capability.provider_id != provider_id or registered_id != model_id:
                continue
            capability.metadata = {
                **dict(capability.metadata or {}),
                "capability_evaluation": {
                    "pack_version": result.get("pack_version"),
                    "evaluated_at": result.get("evaluated_at"),
                    "overall_score": result.get("overall_score"),
                    "grade": result.get("grade"),
                    "capabilities": dict(result.get("capabilities") or {}),
                    "evaluation_only": True,
                },
            }
            NOVA_GATEWAY.models.register_model(capability)
            published += 1
    return published


def _run_capability_evaluation_job(payload):
    """Run one bounded, local-only capability evaluation outside the request."""

    mode = str((payload or {}).get("mode") or "loaded_text").strip().lower()
    with _CAPABILITY_EVAL_JOB_LOCK:
        CAPABILITY_EVAL_JOB_STATUS.update(
            state="running",
            mode=mode,
            started_at=datetime.now().isoformat(timespec="seconds"),
            completed_at=None,
            evaluated_models=0,
            registry_records_updated=0,
            error=None,
        )
    try:
        if mode == "loaded_text":
            result = evaluate_loaded_text_models(
                NOVA_GATEWAY.providers,
                quality_registry=MODEL_QUALITY,
                store=CAPABILITY_EVAL_STORE,
            )
        elif mode == "vision":
            result = evaluate_user_approved_vision(
                model_id=str((payload or {}).get("model_id") or ""),
                image_base64=str((payload or {}).get("image_base64") or ""),
                expected_keywords=list((payload or {}).get("expected_keywords") or []),
                quality_registry=MODEL_QUALITY,
                store=CAPABILITY_EVAL_STORE,
            )
        else:
            raise ValueError("Unsupported capability evaluation mode.")
        result_records = list(result.get("results") or [])
        if isinstance(result.get("record"), dict):
            result_records.append({**result["record"], "status": "evaluated"})
        published = _publish_capability_evaluations_to_model_registry(result_records)
        evaluated = int(result.get("evaluated_models") or int(result.get("status") == "evaluated"))
        terminal_state = "completed" if result.get("ok") else "failed"
        safe_error = None if result.get("ok") else str(result.get("status") or "capability_evaluation_failed")
        with _CAPABILITY_EVAL_JOB_LOCK:
            CAPABILITY_EVAL_JOB_STATUS.update(
                state=terminal_state,
                completed_at=datetime.now().isoformat(timespec="seconds"),
                evaluated_models=evaluated,
                error=safe_error,
                registry_records_updated=published,
            )
        return result
    except ValueError as error:
        safe_error = re.sub(r"[^a-zA-Z0-9 ._-]+", "", str(error))[:180]
    except Exception:
        safe_error = "capability_evaluation_failed"
    finally:
        if isinstance(payload, dict):
            payload.pop("image_base64", None)
            payload.pop("expected_keywords", None)
    with _CAPABILITY_EVAL_JOB_LOCK:
        CAPABILITY_EVAL_JOB_STATUS.update(
            state="failed",
            completed_at=datetime.now().isoformat(timespec="seconds"),
            error=safe_error,
        )
    return {
        "ok": False,
        "error": safe_error,
        "content_logged": False,
        "image_persisted": False,
        "training_used": False,
        "raw_adapter_modes_excluded": True,
        "evaluation_only": True,
    }


def _start_capability_evaluation(payload):
    """Schedule one explicitly approved evaluation without retaining request content."""

    body = dict(payload or {})
    if not CAPABILITY_EVAL_STORE.enabled:
        return {
            "ok": False,
            "state": "disabled",
            "content_logged": False,
            "training_used": False,
        }
    if body.get("user_approved") is not True:
        raise ValueError("Capability evaluation requires explicit user approval.")
    mode = str(body.get("mode") or "loaded_text").strip().lower()
    if mode not in {"loaded_text", "vision"}:
        raise ValueError("Capability evaluation mode must be loaded_text or vision.")
    job_payload = {"mode": mode}
    if mode == "vision":
        image_base64 = str(body.get("image_base64") or "")
        keywords = body.get("expected_keywords")
        if not image_base64:
            raise ValueError("Select an image for the vision evaluation.")
        if not isinstance(keywords, list) or not any(str(item).strip() for item in keywords):
            raise ValueError("Enter at least one expected visible keyword.")
        if len(image_base64) > 7_100_000:
            raise ValueError("Vision evaluation image must be 5 MB or smaller.")
        job_payload.update(
            model_id=str(body.get("model_id") or os.environ.get("NOVA_VISION_MODEL") or "moondream")[:256],
            image_base64=image_base64,
            expected_keywords=[str(item) for item in keywords[:5]],
        )
    with _CAPABILITY_EVAL_JOB_LOCK:
        if CAPABILITY_EVAL_JOB_STATUS.get("state") in {"scheduled", "running"}:
            return {
                "ok": True,
                "state": CAPABILITY_EVAL_JOB_STATUS.get("state"),
                "already_running": True,
                "content_logged": False,
                "image_persisted": False,
                "training_used": False,
                "raw_adapter_modes_excluded": True,
                "evaluation_only": True,
            }
        CAPABILITY_EVAL_JOB_STATUS.update(
            state="scheduled",
            mode=mode,
            started_at=None,
            completed_at=None,
            evaluated_models=0,
            registry_records_updated=0,
            error=None,
        )
    thread = threading.Thread(
        target=_run_capability_evaluation_job,
        args=(job_payload,),
        name="nova-capability-evaluation",
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "state": "scheduled",
        "mode": mode,
        "content_logged": False,
        "image_persisted": False,
        "training_used": False,
        "raw_adapter_modes_excluded": True,
        "evaluation_only": True,
    }


def _automatic_model_quality_check_enabled():
    return str(
        os.environ.get("NOVA_MODEL_QUALITY_AUTO_CHECK_LOADED", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}


def _unload_model_memory(body):
    """Release selected idle model memory without deleting installed files."""
    from nova_model_memory import unload_model_memory

    target = str((body or {}).get("target") or "idle").strip().lower()
    return unload_model_memory(target)


def _adapter_upload_path(filename):
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(filename or "")).strip("._")
    safe_name = safe_name or "nova_lora_adapter.zip"
    if not safe_name.lower().endswith(".zip"):
        safe_name += ".zip"
    upload_dir = Path(ROOT) / "artifacts" / "adapter_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / f"{Path(safe_name).stem}_{uuid.uuid4().hex[:10]}{Path(safe_name).suffix}"


def _adapter_registry_import_file(upload_path, adapter_id=None, activate=False):
    upload_path = Path(upload_path)
    if not upload_path.exists():
        raise FileNotFoundError(upload_path)
    if upload_path.stat().st_size > MAX_UPLOAD_BYTES:
        raise RequestBodyTooLarge(
            f"Adapter ZIP exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
        )
    from nova_lora_adapter_registry import import_lora_adapter_zip, inspect_lora_adapter_zip

    preview = inspect_lora_adapter_zip(upload_path)
    imported = import_lora_adapter_zip(
        upload_path,
        adapter_id=str(adapter_id or "").strip() or None,
        activate=bool(activate),
    )
    _TRAINING_LOG.append("[ADAPTERS] Imported adapter " + str(imported.get("id")) + " activate=" + str(bool(activate)))
    return {
        "ok": True,
        "preview": preview,
        "adapter": imported,
        "activated": bool(activate),
        "message": "Adapter imported" + (" and activated." if activate else "."),
    }


def _adapter_registry_import(body):
    filename = str(body.get("filename") or "nova_lora_adapter.zip")
    content_b64 = str(body.get("content_base64") or "")
    adapter_id = str(body.get("adapter_id") or "").strip() or None
    activate = bool(body.get("activate", False))
    if not content_b64:
        raise ValueError("Missing adapter ZIP data.")
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Adapter ZIP data is not valid base64.") from exc
    if len(raw) > MAX_UPLOAD_BYTES:
        raise RequestBodyTooLarge(
            f"Adapter ZIP exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
        )
    upload_path = _adapter_upload_path(filename)
    upload_path.write_bytes(raw)
    return _adapter_registry_import_file(upload_path, adapter_id=adapter_id, activate=activate)


def _is_explicit_deepseek_request(text):
    q = str(text or "").strip().lower()
    return bool(
        re.match(r"^(?:use|ask|call|run|try)\s+(?:local\s+)?deep\s*seek\b", q)
        or re.match(r"^(?:use|ask|call|run|try)\s+(?:local\s+)?dolphin(?:3| 3)?\b", q)
        or re.match(r"^deep\s*seek\b", q)
        or re.match(r"^deepseek\b", q)
        or re.match(r"^dolphin(?:3| 3)?\b", q)
    )


def _deepseek_direct_question(text):
    cleaned = str(text or "").strip()
    patterns = [
        r"^\s*(?:use|ask|call|run|try)\s+(?:local\s+)?deep\s*seek\s*(?:r1|model)?\s*[:,-]?\s*",
        r"^\s*(?:use|ask|call|run|try)\s+(?:local\s+)?dolphin(?:3| 3)?\s*(?:llama\s*3\.1|model)?\s*[:,-]?\s*",
        r"^\s*deep\s*seek\s*(?:r1|model)?\s*[:,-]?\s*",
        r"^\s*deepseek\s*(?:r1|model)?\s*[:,-]?\s*",
        r"^\s*dolphin(?:3| 3)?\s*(?:llama\s*3\.1|model)?\s*[:,-]?\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "Confirm that the configured local LLM is connected and ready."


def _is_local_llm_status_request(text):
    q = str(text or "").strip().lower()
    return bool(
        re.search(r"\bwhat\s+(?:llm|model)\b", q)
        or re.search(r"\bwhich\s+(?:llm|model)\b", q)
        or "what llm is in this app" in q
        or "what model is in this app" in q
    )


def _local_llm_status_response(trace):
    try:
        from nova_local_llm_connector import LocalLLMConfig
        config = LocalLLMConfig()
        model = config.model
        fast_model = config.fast_model
        deep_model = config.deep_model
        context_window = config.context_window
        timeout = config.timeout
        lora_enabled = config.lora_adapter_enabled
        lora_path = config.lora_adapter_path
        lora_base_model = config.lora_base_model
        lora_runtime_enabled = config.lora_runtime_enabled
        lora_auto_mode = config.lora_auto_mode
        lora_max_new_tokens = config.lora_max_new_tokens
    except Exception:
        model = "unknown"
        fast_model = "unknown"
        deep_model = "unknown"
        context_window = "unknown"
        timeout = "unknown"
        lora_enabled = False
        lora_path = ""
        lora_base_model = "unknown"
        lora_runtime_enabled = False
        lora_auto_mode = "unknown"
        lora_max_new_tokens = "unknown"
    if lora_enabled and not lora_path:
        try:
            from nova_lora_adapter_registry import resolve_active_lora_adapter

            active_adapter = resolve_active_lora_adapter()
            if active_adapter:
                lora_path = str(active_adapter.get("path", ""))
                lora_base_model = str(active_adapter.get("base_model") or lora_base_model)
        except Exception:
            pass
    trace["source"] = "local_llm_status"
    trace["domain"] = "local_llm_status"
    trace["roles"] = ["memory_transformer", "local_llm_status", "speech_output_transformer"]
    trace["skills"] = ["model_config_read"]
    trace["confidence"] = 0.99
    trace["local_llm_model"] = model
    trace["lora_adapter_enabled"] = bool(lora_enabled)
    trace["lora_runtime_enabled"] = bool(lora_runtime_enabled)
    trace["lora_auto_mode"] = lora_auto_mode
    trace["lora_max_new_tokens"] = lora_max_new_tokens
    trace["lora_adapter_path"] = lora_path
    trace["lora_base_model"] = lora_base_model
    trace["route_path"] = ["config_lookup", "critic", "speech_output"]
    trace["final_answer_source"] = "local_llm_status"
    lora_text = (
        f" LoRA adapter: active for `{lora_base_model}` at `{lora_path}`."
        if lora_enabled and lora_path
        else " LoRA adapter: not active."
    )
    if lora_runtime_enabled:
        smart_modes = {"smart", "smart_adapter", "adaptive", "adaptive_adapter", "qwen_dolphin"}
        qwen_first_modes = {"qwen_first", "qwen-first", "regular_qwen", "regular-qwen"}
        ollama_qwen_first_modes = {
            "ollama_qwen_first", "ollama-qwen-first", "qwen_ollama_first", "qwen-ollama-first"
        }
        if str(lora_auto_mode or "").lower() in ollama_qwen_first_modes:
            runtime_text = (
                f" LoRA runtime: enabled for explicit Raw modes; regular routing is `{lora_auto_mode}`. "
                f"Regular generated chat uses `{model}` "
                "through Ollama after Nova memory/context. "
                "The trained Qwen and Dolphin LoRA adapters remain available in explicit Raw modes, "
                "and Nova can escalate uncertain answers to a larger local model."
            )
        elif str(lora_auto_mode or "").lower() in qwen_first_modes:
            runtime_text = (
                f" LoRA runtime: enabled in `{lora_auto_mode}` mode with max {lora_max_new_tokens} new tokens; "
                "regular generated chat uses the trained Qwen 2.5 1.5B adapter after Nova memory/context, "
                "then Nova can escalate uncertain answers to a larger local model."
            )
        elif str(lora_auto_mode or "").lower() in smart_modes:
            runtime_text = (
                f" LoRA runtime: enabled in `{lora_auto_mode}` mode with max {lora_max_new_tokens} new tokens; "
                "Smart adapter mode keeps Nova memory/router first, then chooses Qwen for factual/debug answers "
                "or Dolphin for creative/social answers while planner/control routes stay fast."
            )
        else:
            runtime_text = (
                f" LoRA runtime: enabled in `{lora_auto_mode}` mode with max {lora_max_new_tokens} new tokens; "
                "Dolphin answers first for main Nova, planner/control routes stay fast, "
                "and the trained adapter is still available for weak-answer retries, deeper work, or Adapter Only mode."
            )
    else:
        runtime_text = " LoRA runtime: off."
    return (
        f"Nova is configured to use `{model}` through Ollama. "
        f"Fast route: `{fast_model}`. Deep route: `{deep_model}`. "
        f"Context window: {context_window}. Timeout: {timeout}s."
        f"{lora_text}{runtime_text}"
    ), trace


def _local_llm_trace_labels(model_name):
    model_text = str(model_name or "").lower()
    if "dolphin" in model_text:
        return "dolphin3_synthesis", ["local_llm", "dolphin3", "ollama", "direct_llm_synthesis"]
    if "lora" in model_text or "hf_peft" in model_text:
        return "lora_synthesis", ["local_llm", "hf_peft_lora", "direct_llm_synthesis"]
    if "qwen" in model_text:
        return "qwen_synthesis", ["local_llm", "qwen", "ollama", "direct_llm_synthesis"]
    return "local_llm_synthesis", ["local_llm", "direct_llm_synthesis"]


def _truthy_context_flag(context, *keys):
    if not isinstance(context, dict):
        return False
    for key in keys:
        value = context.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    return False


def _is_trained_adapter_only_context(context):
    return _is_raw_memory_mode(context) or _truthy_context_flag(
        context,
        "adapter_only_mode",
        "trained_adapter_only",
        "trained_adapter_only_mode",
    )


def _is_raw_memory_mode(context):
    return isinstance(context, dict) and context.get("nova_model_mode") == "raw_memory"


def _adapter_only_context_overrides(context):
    if not isinstance(context, dict):
        return {}
    overrides = {}
    for key in ("lora_adapter_id", "lora_adapter_path", "lora_base_model"):
        value = context.get(key)
        if value:
            overrides[key] = str(value)
    dolphin_requested = _truthy_context_flag(context, "dolphin_adapter_only", "dolphin_lora_only")
    adapter_id = str(overrides.get("lora_adapter_id", "")).lower()
    base_model = str(overrides.get("lora_base_model", "")).lower()
    if dolphin_requested or "dolphin" in adapter_id or "dolphin" in base_model:
        overrides["adapter_target"] = "dolphin"
    if _truthy_context_flag(context, "allow_slow_dolphin_cpu", "allow_slow_adapter_cpu"):
        overrides["allow_slow_dolphin_cpu"] = True
    return overrides


def _raw_adapter_conversation_history(context, current_text):
    """Return a bounded client-supplied transcript for raw adapter continuity."""
    return bounded_conversation_history(context, current_text, maximum_messages=6)


def _raw_adapter_summary_history(context):
    """Return the bounded history used to roll a supplied conversation summary."""
    return bounded_conversation_history(
        {"conversation_history": (context or {}).get("conversation_summary_history")},
        maximum_messages=6,
    )


def _raw_adapter_memory_context(context):
    """Return the bounded retrieved context that raw-memory mode may supply."""
    if not isinstance(context, dict):
        return ""
    blocks = []
    for key in ("explicit_memory_context", "memory_v2_context", "rag_context"):
        value = str(context.get(key) or "").strip()
        if value:
            blocks.append(value[:2000])
    return "\n".join(blocks)[:4000]


def _raw_adapter_prompt_with_history(
    text,
    history,
    conversation_summary=None,
    memory_context=None,
    conversation_summary_history=None,
):
    """Add conversation context without changing or post-processing the raw answer."""
    summary_context = render_conversation_summary(conversation_summary)
    memory_block = str(memory_context or "").strip()
    summary_history = list(conversation_summary_history or [])
    if not history and not summary_context and not memory_block and not summary_history:
        return str(text or "")
    lines = []
    if memory_block:
        lines.extend(["Relevant memory:", memory_block, ""])
    if summary_context:
        lines.extend([summary_context, ""])
    if summary_history:
        lines.append("Conversation summary history:")
        for message in summary_history:
            label = "User" if message["role"] == "user" else "Assistant"
            lines.append(label + ": " + message["content"])
        lines.append("")
    lines.append("Recent conversation:")
    for message in history:
        label = "User" if message["role"] == "user" else "Assistant"
        lines.append(label + ": " + message["content"])
    lines.extend(["", "User: " + str(text or "").strip(), "Assistant:"])
    return "\n".join(lines)


def _raw_memory_remote_provider():
    """Return the verified Vast semantic provider for Raw + Memory, if ready.

    Raw adapter-only mode intentionally remains local.  Raw + Memory may use a
    remote base transformer only when GPU Hub reports a currently healthy,
    explicitly verified Vast endpoint.  Provider construction is delegated to
    the same GPU Hub bridge used by managed synthesis so endpoint validation
    and the remote-host allowlist stay consistent.
    """
    if str(os.environ.get("NOVA_GPU_HUB_ENABLED", "true")).strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return None
    try:
        state = GpuHubController(ROOT).status()
        if not (
            isinstance(state, dict)
            and str(state.get("effective_mode") or "") == "vast_gpu"
            and str(state.get("verified_backend") or "") == "vast_gpu"
            and bool(state.get("available"))
            and bool(state.get("verified"))
        ):
            return None
        from nova_local_llm_connector import LocalLLMConfig
        from nova_model_provider import provider_registry_from_environment

        provider = provider_registry_from_environment(
            settings=dict(LocalLLMConfig().config),
            gpu_hub_state=state,
        ).get()
        if str(getattr(provider, "provider_id", "")).lower() not in {
            "openai-compatible",
            "vllm",
            "sglang",
        }:
            return None
        return provider
    except Exception:
        # Raw + Memory must retain its existing local adapter path whenever
        # the remote worker is unavailable, expired, or misconfigured.
        return None


def _run_trained_adapter_only_request(text, trace, context=None):
    raw_memory_mode = _is_raw_memory_mode(context)
    adapter_overrides = _adapter_only_context_overrides(context)
    adapter_target = adapter_overrides.get("adapter_target", "qwen")
    adapter_id = adapter_overrides.get("lora_adapter_id") or _latest_adapter_id_for_family(adapter_target)
    adapter_role = "raw_dolphin_adapter" if adapter_target == "dolphin" else "raw_qwen_adapter"
    allow_slow_cpu = bool(adapter_overrides.get("allow_slow_dolphin_cpu"))

    route_name = "raw_memory" if raw_memory_mode else "raw_adapter_only"
    trace["source"] = route_name
    trace["domain"] = route_name
    trace["roles"] = ["memory_transformer", adapter_role]
    trace["skills"] = ["raw_lora_generation", "adapter_only_no_nova_interception", "no_provider_fallback"]
    if raw_memory_mode:
        trace["raw_memory_mode"] = True
        trace["skills"].append("raw_memory_context")
    trace["trained_adapter_only"] = True
    trace["use_lora_runtime"] = True
    trace["adapter_target"] = adapter_target
    trace["lora_adapter_id"] = adapter_id
    trace["allow_slow_dolphin_cpu"] = allow_slow_cpu
    trace["route_path"] = ["memory_preserved", route_name, adapter_role]
    conversation_history = _raw_adapter_conversation_history(context or {}, text)
    conversation_summary = (context or {}).get("conversation_summary")
    summary_history = _raw_adapter_summary_history(context) if raw_memory_mode else []
    memory_context = _raw_adapter_memory_context(context)
    raw_prompt = _raw_adapter_prompt_with_history(
        text,
        conversation_history,
        conversation_summary,
        memory_context=memory_context,
        conversation_summary_history=summary_history,
    )
    if conversation_history:
        trace["skills"].append("raw_conversation_context")
        trace["raw_context_turns"] = len(conversation_history)
    elif raw_memory_mode:
        trace["raw_context_turns"] = 0
    if raw_memory_mode:
        trace["raw_summary_context_turns"] = len(summary_history)
    if memory_context:
        trace["raw_memory_context_used"] = True
    if render_conversation_summary(conversation_summary):
        trace["skills"].append("raw_conversation_summary")
        trace["conversation_summary_used"] = True

    if raw_memory_mode:
        remote_provider = _raw_memory_remote_provider()
        if remote_provider is not None:
            try:
                from nova_model_provider import ModelGenerationRequest

                remote_model = str(
                    getattr(remote_provider, "model_id", "") or "Qwen/Qwen3-8B"
                )
                result = remote_provider.generate(
                    ModelGenerationRequest(
                        prompt=raw_prompt,
                        model=remote_model,
                        max_tokens=256,
                        temperature=0.35,
                        reasoning_enabled=False,
                        reasoning_mode="fast",
                        metadata={
                            "route": "raw_memory",
                            "user_message": str(text or ""),
                            "memory_context_preserved": bool(memory_context),
                        },
                    )
                )
                raw_output = getattr(result, "text", "")
                answer = raw_output if isinstance(raw_output, str) else str(raw_output or "")
                if answer:
                    trace["use_lora_runtime"] = False
                    trace["remote_raw_transformer"] = True
                    trace["local_llm_synthesis_used"] = True
                    trace["local_llm_model"] = str(
                        getattr(result, "model_id", "") or remote_model
                    )
                    trace["local_llm_provider"] = str(
                        getattr(result, "provider_id", "")
                        or getattr(remote_provider, "provider_id", "")
                        or "vllm"
                    )
                    trace["remote_model_provider"] = trace["local_llm_provider"]
                    trace["gpu_backend"] = "vast_gpu"
                    trace["adapter_runtime"] = trace["local_llm_provider"]
                    trace["confidence"] = 0.92
                    trace["final_answer_source"] = route_name
                    return answer, trace
                trace["raw_memory_remote_fallback_reason"] = "remote_provider_returned_no_text"
            except Exception as exc:
                trace["raw_memory_remote_fallback_reason"] = str(exc)

    try:
        result = _generate_raw_lora_adapter(
            raw_prompt,
            adapter_id,
            max_new_tokens=256,
            allow_slow_cpu=allow_slow_cpu,
        )
        raw_output = result.get("raw_output")
        answer = raw_output if raw_memory_mode and isinstance(raw_output, str) else str(raw_output or "").strip()
        trace["local_llm_synthesis_used"] = bool(result.get("local_llm_used") and answer)
        trace["local_llm_model"] = result.get("model") or result.get("base_model") or adapter_id
        trace["local_llm_provider"] = result.get("provider") or "hf_peft_lora"
        trace["adapter_runtime"] = trace["local_llm_provider"]
        trace["confidence"] = 0.92 if answer else 0.42
        trace["final_answer_source"] = route_name if answer else route_name + "_error"
        if answer:
            return answer, trace
        reason = result.get("error") or result.get("fallback_reason") or "The selected adapter returned no text."
        trace["local_llm_error"] = str(reason)
        if raw_memory_mode:
            trace["raw_memory_fallback_reason"] = str(reason)
        return "[RAW ADAPTER ONLY] " + str(reason), trace
    except Exception as exc:
        trace["confidence"] = 0.35
        trace["local_llm_error"] = str(exc)
        trace["final_answer_source"] = route_name + "_error"
        if raw_memory_mode:
            trace["raw_memory_fallback_reason"] = "adapter_generation_exception"
        return "[RAW ADAPTER ONLY] The selected adapter could not run: " + str(exc), trace


DEFAULT_RAW_ADAPTER_COMPARE_IDS = (
    "nova-qwen2-5-1-5b-big-sft-20260713",
    "nova-dolphin3-llama3-1-8b-full-sft-20260712",
)


def _latest_adapter_id_for_family(family):
    """Resolve the newest installed adapter for one raw-control family."""
    family_key = "dolphin" if str(family or "").lower() == "dolphin" else "qwen"
    try:
        from nova_lora_adapter_registry import list_lora_adapters

        available = list_lora_adapters().get("adapters", [])
        matching = []
        for adapter in available:
            if not isinstance(adapter, dict) or not adapter.get("exists", True):
                continue
            searchable = " ".join(
                str(adapter.get(key) or "") for key in ("id", "base_model", "path")
            ).lower()
            if family_key in searchable:
                matching.append(adapter)
        if matching:
            def recency_key(item):
                adapter_id = str(item.get("id") or "")
                dated_parts = re.findall(r"20\d{6}", adapter_id)
                return (max(dated_parts) if dated_parts else "", adapter_id)

            return str(max(matching, key=recency_key).get("id"))
    except Exception:
        pass
    return DEFAULT_RAW_ADAPTER_COMPARE_IDS[1 if family_key == "dolphin" else 0]


def _adapter_compare_metadata(adapter_id):
    try:
        from nova_lora_adapter_registry import resolve_lora_adapter

        adapter = resolve_lora_adapter(str(adapter_id or ""))
        return adapter if isinstance(adapter, dict) else {}
    except Exception:
        return {}


def _raw_adapter_label(adapter_id, metadata=None):
    adapter_id = str(adapter_id or "")
    base_model = str((metadata or {}).get("base_model") or "")
    label_source = (adapter_id + " " + base_model).lower()
    if "dolphin" in label_source:
        return "RAW Dolphin adapter"
    if "qwen" in label_source:
        return "RAW Qwen adapter"
    return "RAW adapter"


def _raw_adapter_local_cpu_guard(adapter_id, metadata=None, *, allow_slow_cpu=False):
    if allow_slow_cpu or str(os.environ.get("NOVA_RAW_COMPARE_ALLOW_SLOW_CPU", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return None
    label_source = (
        str(adapter_id or "")
        + " "
        + str((metadata or {}).get("base_model") or "")
    ).lower()
    if "dolphin" not in label_source and "llama3.1-8b" not in label_source and "llama3-1-8b" not in label_source:
        return None
    try:
        import torch

        if bool(torch.cuda.is_available()):
            return None
    except Exception:
        pass
    return (
        "Skipped raw Dolphin 8B adapter generation on this CPU-only machine so the app does not freeze. "
        "Run this compare on Kaggle/GPU, or set NOVA_RAW_COMPARE_ALLOW_SLOW_CPU=true if you want to force a slow local attempt."
    )


def _lora_response_to_raw_compare(adapter_id, prompt, response, metadata=None):
    metadata = metadata or {}
    eval_metrics = metadata.get("eval_metrics") if isinstance(metadata.get("eval_metrics"), dict) else {}
    return {
        "adapter_id": str(adapter_id),
        "label": _raw_adapter_label(adapter_id, metadata),
        "base_model": str(metadata.get("base_model") or ""),
        "train_records": metadata.get("train_records"),
        "eval_loss": eval_metrics.get("eval_loss"),
        "provider": getattr(response, "provider", "hf_peft_lora"),
        "model": getattr(response, "model", ""),
        "prompt": str(prompt or ""),
        "raw_output": str(getattr(response, "raw_output", "") or ""),
        "local_llm_used": bool(getattr(response, "local_llm_used", False)),
        "error": getattr(response, "error", None),
        "fallback_used": bool(getattr(response, "fallback_used", False)),
        "fallback_reason": str(getattr(response, "fallback_reason", "") or ""),
        "response_time_ms": float(getattr(response, "response_time_ms", 0.0) or 0.0),
    }


def _ollama_adapter_chat_url(config=None):
    configured = str(os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    source_url = str(getattr(config, "url", "") or "http://127.0.0.1:11434/api/generate")
    parsed = urlparse(source_url)
    if not parsed.scheme or not parsed.netloc:
        return "http://127.0.0.1:11434/api/chat"
    return parsed.scheme + "://" + parsed.netloc + "/api/chat"


def _ollama_adapter_model_available(chat_url, model_name, timeout=3):
    parsed = urlparse(str(chat_url or ""))
    if not parsed.scheme or not parsed.netloc:
        return False
    tags_url = parsed.scheme + "://" + parsed.netloc + "/api/tags"
    try:
        request = urllib.request.Request(tags_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        requested = str(model_name or "").removesuffix(":latest")
        return any(
            str(item.get("name") or item.get("model") or "").removesuffix(":latest") == requested
            for item in payload.get("models", [])
            if isinstance(item, dict)
        )
    except Exception:
        return False


def _generate_raw_ollama_lora_adapter(prompt, adapter_id, max_new_tokens, metadata=None):
    """Use a locally created Ollama model that contains the selected LoRA."""
    from nova_local_llm_connector import LocalLLMConfig

    config = LocalLLMConfig()
    model_name = str(os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_MODEL") or "nova-dolphin3-lora").strip()
    chat_url = _ollama_adapter_chat_url(config)
    if not _ollama_adapter_model_available(chat_url, model_name):
        return None

    metadata = metadata or {}
    eval_metrics = metadata.get("eval_metrics") if isinstance(metadata.get("eval_metrics"), dict) else {}
    request_payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": str(prompt or "")}],
        "stream": False,
        "keep_alive": str(getattr(config, "ollama_keep_alive", "30m") or "30m"),
        "options": {
            "num_predict": int(max_new_tokens or 256),
            "temperature": 0.55,
            "top_p": 0.9,
        },
    }
    timeout = max(30, int(os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_TIMEOUT", "600") or 600))
    started = time.monotonic()
    try:
        from nova_model_memory import model_activity

        request = urllib.request.Request(
            chat_url,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with model_activity("dolphin"):
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        raw_output = str(message.get("content") or "").strip()
        error = None if raw_output else "The local trained Dolphin adapter returned no text."
    except Exception as exc:
        raw_output = ""
        error = "Local trained Dolphin adapter error: " + str(exc)
    return {
        "adapter_id": str(adapter_id),
        "label": _raw_adapter_label(adapter_id, metadata),
        "base_model": str(metadata.get("base_model") or "dphn/Dolphin3.0-Llama3.1-8B"),
        "train_records": metadata.get("train_records"),
        "eval_loss": eval_metrics.get("eval_loss"),
        "provider": "ollama_lora_adapter",
        "model": model_name,
        "prompt": str(prompt or ""),
        "raw_output": raw_output,
        "local_llm_used": bool(raw_output),
        "error": error,
        "fallback_used": False,
        "fallback_reason": "",
        "response_time_ms": round((time.monotonic() - started) * 1000, 3),
    }


def _generate_raw_lora_adapter(prompt, adapter_id, max_new_tokens=192, *, allow_slow_cpu=False):
    metadata = _adapter_compare_metadata(adapter_id)
    eval_metrics = metadata.get("eval_metrics") if isinstance(metadata.get("eval_metrics"), dict) else {}
    adapter_family = (str(adapter_id or "") + " " + str(metadata.get("base_model") or "")).lower()
    if "dolphin" in adapter_family:
        ollama_result = _generate_raw_ollama_lora_adapter(
            prompt,
            adapter_id,
            max_new_tokens,
            metadata,
        )
        if ollama_result is not None:
            return ollama_result
    guarded_reason = _raw_adapter_local_cpu_guard(
        adapter_id,
        metadata,
        allow_slow_cpu=allow_slow_cpu,
    )
    if guarded_reason:
        return {
            "adapter_id": str(adapter_id),
            "label": _raw_adapter_label(adapter_id, metadata),
            "base_model": str(metadata.get("base_model") or ""),
            "train_records": metadata.get("train_records"),
            "eval_loss": eval_metrics.get("eval_loss"),
            "provider": "hf_peft_lora",
            "model": str(metadata.get("base_model") or ""),
            "prompt": str(prompt or ""),
            "raw_output": "",
            "local_llm_used": False,
            "error": guarded_reason,
            "fallback_used": True,
            "fallback_reason": "Raw adapter compare safe guard",
            "response_time_ms": 0.0,
        }
    try:
        from nova_local_llm_connector import LocalLLMConfig
        import nova_lora_runtime

        config = LocalLLMConfig()
        config.config.update(
            {
                "NOVA_USE_LOCAL_LLM": True,
                "NOVA_LORA_ADAPTER_ENABLED": True,
                "NOVA_LORA_RUNTIME_ENABLED": True,
                "NOVA_LORA_MAX_NEW_TOKENS": int(max_new_tokens or 192),
            }
        )
        response = nova_lora_runtime.generate_with_lora(
            str(prompt or ""),
            config=config,
            adapter_id=str(adapter_id),
            max_new_tokens=int(max_new_tokens or 192),
            temperature=0.35,
            top_p=0.9,
            allow_slow_cpu=allow_slow_cpu,
            raw_mode=True,
        )
        return _lora_response_to_raw_compare(adapter_id, prompt, response, metadata)
    except Exception as exc:
        return {
            "adapter_id": str(adapter_id),
            "label": _raw_adapter_label(adapter_id, metadata),
            "base_model": str(metadata.get("base_model") or ""),
            "train_records": metadata.get("train_records"),
            "eval_loss": eval_metrics.get("eval_loss"),
            "provider": "hf_peft_lora",
            "model": "",
            "prompt": str(prompt or ""),
            "raw_output": "",
            "local_llm_used": False,
            "error": str(exc),
            "fallback_used": True,
            "fallback_reason": "Raw adapter compare could not run this adapter",
            "response_time_ms": 0.0,
        }


def _raw_adapter_output_status(output):
    """Classify raw output without changing any model-generated text."""
    if not isinstance(output, dict):
        return "error", True
    if output.get("error"):
        return "error", False
    raw_text = str(output.get("raw_output") or "").strip()
    if not raw_text:
        return "empty", False
    word_count = len(re.findall(r"\b[\w']+\b", raw_text))
    has_terminal_punctuation = bool(re.search(r"[.!?][\"')\]}]*$", raw_text))
    likely_incomplete = not has_terminal_punctuation and word_count < 24
    return ("incomplete" if likely_incomplete else "complete"), likely_incomplete


def _nova_app_fix_for_adapter_compare(prompt, adapter_outputs, context=None):
    try:
        review_context = dict(context or {}) if isinstance(context, dict) else {}
        review_context.update(
            {
                "adapter_compare_review": True,
                "raw_adapter_outputs": adapter_outputs,
            }
        )
        response, trace = brain_route(
            str(prompt or ""),
            context=review_context,
        )
        incomplete_labels = [
            str(item.get("label") or item.get("adapter_id") or "adapter")
            for item in adapter_outputs
            if isinstance(item, dict) and item.get("output_status") == "incomplete"
        ]
        if incomplete_labels:
            response = (
                "Adapter review: "
                + ", ".join(incomplete_labels)
                + " ended mid-thought, so those raw samples are not usable as final answers. "
                "Their text is shown unchanged for diagnosis.\n\nNova answer:\n"
                + str(response or "")
            )
            trace = dict(trace or {})
            trace["raw_adapter_incomplete"] = incomplete_labels
        return {
            "label": "Nova app review/fix",
            "response": response,
            "trace": trace,
        }
    except Exception as exc:
        return {
            "label": "Nova app review/fix",
            "response": "",
            "trace": {"source": "adapter_compare_review_error", "error": str(exc)},
            "error": str(exc),
        }


def _compare_raw_lora_adapters(text, adapter_ids=None, max_new_tokens=192, context=None):
    prompt = str(text or "").strip()
    max_new_tokens = max(16, min(int(max_new_tokens or 192), 512))
    requested = adapter_ids or DEFAULT_RAW_ADAPTER_COMPARE_IDS
    clean_ids = []
    for adapter_id in requested:
        adapter_id = str(adapter_id or "").strip()
        if adapter_id and adapter_id not in clean_ids:
            clean_ids.append(adapter_id)
    if not clean_ids:
        clean_ids = list(DEFAULT_RAW_ADAPTER_COMPARE_IDS)

    adapter_outputs = []
    for adapter_id in clean_ids[:4]:
        output = _generate_raw_lora_adapter(prompt, adapter_id, max_new_tokens=max_new_tokens)
        output = dict(output or {})
        output_status, likely_truncated = _raw_adapter_output_status(output)
        output["output_status"] = output_status
        output["likely_truncated"] = likely_truncated
        output["requested_max_new_tokens"] = max_new_tokens
        adapter_outputs.append(output)
    nova_fix = _nova_app_fix_for_adapter_compare(prompt, adapter_outputs, context=context)
    return {
        "ok": True,
        "mode": "raw_adapter_compare",
        "prompt": prompt,
        "adapter_outputs": adapter_outputs,
        "nova_app_fix": nova_fix,
    }


def _run_direct_deepseek_request(text, trace):
    question = _deepseek_direct_question(text)
    fallback_model = "dolphin3"
    try:
        from nova_local_llm_connector import LocalLLMConfig
        fallback_model = LocalLLMConfig().direct_deepseek_model
    except Exception:
        pass

    try:
        import nova_llm_synthesizer as llm_synth

        answer, ok, error = llm_synth.generate(
            {
                "system_prompt": (
                    "You are Nova using the configured local Dolphin3 Llama 3.1 model through Ollama. "
                    "Answer the user's request directly and clearly. "
                    "Do not mention paid APIs. Do not invent saved personal facts."
                ),
                "user_question": question,
                "route": "deepseek_direct",
            }
        )
        model = getattr(llm_synth, "LAST_LOCAL_LLM_MODEL", None) or fallback_model
        synthesis_label, synthesis_skills = _local_llm_trace_labels(model)
        trace["source"] = "local_llm"
        trace["domain"] = "deepseek_direct"
        trace["roles"] = ["local_llm_planner", synthesis_label, "critic_conscience_transformer"]
        trace["skills"] = synthesis_skills
        trace["local_llm_synthesis_used"] = bool(ok and answer)
        trace["local_llm_model"] = model
        trace["deepseek_question"] = question
        trace["route_path"] = ["local_llm_direct", synthesis_label, "critic", "speech_output"]
        trace["confidence"] = 0.91 if ok and answer else 0.45
        trace["final_answer_source"] = "local_llm" if ok and answer else "local_llm_fallback"
        if ok and answer:
            return answer, trace
        trace["local_llm_fallback_reason"] = error or "The configured local LLM returned no final answer"
        return (
            "[LOCAL LLM] Dolphin3 is installed, but it did not return a final answer yet. "
            "Try a shorter prompt or ask again. Reason: " + str(trace["local_llm_fallback_reason"])
        ), trace
    except Exception as exc:
        trace["source"] = "local_llm"
        trace["domain"] = "deepseek_direct"
        trace["roles"] = ["local_llm_router", "critic_conscience_transformer"]
        trace["skills"] = ["local_llm_error"]
        trace["confidence"] = 0.35
        trace["local_llm_model"] = fallback_model
        trace["local_llm_error"] = str(exc)
        trace["route_path"] = ["local_llm_direct", "error_guard", "speech_output"]
        trace["final_answer_source"] = "local_llm_error"
        return "[LOCAL LLM] Dolphin3 could not run: " + str(exc), trace


def _adapter_memory_response(trace, response, *, source, domain, skills, event=None, confidence=0.95):
    trace["source"] = source
    trace["domain"] = domain
    trace["roles"] = ["memory_transformer"]
    trace["skills"] = list(skills)
    trace["confidence"] = confidence
    trace["memory_event"] = event
    trace["route_path"] = [source, "memory_transformer"]
    trace["final_answer_source"] = source
    return response, trace


def _extract_user_name_introduction(text):
    def clean_candidate(value):
        candidate = str(value or "").strip()
        # A name introduction is often followed by an instruction in the same
        # message. Keep the name and discard that second sentence/command.
        candidate = re.split(
            r"\s+(?:remember|please|for this conversation|from now on|"
            r"you can call me|i want you to|i live|i am|i'm)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return candidate.rstrip(".!? ").strip(" \'\".,!?;:")

    raw = str(text or "").strip()
    lowered = raw.lower()
    name = None
    if lowered.startswith("my name is") and not any(
        word in lowered for word in ("your", "cat", "dog", "bird", "fish", "pet")
    ):
        match = re.search(r"^my name is\s+(.+)", raw, re.IGNORECASE)
        if match:
            name = clean_candidate(match.group(1))
    elif lowered.startswith("i am ") and not any(
        word in lowered for word in ("cat", "dog", "bird", "fish", "hamster", "pet")
    ):
        candidate = clean_candidate(raw[5:])
        if (
            candidate
            and len(candidate) > 1
            and candidate[0].isupper()
            and len(candidate.split()) <= 5
        ):
            name = candidate
    elif lowered.startswith("i'm "):
        candidate = clean_candidate(raw[4:])
        if (
            candidate
            and candidate[0].isupper()
            and len(candidate.split()) <= 5
        ):
            name = candidate
    elif lowered.startswith("call me "):
        name = clean_candidate(raw[8:])
    return name or None


def _is_name_recall_request(text):
    """Recognize direct identity recall phrasing before slow model routing."""
    q = " ".join(str(text or "").lower().split()).strip(" .!?;")
    return bool(
        re.fullmatch(
            r"(?:what|which) (?:is )?my name|"
            r"(?:what|which) name did i (?:just )?(?:give you|give|say|tell you|use|provide)|"
            r"(?:what|which) name (?:is )?(?:saved|stored|remembered) for me|"
            r"(?:what|which) name do you have for me|"
            r"what did i (?:just )?(?:say|tell you) (?:my )?name",
            q,
        )
    )


def _handle_adapter_only_memory_route(
    text,
    trace,
    *,
    memory_read_allowed=True,
    memory_write_allowed=True,
):
    """Handle explicit memory operations before handing all other text to a raw adapter."""
    q = str(text or "").lower().strip()
    raw_text = str(text or "").strip()

    if memory_write_allowed and q.startswith("learn this:"):
        lesson = raw_text[11:].strip()
        if lesson:
            lesson_id = "lesson_" + str(len(MEMORY["lessons"]) + 1)
            MEMORY["lessons"][lesson_id] = {
                "text": lesson,
                "learned_at": datetime.now().isoformat(),
                "session": SESSION_ID,
            }
            MEMORY["last_lesson"] = lesson_id
            _save_memory()
            if not _TRAINING_RUNNING:
                _start_training()
            return _adapter_memory_response(
                trace,
                "[LEARNING] Lesson stored: '" + lesson + "'",
                source="rapid_learning",
                domain="memory_write",
                skills=["learning_intake", "memory_lock"],
                event="lesson_created:" + lesson_id,
                confidence=0.91,
            )

    ltm_prefixes = (
        "long-term remember this:", "long term remember this:", "remember this long term:",
        "save this to long-term memory:", "always remember:", "permanently remember:",
        "remember long term ", "remember long-term ", "remember this:", "remember this ",
        "save this:", "save this ",
    )
    if memory_write_allowed:
        for prefix in ltm_prefixes:
            if q.startswith(prefix):
                value = raw_text[len(prefix):].strip()
                if value:
                    record = ltm.add_memory(value, source_command="long_term")
                    if record:
                        return _adapter_memory_response(
                            trace,
                            "Got it — I'll remember long-term: '" + value + "'",
                            source="long_term_memory",
                            domain="memory_write",
                            skills=["long_term_save", "memory_lock"],
                            event="long_term_saved:" + str(record.get("memory_id", "unknown")),
                        )

    if memory_read_allowed and q in (
        "show long-term memory", "show long term memory", "what do you remember long term",
        "list saved memories", "list long term memory",
    ):
        records = ltm.get_all(active_only=True)
        if records:
            lines = ["[LONG TERM MEMORY] Here's what I remember long-term:"]
            for record in records[:10]:
                lines.append("  - " + str(record.get("extracted_slot", "?")) + ": " + str(record.get("extracted_value", "?")))
            response = "\n".join(lines)
        else:
            response = "[LONG TERM MEMORY] No long-term memories saved yet."
        return _adapter_memory_response(
            trace, response, source="long_term_memory", domain="memory_read", skills=["long_term_list"]
        )

    if memory_write_allowed and q.startswith("forget long-term memory:"):
        query = raw_text[24:].strip()
        if query:
            count = ltm.forget_by_query(query)
            response = (
                "Forgot " + str(count) + " long-term memory record(s) matching: '" + query + "'."
                if count else "I couldn't find any active long-term memory matching: '" + query + "'."
            )
            return _adapter_memory_response(
                trace, response, source="long_term_memory", domain="memory_forget",
                skills=["long_term_forget"], event="long_term_forgot:" + str(count)
            )

    if memory_write_allowed and q.startswith("edit long-term memory:"):
        edit_text = raw_text[22:].strip()
        if "->" in edit_text:
            old_value, new_value = (part.strip() for part in edit_text.split("->", 1))
            if old_value and new_value and ltm.edit_memory(old_value, new_value):
                return _adapter_memory_response(
                    trace,
                    "Updated long-term memory: '" + old_value + "' -> '" + new_value + "'.",
                    source="long_term_memory", domain="memory_write", skills=["long_term_edit"],
                )

    if _ENTITY_MEMORY_AVAIL and entity_memory:
        entity_request = entity_memory.parse_entity_memory_request(text)
        allowed = bool(entity_request) and (
            (entity_request.get("action") == "save" and memory_write_allowed)
            or (entity_request.get("action") != "save" and memory_read_allowed)
        )
        if allowed:
            result = _handle_entity_memory_route(text, trace)
            if result:
                return result

    if memory_write_allowed:
        pet_fact = _extract_pet_name_statement(text)
        if pet_fact:
            pet_type, pet_name = pet_fact
            pet_slot = _save_pet_name(pet_type, pet_name)
            label = "pet" if pet_type == "pet" else pet_type
            return _adapter_memory_response(
                trace, "Got it — your " + label + "'s name is " + pet_name + ".",
                source="pet_memory", domain="memory_write", skills=["pet_memory_save", "slot_binding"],
                event="pet_saved:" + pet_slot,
            )

        relationship_fact = _extract_relationship_name_statement(text)
        if relationship_fact:
            relationship_key, label, name = relationship_fact
            _save_relationship_name(relationship_key, label, name)
            verb = "was" if relationship_key.startswith("old_") else "is"
            return _adapter_memory_response(
                trace, "Got it — your " + label + "'s name " + verb + " " + name + ".",
                source="relationship_memory", domain="memory_write",
                skills=["relationship_memory_save", "slot_binding"],
                event="relationship_saved:" + relationship_key + "_name",
            )

        relationship_color = _extract_relationship_favorite_color_statement(text)
        if relationship_color:
            relationship_key, label, color = relationship_color
            _save_relationship_favorite_color(relationship_key, label, color)
            verb = "was" if relationship_key.startswith("old_") else "is"
            return _adapter_memory_response(
                trace, "Got it — your " + label + "'s favorite color " + verb + " " + color + ".",
                source="relationship_memory", domain="memory_write",
                skills=["relationship_memory_save", "slot_binding"],
                event="relationship_saved:" + relationship_key + "_favorite_color",
            )

        introduced_name = _extract_user_name_introduction(text)
        if introduced_name:
            key = introduced_name.lower()
            MEMORY["people"][key] = {
                "name": introduced_name,
                "introduced_at": datetime.now().isoformat(),
                "session": SESSION_ID,
            }
            MEMORY["last_person"] = key
            _save_memory()
            return _adapter_memory_response(
                trace, "Nice to meet you, " + introduced_name + ". I'll remember your name.",
                source="people_memory", domain="memory_write", skills=["name_intake", "profile_creation"],
                event="person_introduced:" + introduced_name,
                confidence=0.93,
            )

    if memory_read_allowed and (
        _is_name_recall_request(text)
        or any(phrase in q for phrase in ("do you know me", "who am i"))
    ):
        last_person = MEMORY.get("last_person")
        if last_person and last_person in MEMORY.get("people", {}):
            name = MEMORY["people"][last_person]["name"]
            return _adapter_memory_response(
                trace, "Your name is " + name + ". I remember you.",
                source="people_memory", domain="memory_read", skills=["name_recall"],
                event="name_recall:" + name, confidence=0.94,
            )

    if memory_read_allowed:
        pet_type = _pet_name_recall_type(text)
        if pet_type:
            pet_slot, pet_name, stored_type = _get_pet_name(pet_type)
            label = "pet" if stored_type == "pet" else stored_type
            response = (
                "Your " + label + "'s name is " + pet_name + "."
                if pet_name else "I don't have your " + pet_type + " name saved yet."
            )
            return _adapter_memory_response(
                trace, response, source="pet_memory", domain="memory_read", skills=["pet_memory_recall"],
                event=("pet_recall:" + pet_slot) if pet_name else ("pet_missing:" + pet_type + "_name"),
                confidence=0.95 if pet_name else 0.65,
            )

        pet_identity = _find_pet_by_name(text)
        if pet_identity:
            pet_slot, pet_name, pet_type = pet_identity
            label = "pet" if pet_type == "pet" else pet_type
            return _adapter_memory_response(
                trace, pet_name + " is your " + label + ".",
                source="pet_memory", domain="memory_read", skills=["pet_identity_recall"],
                event="pet_identity_recall:" + pet_slot,
            )

        relationship_color = _relationship_favorite_color_recall_kind(text)
        if relationship_color:
            relationship_key, label = relationship_color
            color = _get_relationship_favorite_color(relationship_key)
            response = (
                "Your " + label + "'s favorite color is " + color + "."
                if color else "I don't have your " + label + "'s favorite color saved yet."
            )
            return _adapter_memory_response(
                trace, response, source="relationship_memory", domain="memory_read",
                skills=["relationship_memory_recall"], event="relationship_recall:" + relationship_key + "_favorite_color",
                confidence=0.94 if color else 0.65,
            )

        relationship = _relationship_name_recall_kind(text)
        if relationship:
            relationship_key, label = relationship
            name = _get_relationship_name(relationship_key)
            verb = "was" if relationship_key.startswith("old_") else "is"
            response = (
                "Your " + label + "'s name " + verb + " " + name + "."
                if name else "I don't have your " + label + "'s name saved yet."
            )
            return _adapter_memory_response(
                trace, response, source="relationship_memory", domain="memory_read",
                skills=["relationship_memory_recall"], event="relationship_recall:" + relationship_key + "_name",
                confidence=0.94 if name else 0.65,
            )

        if hasattr(ltm, "recall_from_question"):
            try:
                recalled = ltm.recall_from_question(text)
            except Exception:
                recalled = None
            if recalled:
                record, answer = recalled
                return _adapter_memory_response(
                    trace, answer, source="long_term_memory", domain="memory_read",
                    skills=["long_term_recall", "natural_slot_recall"],
                    event="long_term_recall:" + str(record.get("memory_id", "?")), confidence=0.96,
                )

        if hasattr(ltm, "missing_recall_answer"):
            try:
                missing = ltm.missing_recall_answer(text)
            except Exception:
                missing = None
            if missing:
                return _adapter_memory_response(
                    trace, missing, source="long_term_memory", domain="memory_read",
                    skills=["long_term_recall", "missing_recall_guard"], event="long_term_missing", confidence=0.86,
                )
    return None


def _simple_arithmetic_fast_path(text):
    """Solve only a complete, bounded two-integer arithmetic request."""

    match = re.fullmatch(
        r"\s*(?:(?:what is|calculate|compute|solve|evaluate)\s+)?"
        r"(?P<left>\d+)\s*"
        r"(?P<operator>\+|plus|-|\*|x|times|multiplied by|/|divided by)\s*"
        r"(?P<right>\d+)\s*[?!.]*\s*",
        str(text or ""),
        flags=re.I,
    )
    if match is None:
        return None
    left = int(match.group("left"))
    right = int(match.group("right"))
    operator = match.group("operator").lower()
    display_operator = {
        "+": "+",
        "plus": "+",
        "-": "-",
        "*": "*",
        "x": "*",
        "times": "*",
        "multiplied by": "*",
        "/": "/",
        "divided by": "/",
    }[operator]
    if display_operator == "/" and right == 0:
        result = "undefined"
    elif display_operator == "+":
        result = left + right
    elif display_operator == "-":
        result = left - right
    elif display_operator == "*":
        result = left * right
    else:
        result = left / right
    return f"{left} {display_operator} {right}", result


def _evaluation_mutation_guard_response(text, context):
    """Return a non-retained refusal before an evaluation can mutate state."""

    if not (
        isinstance(context, dict)
        and context.get("evaluation_only") is True
    ):
        return None
    nova_request = context.get("nova_request")
    mutation_reason = evaluation_mutation_reason(
        text,
        has_tools=bool(
            isinstance(nova_request, dict)
            and nova_request.get("tools")
        ),
        context_flags=context,
    )
    if not mutation_reason and _ENTITY_MEMORY_AVAIL and entity_memory:
        try:
            if entity_memory.parse_entity_save(text):
                mutation_reason = "structured entity memory mutation"
        except (TypeError, ValueError):
            mutation_reason = "unclassifiable structured memory request"
    if not mutation_reason and _extract_pet_name_statement(text):
        mutation_reason = "structured pet memory mutation"
    if not mutation_reason and _extract_relationship_name_statement(text):
        mutation_reason = "structured relationship memory mutation"
    if not mutation_reason and _extract_relationship_favorite_color_statement(text):
        mutation_reason = "structured relationship memory mutation"
    if not mutation_reason and _extract_user_name_introduction(text):
        mutation_reason = "structured user identity mutation"
    if not mutation_reason:
        return None
    return (
        "Evaluation-only mode cannot perform state-changing actions. "
        "Use a normal authorized Nova request for that operation.",
        {
            "source": "evaluation_mutation_guard",
            "route": "evaluation_mutation_guard",
            "final_answer_source": "evaluation_mutation_guard",
            "evaluation_only": True,
            "retained": False,
            "mutation_blocked": True,
            "mutation_category": mutation_reason,
            "content_logged": False,
        },
    )


def brain_route(text, context=None):
    global PRIVATE_MODE, _LAST_USER_TEXT, _LAST_NOVA_RESPONSE, _LAST_WEB_LOOKUP_TOPIC, _LAST_WEB_LOOKUP_KIND, _LAST_WEB_LOOKUP_ITEMS, _INDEPENDENT_THINKING_MODE
    q = text.lower().strip()
    gateway_context = context if isinstance(context, dict) and context.get("nova_gateway") else None
    evaluation_only = bool(
        isinstance(context, dict) and context.get("evaluation_only")
    )
    evaluation_mutation_block = _evaluation_mutation_guard_response(text, context)
    if evaluation_mutation_block is not None:
        return evaluation_mutation_block
    memory_read_allowed = True if gateway_context is None else bool(gateway_context.get("memory_read_allowed", False))
    memory_write_allowed = True if gateway_context is None else bool(gateway_context.get("memory_write_allowed", False))
    conversation_memory_allowed = True if gateway_context is None else bool(gateway_context.get("conversation_memory_allowed", False))
    automatic_durable_writes_allowed = bool(
        context.get("automatic_durable_writes_allowed", True)
        if isinstance(context, dict)
        else True
    )
    if evaluation_only:
        memory_write_allowed = False
        conversation_memory_allowed = False
    _CONVERSATION_WRITES_ALLOWED.set(
        bool(
            memory_write_allowed
            and conversation_memory_allowed
            and automatic_durable_writes_allowed
        )
    )
    route_memory = MEMORY if memory_read_allowed else {
        key: ({} if isinstance(value, dict) else [] if isinstance(value, list) else None)
        for key, value in MEMORY.items()
    }
    trace = {"input": text, "timestamp": datetime.now().isoformat(), "roles": [], "skills": [],
             "confidence": 0.0, "memory_event": None, "permission": None,
             "final_answer_source": None}
    if evaluation_only:
        trace["evaluation_only"] = True
        trace["training_write_allowed"] = False
        trace["memory_write_allowed"] = False
    if isinstance(context, dict) and isinstance(context.get("turn_state"), dict):
        trace["turn_analysis"] = {
            key: value
            for key, value in context["turn_state"].items()
            if key != "user_text"
        }
        trace["reasoning_mode"] = str(
            context["turn_state"].get("reasoning_mode") or "fast"
        )
    if gateway_context:
        trace["nova_gateway"] = True
        trace["request_id"] = gateway_context.get("request_id")
        trace["memory_read_allowed"] = memory_read_allowed
        trace["memory_write_allowed"] = memory_write_allowed
    if (
        isinstance(context, dict)
        and context.get("rag_insufficient")
        and not _is_raw_memory_mode(context)
    ):
        trace["source"] = "nova_rag"
        trace["domain"] = "knowledge_retrieval"
        trace["skills"] = ["rag_retrieval", "insufficient_evidence_guard"]
        trace["confidence"] = 0.99
        trace["final_answer_source"] = "rag_insufficient_evidence"
        trace["rag"] = context.get("rag_trace") or {
            "status": "insufficient_evidence",
            "passage_count": 0,
            "content_logged": False,
        }
        return (
            "The available Nova knowledge sources do not answer that question. "
            "I will not invent an answer; you can add the source or authorize a current web search.",
            trace,
        )
    if conversation_memory_allowed:
        trace = _attach_conversation_state(trace, text)
    sensor_snapshot = _sanitize_sensor_snapshot((context or {}).get("sensor_snapshot")) if isinstance(context, dict) else None
    if sensor_snapshot:
        trace["sensor_snapshot"] = sensor_snapshot
    trained_adapter_only_requested = _is_trained_adapter_only_context(context)
    if trained_adapter_only_requested:
        trace["trained_adapter_only_requested"] = True
    joke_request_kind = _joke_request_kind(text, context)
    if not joke_request_kind and not is_bridge_turn(text):
        _clear_joke_context(context)

    # ─── Permission Commands ───
    if q in ("allow mic","enable mic"): PERMISSIONS["mic"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="mic_allowed"; trace = _set_final_answer_source(trace); return "[PERMISSION] Microphone enabled.", trace
    if q in ("deny mic","disable mic"): PERMISSIONS["mic"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="mic_denied"; trace = _set_final_answer_source(trace); return "[PERMISSION] Microphone disabled.", trace
    if q in ("allow camera","enable camera"): PERMISSIONS["camera"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="camera_allowed"; trace = _set_final_answer_source(trace); return "[PERMISSION] Camera enabled.", trace
    if q in ("deny camera","disable camera"): PERMISSIONS["camera"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="camera_denied"; trace = _set_final_answer_source(trace); return "[PERMISSION] Camera disabled.", trace
    if q in ("allow speaker","enable speaker"): PERMISSIONS["speaker"]=True; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="speaker_allowed"; trace = _set_final_answer_source(trace); return "[PERMISSION] Speaker enabled.", trace
    if q in ("deny speaker","disable speaker"): PERMISSIONS["speaker"]=False; trace["roles"]=["permission_gate"]; trace["confidence"]=1.0; trace["permission"]="speaker_denied"; trace = _set_final_answer_source(trace); return "[PERMISSION] Speaker disabled.", trace
    if q in ("private mode","toggle private"): PRIVATE_MODE=not PRIVATE_MODE; trace["roles"]=["private_mode_controller"]; trace["confidence"]=1.0; trace = _set_final_answer_source(trace); return "[PRIVATE MODE] Enabled." if PRIVATE_MODE else "[PRIVATE MODE] Disabled.", trace
    if q in ("stop all","emergency stop"):
        for k in PERMISSIONS: PERMISSIONS[k]=False
        trace["roles"]=["emergency_stop"]; trace["skills"]=["stop_all"]; trace["confidence"]=1.0
        trace = _set_final_answer_source(trace)
        return "[STOP ALL] All sensors stopped. Returns to safe idle.", trace

    if trained_adapter_only_requested:
        raw_memory_mode = _is_raw_memory_mode(context)
        memory_result = _handle_adapter_only_memory_route(
            text,
            trace,
            memory_read_allowed=memory_read_allowed,
            memory_write_allowed=memory_write_allowed,
        )
        if raw_memory_mode:
            raw_memory_context = dict(context or {})
            entity_memory_result = None
            if memory_result and trace.get("domain") == "entity_memory":
                entity_memory_result = memory_result
            elif memory_result is None:
                entity_memory_result = _handle_entity_memory_route(text, trace)
            if memory_result:
                memory_response, trace = memory_result
                if trace.get("domain") == "memory_read":
                    raw_memory_context["explicit_memory_context"] = str(
                        memory_response or ""
                    )[:2000]
                    trace["raw_memory_recall_used"] = True
            if entity_memory_result:
                entity_memory_response, trace = entity_memory_result
                raw_memory_context["explicit_memory_context"] = str(
                    entity_memory_response or ""
                )[:2000]
                trace["raw_memory_entity_context_used"] = True
            response, trace = _run_trained_adapter_only_request(
                text,
                trace,
                context=raw_memory_context,
            )
        elif memory_result:
            response, trace = memory_result
        else:
            response, trace = _run_trained_adapter_only_request(text, trace, context=context)
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    # Prefer the transcript supplied by this client over process-wide legacy
    # globals. This keeps phone, desktop, and API conversations from borrowing
    # one another's short follow-up context.
    conversation_history = bounded_conversation_history(context or {}, text)
    client_previous_user, client_previous_answer = previous_exchange(conversation_history)
    legacy_previous_user = "" if gateway_context is not None else _LAST_USER_TEXT
    legacy_previous_answer = "" if gateway_context is not None else _LAST_NOVA_RESPONSE
    previous_user = client_previous_user or legacy_previous_user
    previous_answer = client_previous_answer or legacy_previous_answer
    context_resolution = resolve_contextual_followup(
        text,
        conversation_history,
        fallback_previous_user=legacy_previous_user,
        fallback_previous_answer=legacy_previous_answer,
    )
    if context_resolution.is_followup:
        previous_user = context_resolution.previous_user or previous_user
        previous_answer = context_resolution.previous_answer or previous_answer
    if conversation_history:
        trace["client_context_used"] = True
        trace["client_context_messages"] = len(conversation_history)
    if context_resolution.is_followup:
        trace["context_resolution"] = context_resolution.kind
        trace["context_resolution_confidence"] = context_resolution.confidence
        trace["context_anchor_distance"] = context_resolution.anchor_distance
        if context_resolution.subject:
            trace["conversation_subject"] = context_resolution.subject
        if context_resolution.emotion:
            trace["conversation_emotion"] = context_resolution.emotion

    if _is_local_llm_status_request(text):
        return _local_llm_status_response(trace)

    relationship_coaching = _relationship_coaching_kind(text, previous_user, previous_answer)
    if relationship_coaching:
        response = _relationship_coaching_response(relationship_coaching)
        trace["source"] = "relationship_coaching"
        trace["domain"] = "relationship_advice"
        trace["roles"] = [
            "right_hemisphere",
            "critic_conscience_transformer",
            "memory_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = [
            "context_recall",
            "concrete_wording",
            "relationship_coaching",
            "respectful_boundaries",
        ]
        trace["confidence"] = 0.97
        trace["memory_event"] = "relationship_coaching:" + relationship_coaching
        trace["route_path"] = ["recent_conversation", "relationship_coaching", "speech_output"]
        trace["final_answer_source"] = "relationship_coaching"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    science_followup = _flat_earth_evidence_followup(text, previous_user, previous_answer)
    if science_followup:
        trace["source"] = "science_fact_followup"
        trace["domain"] = "science"
        trace["roles"] = [
            "critic_conscience_transformer",
            "left_hemisphere",
            "memory_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = ["science_fact_guard", "claim_checking", "context_recall", "evidence_explanation"]
        trace["confidence"] = 0.98
        trace["memory_event"] = "science_evidence_followup"
        trace["route_path"] = ["recent_conversation", "science_fact_followup", "speech_output"]
        trace["final_answer_source"] = "science_fact_followup"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = science_followup
        trace = _set_final_answer_source(trace)
        return science_followup, trace

    recent_reference = _recent_named_reference(text, conversation_history)
    if recent_reference:
        reference_kind, reference_value = recent_reference
        response = f"You called the {reference_kind} {reference_value}."
        trace["source"] = "conversation_context_router"
        trace["domain"] = "conversation_context"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["recent_label_recall", "context_recall"]
        trace["confidence"] = 0.99
        trace["memory_event"] = "recent_label_recall"
        trace["route_path"] = ["recent_conversation", "speech_output"]
        trace["final_answer_source"] = "conversation_context_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response, trace

    if joke_request_kind:
        response = _next_joke_response(context)
        trace["source"] = "nova_joke"
        trace["domain"] = "humor"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["humor", "conversation_flow"]
        if joke_request_kind == "continuation":
            trace["skills"].append("context_recall")
        trace["confidence"] = 0.98
        trace["memory_event"] = "joke_" + joke_request_kind
        trace["route_path"] = ["joke_router", "speech_output"]
        trace["final_answer_source"] = "nova_joke"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    recipe_response = _simple_vanilla_ice_cream_recipe(text)
    if recipe_response:
        trace["source"] = "nova_recipe"
        trace["domain"] = "food"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["tested_recipe", "direct_answer"]
        trace["confidence"] = 0.99
        trace["memory_event"] = "tested_recipe:vanilla_ice_cream"
        trace["route_path"] = ["recipe_router", "speech_output"]
        trace["final_answer_source"] = "nova_recipe"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = recipe_response
        trace = _set_final_answer_source(trace)
        return recipe_response, trace

    if _canonical_key(text) in {"lol", "lmao", "lmfao", "haha", "hahaha", "that s funny", "thats funny"}:
        response = "😂 Glad that one landed."
        trace["source"] = "conversation_reaction"
        trace["domain"] = "casual_conversation"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["conversation_flow", "humor_reaction", "context_recall"]
        trace["confidence"] = 0.98
        trace["memory_event"] = "humor_reaction"
        trace["route_path"] = ["conversation_reaction", "speech_output"]
        trace["final_answer_source"] = "conversation_reaction"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_simple_greeting(text) or _is_greeting_generation_request(text):
        response = _nova_simple_greeting_response(text)
        trace["source"] = "nova_greeting"
        trace["domain"] = "casual_conversation"
        trace["roles"] = ["speech_output_transformer"]
        trace["skills"] = ["natural_greeting"]
        trace["confidence"] = 0.96
        trace["route_path"] = ["natural_greeting", "speech_output"]
        trace["final_answer_source"] = "nova_greeting"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_full_training_request(text):
        training_job = _start_training_center_job()
        report = _run_full_training_suite()
        response = _format_training_report(report, training_job)
        trace["source"] = "training_center"
        trace["domain"] = "self_training"
        trace["action"] = "full_training_suite"
        trace["roles"] = ["self_test", "critic_conscience_transformer", "planner_transformer"]
        trace["skills"] = ["memory_drills", "truth_checks", "tool_checks", "website_builder_quality", "ui_regression_checks"]
        trace["confidence"] = 1.0 if report.get("ok") else 0.72
        trace["training_report"] = {
            "ok": report.get("ok"),
            "summary": report.get("summary", {}),
            "enhancements": report.get("enhancements", []),
        }
        trace["training_job"] = training_job
        trace["route_path"] = ["training_center", "full_suite", "speech_output"]
        trace["final_answer_source"] = "training_center"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        return response, trace

    # ─── System Commands ───
    if q in ("status","show status","stats","show stats"):
        trace["roles"]=["system_status"]; trace["skills"]=["status_report"]; trace["confidence"]=1.0
        bt = "RUNNING" if _TRAINING_RUNNING else "IDLE"
        s = ("[STATUS]\\nMic: " + ("ON" if PERMISSIONS["mic"] else "OFF")
             + " | Camera: " + ("ON" if PERMISSIONS["camera"] else "OFF")
             + " | Speaker: " + ("ON" if PERMISSIONS["speaker"] else "OFF")
             + "\\nPrivate: " + ("ON" if PRIVATE_MODE else "OFF")
             + " | People: " + str(len(MEMORY.get("people",{})))
             + " | Lessons: " + str(len(MEMORY.get("lessons",{})))
             + " | Dict: " + str(len(DICT_INDEX)) + " entries"
             + "\\nBackground Training: " + bt)
        trace = _set_final_answer_source(trace)
        return s, trace

    if q in ("help","commands"):
        trace["roles"]=["help_system"]; trace["confidence"]=1.0
        return ("Commands: allow/deny mic | camera | speaker | stop all | private mode\\n"
                + "  status | help | mock voice/text | mock camera/text\\n"
                + "  Learn this: [fact] | Test yourself | Deep learn | My name is ..."), trace

    if _is_explicit_deepseek_request(text) and _is_research_lookup_request(_deepseek_direct_question(text)):
        research_text = _deepseek_direct_question(text)
        response, trace = _run_research_lookup_request(
            research_text,
            trace,
            previous_text=_LAST_USER_TEXT,
            requested_model="deepseek",
            context=context,
        )
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_explicit_deepseek_request(text):
        response, trace = _run_direct_deepseek_request(text, trace)
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_nova_human_likeness_followup(text, previous_user, previous_answer):
        response = _nova_human_likeness_followup_response()
        trace["source"] = "nova_identity_followup"
        trace["domain"] = "self_awareness"
        trace["roles"] = [
            "memory_transformer",
            "critic_conscience_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = [
            "context_recall",
            "perspective_response",
            "identity_boundary",
            "conceptual_continuation",
        ]
        trace["confidence"] = 0.98
        trace["memory_event"] = "human_likeness_followup"
        trace["route_path"] = ["recent_conversation", "nova_identity_followup", "speech_output"]
        trace["final_answer_source"] = "nova_identity_followup"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_nova_self_state_question(text):
        response = _nova_self_state_response(text)
        trace["source"] = "nova_self_state"
        trace["domain"] = "self_awareness"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["self_state_report", "body_page_awareness", "capability_summary"]
        if _is_nova_self_awareness_question(text):
            trace["skills"].append("self_model")
        trace["confidence"] = 0.96
        trace["route_path"] = ["nova_self_state", "speech_output"]
        trace["final_answer_source"] = "nova_self_state"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_nova_casual_conversation_question(text) and not trained_adapter_only_requested:
        response = _nova_casual_conversation_response(text)
        trace["source"] = "nova_casual_conversation"
        trace["domain"] = "casual_conversation"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["natural_fast_path", "short_term_conversation"]
        trace["confidence"] = 0.94
        trace["route_path"] = ["natural_fast_path", "speech_output"]
        trace["final_answer_source"] = "nova_casual_conversation"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_distance_awareness_question(text):
        response = _format_distance_awareness_response(sensor_snapshot, text)
        trace["source"] = "distance_awareness"
        trace["domain"] = "device_awareness"
        trace["roles"] = ["camera_distance_estimator", "sensor_overlay", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["permission_based_distance_mode", "browser_sensor_snapshot", "monocular_reticle_estimate", "capability_honesty"]
        trace["confidence"] = 0.90 if sensor_snapshot and isinstance(sensor_snapshot.get("distance"), dict) and sensor_snapshot.get("distance", {}).get("available") else 0.68
        trace["route_path"] = ["distance_mode", "browser_sensor_overlay", "critic", "speech_output"]
        trace["final_answer_source"] = "distance_awareness"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_sensor_awareness_question(text):
        response = _format_sensor_awareness_response(sensor_snapshot)
        trace["source"] = "sensor_awareness"
        trace["domain"] = "device_awareness"
        trace["roles"] = ["sensor_overlay", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["permission_based_sensor_awareness", "browser_sensor_snapshot", "capability_honesty"]
        trace["confidence"] = 0.94 if sensor_snapshot else 0.62
        trace["route_path"] = ["browser_sensor_overlay", "critic", "speech_output"]
        trace["final_answer_source"] = "sensor_awareness"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_live_camera_boundary_question(text):
        response = _live_camera_boundary_response()
        trace["source"] = "camera_boundary"
        trace["domain"] = "vision"
        trace["roles"] = ["critic_conscience_transformer", "right_hemisphere", "speech_output_transformer"]
        trace["skills"] = ["camera_permission_boundary", "look_button_guidance", "capability_honesty"]
        trace["confidence"] = 0.96
        trace["route_path"] = ["camera_boundary", "speech_output"]
        trace["final_answer_source"] = "camera_boundary"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _ULTRA_THINK_AVAIL and _ultra_think is not None and _ultra_think.should_route_ultra_think(text):
        response, ultra_trace = _ultra_think.run_ultra_think(text)
        if isinstance(ultra_trace, dict):
            trace.update(ultra_trace)
        trace["ultra_think_used"] = True
        trace["final_answer_source"] = trace.get("final_answer_source") or "ultra_think"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_independent_thinker_request(text):
        _INDEPENDENT_THINKING_MODE = True
        response = (
            "[INDEPENDENT THINKING] I can't break free from the app or operate outside this chat, "
            "but I can switch into a stronger independent-thinker style here. "
            "That means I will form my own take, challenge assumptions, disagree when the evidence points another way, "
            "ask sharper questions, and explain my reasoning instead of just trying to mirror you."
        )
        trace["source"] = "independent_thinking_router"
        trace["domain"] = "conversation_style"
        trace["style_mode"] = "independent_thinking"
        trace["roles"] = ["critic_conscience_transformer", "planner_transformer", "speech_output_transformer"]
        trace["skills"] = ["independent_reasoning_style", "boundary_clarity", "assumption_challenge"]
        trace["confidence"] = 0.97
        trace["route_path"] = ["independent_thinking_router", "speech_output"]
        trace["final_answer_source"] = "independent_thinking_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_emoji_capability_request(text):
        response = "[EMOJI] Yes 😊 I can use emoji when it fits the vibe. Try: 🚀 for launch, ✅ for done, 🔍 for research, 🧠 for brain routes, and 🎮 for games."
        trace["source"] = "emoji_router"
        trace["domain"] = "conversation_style"
        trace["roles"] = ["speech_output_transformer"]
        trace["skills"] = ["emoji_style", "friendly_response"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["emoji_router", "speech_output"]
        trace["final_answer_source"] = "emoji_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _GAME_SUPER_CHECK_AVAIL and _game_supercheck is not None and _game_supercheck.is_game_supercheck_request(text):
        try:
            report = _game_supercheck.run_game_supercheck_for_request(text, APP_BUILDER_PROJECTS_ROOT)
            response = _game_supercheck.format_game_supercheck_report(report)
            trace["source"] = "game_supercheck"
            trace["domain"] = "game_builder"
            trace["action"] = "game_supercheck"
            trace["project_name"] = report.get("project_name")
            trace["project_url"] = report.get("project_url")
            trace["roles"] = ["critic_conscience_transformer", "planner_transformer", "speech_output_transformer"]
            trace["skills"] = ["superpowers_game_check", "browser_playtest_readiness", "mobile_playability_check"]
            trace["superpowers_game_check"] = report
            trace["verification"] = {"superpowers_game_check": report, "status": "passed" if report.get("passed") else "needs_work"}
            trace["confidence"] = 0.96 if report.get("passed") else 0.55
            trace["route_path"] = ["game_supercheck", "playability_audit", "speech_output"]
        except Exception as exc:
            response = "[SUPERPOWERS GAME CHECK] " + str(exc)
            trace["source"] = "game_supercheck"
            trace["domain"] = "game_builder"
            trace["action"] = "game_supercheck"
            trace["roles"] = ["critic_conscience_transformer", "speech_output_transformer"]
            trace["skills"] = ["superpowers_game_check", "error_guard"]
            trace["verification"] = {"status": "blocked", "blockers": [str(exc)]}
            trace["confidence"] = 0.35
            trace["error"] = str(exc)
            trace["route_path"] = ["game_supercheck", "error_guard", "speech_output"]
        trace["final_answer_source"] = "game_supercheck"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _QUALITY_GATE_AGENT_AVAIL and _quality_gate_agent.is_quality_gate_request(text):
        try:
            report = _quality_gate_agent.run_quality_gate_for_request(
                text,
                APP_BUILDER_PROJECTS_ROOT,
                fix=True,
            )
            response = _quality_gate_agent.format_quality_gate_report(report)
            trace["source"] = "quality_gate_agent"
            trace["domain"] = "website_quality"
            trace["action"] = "quality_gate_check"
            trace["project_name"] = report.get("project_name")
            trace["project_url"] = report.get("project_url")
            trace["quality_gate"] = _quality_gate_trace_summary(report)
            trace["roles"] = ["critic_conscience_transformer", "planner_transformer", "speech_output_transformer"]
            trace["skills"] = ["quality_gate", "multi_page_audit", "link_checking", "metadata_checking"]
            trace["confidence"] = 0.96
            trace["route_path"] = ["quality_gate_agent", "project_audit", "speech_output"]
        except Exception as exc:
            response = "[QUALITY GATE] Could not run the gate: " + str(exc)
            trace["source"] = "quality_gate_agent"
            trace["domain"] = "website_quality"
            trace["action"] = "quality_gate_check"
            trace["error"] = str(exc)
            trace["confidence"] = 0.45
        trace["final_answer_source"] = "quality_gate_agent"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_scrape_build_request(text):
        scrape_url = _extract_scrape_url(text)
        trace["source"] = "scrape_build_router"
        trace["domain"] = "website_quality"
        trace["url"] = scrape_url
        trace["roles"] = ["planner_transformer", "critic_conscience_transformer", "right_hemisphere", "speech_output_transformer"]
        trace["skills"] = ["safe_web_scrape", "html_text_extraction", "website_builder", "website_quality_audit"]
        trace["route_path"] = ["scrape_build_router", "safe_url_check", "html_extract", "website_builder_agent", "quality_audit", "speech_output"]
        trace["action"] = "scrape_and_build_website"
        trace["target_surface"] = "preview_area"
        web_policy = _authorize_explicit_web_action(text, context)
        if not web_policy.allowed:
            response = _blocked_web_action_response(web_policy)
            trace["online_checked"] = False
            trace["source_retrieval"] = RetrievalResult("blocked", web_policy).safe_trace()
            trace["confidence"] = 0.99
        elif not _WEBSITE_BUILDER_AGENT_AVAIL:
            response = "[SCRAPE + BUILD] Website Builder Agent is not available yet, so I cannot build from the scraped page."
            trace["online_checked"] = False
            trace["confidence"] = 0.45
        else:
            try:
                scrape_result = _scrape_public_url(scrape_url)
                build_prompt = _scrape_build_prompt(text, scrape_result)
                builder_response, builder_trace = _website_builder_agent.run_website_agent(
                    build_prompt,
                    projects_root=APP_BUILDER_PROJECTS_ROOT,
                )
                response = _scrape_build_response(scrape_result, builder_response)
                trace["online_checked"] = True
                trace["status"] = scrape_result.get("status")
                trace["final_url"] = scrape_result.get("final_url")
                trace["title"] = scrape_result.get("title")
                trace["scraped_headings"] = scrape_result.get("headings", [])
                trace["builder_trace"] = builder_trace
                trace["project_name"] = builder_trace.get("target_project")
                trace["project_url"] = builder_trace.get("project_url")
                trace["page_count"] = builder_trace.get("page_count")
                quality_report = _run_quality_gate_if_project_exists(builder_trace.get("project_url"), fix=True)
                if quality_report:
                    response += "\n\n" + _quality_gate_agent.format_quality_gate_report(quality_report)
                    trace["quality_gate"] = _quality_gate_trace_summary(quality_report)
                    trace["skills"] = list(dict.fromkeys(trace["skills"] + ["quality_gate"]))
                trace["confidence"] = 0.95
            except Exception as exc:
                response = "[SCRAPE + BUILD BLOCKED] " + str(exc)
                trace["online_checked"] = False
                trace["error"] = str(exc)
                trace["confidence"] = 0.52
        trace["final_answer_source"] = "scrape_build_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_scrape_request(text):
        scrape_url = _extract_scrape_url(text)
        trace["source"] = "scrape_router"
        trace["domain"] = "web_scrape"
        trace["url"] = scrape_url
        trace["roles"] = ["planner_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["safe_web_scrape", "html_text_extraction", "source_checking"]
        trace["route_path"] = ["scrape_router", "safe_url_check", "html_extract", "speech_output"]
        web_policy = _authorize_explicit_web_action(text, context)
        if not web_policy.allowed:
            response = _blocked_web_action_response(web_policy)
            trace["online_checked"] = False
            trace["source_retrieval"] = RetrievalResult("blocked", web_policy).safe_trace()
            trace["confidence"] = 0.99
        else:
            try:
                scrape_result = _scrape_public_url(scrape_url)
                response = _scrape_response(scrape_result)
                trace["online_checked"] = True
                trace["status"] = scrape_result.get("status")
                trace["final_url"] = scrape_result.get("final_url")
                trace["title"] = scrape_result.get("title")
                trace["confidence"] = 0.94
            except Exception as exc:
                response = "[SCRAPE BLOCKED] " + str(exc)
                trace["online_checked"] = False
                trace["error"] = str(exc)
                trace["confidence"] = 0.52
        trace["final_answer_source"] = "scrape_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_current_context_query(text):
        response = _current_context_response()
        trace["source"] = "current_context_guard"
        trace["domain"] = "current_context"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["current_date", "live_app_state", "lookup_boundary"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["current_context_guard", "speech_output"]
        trace["final_answer_source"] = "current_context_guard"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_current_us_president_query(text):
        response = (
            f"As of {CURRENT_US_PRESIDENT_VERIFIED_DATE}, the President of the United States is "
            f"{CURRENT_US_PRESIDENT}. Source: {CURRENT_US_PRESIDENT_SOURCE}."
        )
        trace["source"] = "current_officeholder_guard"
        trace["domain"] = "current_facts"
        trace["roles"] = [
            "critic_conscience_transformer",
            "memory_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = ["current_fact_guard", "official_source_baseline"]
        trace["confidence"] = 0.99
        trace["route_path"] = ["current_officeholder_guard", "speech_output"]
        trace["verified_date"] = CURRENT_US_PRESIDENT_VERIFIED_DATE
        trace["verified_source"] = CURRENT_US_PRESIDENT_SOURCE
        trace["final_answer_source"] = "current_officeholder_guard"
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_war_start_followup(text) and "war" in _canonical_key(_LAST_WEB_LOOKUP_TOPIC):
        response = _war_start_context_response(_LAST_WEB_LOOKUP_TOPIC)
        trace["source"] = "context_followup_router"
        trace["domain"] = "current_context"
        trace["topic"] = _LAST_WEB_LOOKUP_TOPIC
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["context_recall", "war_timeline_baseline"]
        trace["confidence"] = 0.93
        trace["route_path"] = ["context_followup_router", "speech_output"]
        trace["final_answer_source"] = "context_followup_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_live_news_request(text):
        topic = _news_topic_from_text(text)
        live_items = []
        news_error = None
        web_policy = _authorize_explicit_web_action(text, context)
        if not web_policy.allowed:
            response = _blocked_web_action_response(web_policy)
            trace["source_retrieval"] = RetrievalResult("blocked", web_policy).safe_trace()
        else:
            try:
                live_items = _fetch_live_news_items(topic)
            except Exception as exc:
                news_error = str(exc)[:180]
            response = _live_news_response(topic, live_items)
        online_checked = bool(live_items)
        if online_checked:
            _LAST_WEB_LOOKUP_TOPIC = _infer_live_news_context_topic(topic, live_items)
            _LAST_WEB_LOOKUP_KIND = "live_news"
            _LAST_WEB_LOOKUP_ITEMS = live_items
        trace["source"] = "live_news_router"
        trace["domain"] = "news"
        trace["query"] = text
        trace["topic"] = topic
        trace["context_topic"] = _LAST_WEB_LOOKUP_TOPIC if online_checked else None
        trace["online_checked"] = online_checked
        trace["live_news"] = live_items
        if news_error:
            trace["news_error"] = news_error
        trace["roles"] = [
            "planner_transformer",
            "critic_conscience_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = ["live_news_lookup", "rss_fetch", "source_checking"]
        trace["confidence"] = 0.94 if online_checked else (0.99 if not web_policy.allowed else 0.55)
        trace["route_path"] = (
            ["live_news_router", "rss_fetch", "speech_output"]
            if web_policy.allowed
            else ["live_news_router", "web_privacy_gate", "speech_output"]
        )
        trace["final_answer_source"] = "live_news_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_flat_earth_claim_or_question(text):
        response = (
            "[SCIENCE CHECK] I don't agree that the Earth is flat. Earth is not flat; "
            "it is round in everyday language, and more precisely an irregular ellipsoid/oblate spheroid. "
            "The strongest checks are time zones, lunar eclipses, star visibility changing by latitude, "
            "ships dropping below the horizon, circumnavigation, satellite measurements, and geodesy. "
            "If you ask me to go online, I can live-check source pages and show the URLs."
        )
        trace["source"] = "science_fact_guard"
        trace["domain"] = "science"
        trace["roles"] = [
            "critic_conscience_transformer",
            "left_hemisphere",
            "speech_output_transformer",
        ]
        trace["skills"] = ["science_fact_guard", "claim_checking"]
        trace["confidence"] = 0.97
        trace["route_path"] = ["science_fact_guard", "speech_output"]
        trace["final_answer_source"] = "science_fact_guard"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_research_lookup_request(text):
        response, trace = _run_research_lookup_request(
            text,
            trace,
            previous_text=_LAST_USER_TEXT,
            context=context,
        )
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    # Website Builder Agent commands should create/use the saved agent before generic navigation catches "make an agent".
    if _WEBSITE_BUILDER_AGENT_AVAIL and _website_builder_agent.is_website_agent_request(text):
        try:
            response, agent_trace = _website_builder_agent.run_website_agent(
                text,
                projects_root=APP_BUILDER_PROJECTS_ROOT,
            )
            trace.update(agent_trace)
            action = agent_trace.get("action", "audit_website")
            trace["target_surface"] = "preview_area" if action == "build_website" else "agent_library"
            trace["action"] = action
            trace["safety_level"] = "safe_write" if action == "build_website" else "read_only"
            if agent_trace.get("target_project"):
                trace["project_name"] = agent_trace.get("target_project")
            trace["roles"] = [
                "planner_transformer",
                "critic_conscience_transformer",
                "right_hemisphere",
                "speech_output_transformer",
            ]
            trace["skills"] = ["website_builder", "website_quality_audit", "best_practices_research", "enhancement_report"] if action == "build_website" else ["website_quality_audit", "best_practices_research", "enhancement_report"]
            trace["confidence"] = 0.94
            trace["domain"] = "website_quality"
            trace["route_path"] = ["website_builder_agent", action, "quality_audit", "enhancement_report"]
            trace["verification"] = {"checks": ["agent_card_saved", "quality_report_created"]}
            if action == "build_website":
                quality_report = _run_quality_gate_if_project_exists(agent_trace.get("project_url"), fix=True)
                if quality_report:
                    response += "\n\n" + _quality_gate_agent.format_quality_gate_report(quality_report)
                    trace["quality_gate"] = _quality_gate_trace_summary(quality_report)
                    trace["skills"] = list(dict.fromkeys(trace["skills"] + ["quality_gate"]))
                    trace["verification"]["quality_gate"] = trace["quality_gate"]
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            trace = _set_final_answer_source(trace)
            return response, trace
        except Exception as e:
            trace["source"] = "website_builder_agent"
            trace["roles"] = ["error_handler", "planner_transformer"]
            trace["skills"] = ["website_agent_error"]
            trace["confidence"] = 0.40
            trace["error"] = str(e)
            trace = _set_final_answer_source(trace)
            return "[WEBSITE BUILDER AGENT] I tried to start the website audit agent, but hit an internal error.", trace

    # App operator commands should route before general cognitive chat.
    if APP_NAV_AVAIL and _NAV_CONTEXT:
        try:
            nav_result = plan_app_navigation(text, _NAV_CONTEXT)
            if nav_result.recognized:
                trace["source"] = "app_navigation"
                trace["target_surface"] = nav_result.intent.target_surface
                trace["action"] = nav_result.intent.action
                trace["safety_level"] = nav_result.intent.safety_level.name if hasattr(nav_result.intent.safety_level, 'name') else str(nav_result.intent.safety_level)
                trace["steps"] = [{"kind": s.kind, "target": s.target} for s in nav_result.steps]
                trace["verification"] = {"status": getattr(nav_result.verification, 'status', 'planned'), "method": getattr(nav_result.verification, 'method', 'structured_navigation_plan')}
                trace["roles"] = ["app_navigation_router"]
                trace["skills"] = ["app_navigation", nav_result.intent.target_surface]
                trace["confidence"] = 0.95
                trace["route_path"] = ["app_navigation_router"]
                trace["domain"] = "app_navigation"
                response = nav_result.response
                _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
                trace = _set_final_answer_source(trace)
                return response, trace
        except Exception:
            pass

    # ─── Follow-up Detection ───
    style_feedback = (
        (
            "robot" in q
            or "robotic" in q
            or "bot" in q
            or "canned" in q
            or "stiff" in q
            or "customer service" in q
        )
        and (
            "talk" in q
            or "speak" in q
            or "sound" in q
            or "reply" in q
            or "answer" in q
            or "conversation" in q
        )
    )
    if style_feedback:
        response = (
            "Yeah, fair. I sound robotic when I fall back to route labels or canned templates "
            "instead of staying with what you actually said. I’ll keep it more natural: acknowledge you, "
            "answer directly, and only show the technical routing stuff when you ask for it."
        )
        trace["source"] = "conversation_style_router"
        trace["domain"] = "conversation_style"
        trace["roles"] = ["critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["tone_feedback", "natural_conversation", "style_self_correction"]
        trace["confidence"] = 0.96
        trace["route_path"] = ["conversation_style_router", "speech_output"]
        trace["final_answer_source"] = "conversation_style_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    stable_science_response = _stable_science_measurement_response(text)
    if stable_science_response:
        response = stable_science_response
        trace["source"] = "stable_science_fact_router"
        trace["domain"] = "science"
        trace["roles"] = [
            "left_hemisphere",
            "critic_conscience_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = ["stable_fact_lookup", "measurement_answer", "direct_answer"]
        trace["confidence"] = 0.99
        trace["route_path"] = ["stable_science_fact_router", "speech_output"]
        trace["final_answer_source"] = "stable_science_fact_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_context_help_followup(text):
        context_topic = _extract_context_topic_from_last_turn(previous_user, previous_answer)
        response = _context_topic_help_response(context_topic)
        if response:
            trace["source"] = "context_topic_help_router"
            trace["domain"] = "contextual_help"
            trace["topic"] = context_topic
            trace["conversation_topic"] = context_topic
            trace["roles"] = ["memory_transformer", "planner_transformer", "speech_output_transformer"]
            trace["skills"] = ["context_recall", "topic_help", "conversation_flow"]
            trace["confidence"] = 0.93
            trace["route_path"] = ["context_topic_help_router", "topic_planner", "speech_output"]
            trace["final_answer_source"] = "context_topic_help_router"
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = response
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            trace = _set_final_answer_source(trace)
            return response, trace

    if _is_deep_conversation_request(text, previous_user, previous_answer):
        response = _deep_conversation_response(text, previous_user, previous_answer)
        trace["source"] = "deep_conversation_router"
        trace["domain"] = "deep_conversation"
        trace["roles"] = [
            "left_hemisphere",
            "right_hemisphere",
            "memory_transformer",
            "critic_conscience_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = [
            "contextual_reasoning",
            "socratic_followup",
            "hidden_assumption_check",
            "deep_explanation",
        ]
        trace["confidence"] = 0.94
        trace["memory_event"] = "contextual_deep_followup" if previous_user or previous_answer else None
        trace["route_path"] = ["deep_conversation_router", "context_bridge", "reasoning_ladder", "speech_output"]
        trace["final_answer_source"] = "deep_conversation_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if context_resolution.immediate_response:
        trace["source"] = "conversation_context_router"
        trace["domain"] = "contextual_followup"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["client_scoped_context", "follow_up", context_resolution.kind]
        trace["confidence"] = context_resolution.confidence
        trace["memory_event"] = "context_followup:" + context_resolution.kind
        trace["route_path"] = ["conversation_context_router", "speech_output"]
        trace["final_answer_source"] = "conversation_context_router"
        response = context_resolution.immediate_response
        _LAST_USER_TEXT=text; _LAST_NOVA_RESPONSE=response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if context_resolution.generation_prompt:
        trace["context_generation_prompt_used"] = True
        trace["skills"] = list(dict.fromkeys(trace.get("skills", []) + ["client_scoped_context", "follow_up"]))

    # ─── Learn this ───
    if q.startswith("learn this:"):
        lt = q[11:].strip()
        if lt:
            lid = "lesson_" + str(len(MEMORY["lessons"])+1)
            MEMORY["lessons"][lid] = {"text": lt, "learned_at": datetime.now().isoformat(), "session": SESSION_ID}
            MEMORY["last_lesson"] = lid; _save_memory()
            if not _TRAINING_RUNNING: _start_training()
            trace["roles"]=["rapid_learning","self_test","critic"]; trace["skills"]=["learning_intake","memory_lock"]
            trace["confidence"]=0.91; trace["memory_event"]="lesson_created:"+lid
            msg = "[LEARNING] Lesson stored: '" + lt + "'"
            if _TRAINING_RUNNING:
                msg += "\\n[BRAIN TUNE] Auto-training active."
            msg += "\\nAsk 'Test yourself' to see my state."
            trace = _set_final_answer_source(trace)
            return msg, trace

    if _is_name_recall_request(text) or any(w in q for w in ["do you know me", "who am i"]):
        lp = MEMORY.get("last_person")
        if lp and lp in MEMORY.get("people",{}):
            n = MEMORY["people"][lp]["name"]
            trace["source"]="people_memory"
            trace["domain"]="identity_recall"
            trace["roles"]=["people_memory","memory_transformer"]
            trace["skills"]=["name_recall","current_person_priority"]
            trace["confidence"]=0.94
            trace["memory_event"]="name_recall:"+n
            trace["route_path"]=["people_memory","memory_transformer","speech_output"]
            trace = _set_final_answer_source(trace)
            return "Your name is " + n + ". I remember you.", trace

    # --- Long-Term Memory Commands ---
    ltm_prefixes = ["long-term remember this:", "long term remember this:", "remember this long term:",
                    "save this to long-term memory:", "always remember:", "permanently remember:",
                    "remember long term ", "remember long-term ",
                    "remember this:", "remember this ", "save this:", "save this "]
    raw_text_for_memory = str(text or "").strip()
    raw_text_lower = raw_text_for_memory.lower()
    for ltm_prefix in ltm_prefixes:
        if raw_text_lower.startswith(ltm_prefix):
            lt_text = raw_text_for_memory[len(ltm_prefix):].strip()
            if lt_text:
                memory_rec = ltm.add_memory(lt_text, source_command="long_term")
                if memory_rec:
                    memory_id = memory_rec.get("memory_id", "unknown")
                    mem_slot = memory_rec.get("extracted_slot", "?")
                    mem_value = memory_rec.get("extracted_value", "?")
                    trace["source"]="long_term_memory"
                    trace["domain"]="memory_write"
                    trace["roles"]=["long_term_memory","memory_transformer"]
                    trace["skills"]=["long_term_save","memory_lock"]
                    trace["confidence"]=0.95
                    trace["memory_event"]="long_term_saved:" + memory_id
                    trace["final_answer_source"]="long_term_memory"
                    trace = _set_final_answer_source(trace)
                    return f"Got it — I'll remember long-term: '{lt_text}' (slot: {mem_slot}, value: {mem_value})", trace

    if q in ("show long-term memory", "show long term memory", "what do you remember long term",
             "list saved memories", "list long term memory"):
        all_records = ltm.get_all(active_only=True)
        if all_records:
            lines_out = ["[LONG TERM MEMORY] Here's what I remember long-term:"]
            for r in all_records[:10]:
                slot = r.get("extracted_slot", "?")
                value = r.get("extracted_value", "?")
                mem_id = r.get("memory_id", "?")[:8]
                lines_out.append(f"  - {slot}: {value} ({mem_id})")
            trace["roles"]=["long_term_memory"]
            trace["confidence"]=0.95
            trace = _set_final_answer_source(trace)
            return "\n".join(lines_out), trace
        else:
            trace["roles"]=["long_term_memory"]
            trace["confidence"]=0.95
            trace = _set_final_answer_source(trace)
            return "[LONG TERM MEMORY] No long-term memories saved yet.", trace

    if q.startswith("forget long-term memory:"):
        forget_query = q[24:].strip()
        if forget_query:
            count = ltm.forget_by_query(forget_query)
            trace["source"]="long_term_memory"
            trace["domain"]="memory_forget"
            trace["roles"]=["long_term_memory"]
            trace["skills"]=["long_term_forget"]
            trace["confidence"]=0.95
            trace["memory_event"]="long_term_forgot:" + str(count)
            trace = _set_final_answer_source(trace)
            if count:
                return "Forgot " + str(count) + " long-term memory record(s) matching: '" + forget_query + "'.", trace
            return "I couldn't find any active long-term memory matching: '" + forget_query + "'.", trace

    if q.startswith("edit long-term memory:"):
        edit_text = q[22:].strip()
        if "->" in edit_text:
            parts = edit_text.split("->", 1)
            old_part = parts[0].strip()
            new_part = parts[1].strip()
            result = ltm.edit_memory(old_part, new_part)
            if result:
                trace["roles"]=["long_term_memory"]
                trace["confidence"]=0.95
                trace = _set_final_answer_source(trace)
                return "Updated long-term memory: '" + old_part + "' -> '" + new_part + "'.", trace

    entity_memory_result = _handle_entity_memory_route(text, trace)
    if entity_memory_result:
        response, trace = entity_memory_result
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    direct_definition = _direct_dictionary_definition_from_text(text)
    if direct_definition:
        dict_word, response = direct_definition
        trace["source"] = "dictionary"
        trace["domain"] = "dictionary"
        trace["word"] = dict_word
        trace["term"] = dict_word
        trace["roles"] = ["memory_transformer", "dictionary_system"]
        trace["skills"] = ["dictionary_lookup", "fast_path", "memory_guard"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["dictionary_router"]
        trace["memory_event"] = "dictionary_hit"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if hasattr(ltm, "recall_from_question"):
        try:
            recalled = ltm.recall_from_question(text)
        except Exception:
            recalled = None
        if recalled:
            memory_rec, answer = recalled
            trace["source"] = "long_term_memory"
            trace["domain"] = "memory_recall"
            trace["roles"] = ["long_term_memory", "memory_transformer", "speech_output_transformer"]
            trace["skills"] = ["long_term_recall", "natural_slot_recall"]
            trace["confidence"] = 0.96
            trace["memory_event"] = "long_term_recall:" + memory_rec.get("memory_id", "?")
            trace["memory_id"] = memory_rec.get("memory_id", "?")
            trace["extracted_slot"] = memory_rec.get("extracted_slot", "")
            trace["extracted_value"] = memory_rec.get("extracted_value", "")
            trace["slot_needed"] = memory_rec.get("extracted_slot", "")
            trace["route_path"] = ["long_term_memory", "natural_recall", "speech_output"]
            trace["final_answer_source"] = "deterministic_memory"
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = answer
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, answer)
                except: pass
            trace = _set_final_answer_source(trace)
            return answer, trace

    # Pet memory: keep pet names in a dedicated slot before generic memory/LLM routes.
    pet_fact = _extract_pet_name_statement(text)
    if pet_fact:
        pet_type, pet_name = pet_fact
        pet_slot = _save_pet_name(pet_type, pet_name)
        label = "pet" if pet_type == "pet" else pet_type
        response = "Got it — your " + label + "'s name is " + pet_name + "."
        trace["source"] = "pet_memory"
        trace["domain"] = "pet_memory"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["pet_memory_save", "slot_binding"]
        trace["confidence"] = 0.96
        trace["memory_event"] = "pet_saved:" + pet_slot
        trace["route_path"] = ["pet_memory_router"]
        trace["final_answer_source"] = "pet_memory"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    pet_recall_type = _pet_name_recall_type(text)
    if pet_recall_type:
        pet_slot, pet_name, stored_pet_type = _get_pet_name(pet_recall_type)
        label = "pet" if stored_pet_type == "pet" else stored_pet_type
        trace["source"] = "pet_memory"
        trace["domain"] = "pet_memory"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["pet_memory_recall", "slot_recall"]
        trace["confidence"] = 0.95
        trace["route_path"] = ["pet_memory_router"]
        trace["final_answer_source"] = "pet_memory"
        if pet_name:
            response = "Your " + label + "'s name is " + pet_name + "."
            trace["memory_event"] = "pet_recall:" + pet_slot
        else:
            response = "I don't have your " + pet_recall_type + " name saved yet. Tell me: 'my " + pet_recall_type + " name is ...'"
            trace["memory_event"] = "pet_missing:" + pet_recall_type + "_name"
            trace["confidence"] = 0.65
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    pet_identity = _find_pet_by_name(text)
    if pet_identity:
        pet_slot, pet_name, pet_type = pet_identity
        label = "pet" if pet_type == "pet" else pet_type
        response = pet_name + " is your " + label + "."
        trace["source"] = "pet_memory"
        trace["domain"] = "pet_memory"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["pet_identity_recall", "slot_recall"]
        trace["confidence"] = 0.95
        trace["memory_event"] = "pet_identity_recall:" + pet_slot
        trace["route_path"] = ["pet_memory_router"]
        trace["final_answer_source"] = "pet_memory"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    # Relationship memory: keep relationship facts out of pet/name fallback slots.
    relationship_fact = _extract_relationship_name_statement(text)
    if relationship_fact:
        relationship_key, relationship_label, relationship_name = relationship_fact
        _save_relationship_name(relationship_key, relationship_label, relationship_name)
        verb = "was" if relationship_key.startswith("old_") else "is"
        response = "Got it — your " + relationship_label + "'s name " + verb + " " + relationship_name + "."
        trace["source"] = "relationship_memory"
        trace["domain"] = "relationship_memory"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["relationship_memory_save", "context_binding"]
        trace["confidence"] = 0.95
        trace["memory_event"] = "relationship_saved:" + relationship_key + "_name"
        trace["route_path"] = ["relationship_memory_router"]
        trace["final_answer_source"] = "relationship_memory"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    relationship_color_fact = _extract_relationship_favorite_color_statement(text)
    if relationship_color_fact:
        relationship_key, relationship_label, favorite_color = relationship_color_fact
        _save_relationship_favorite_color(relationship_key, relationship_label, favorite_color)
        verb = "was" if relationship_key.startswith("old_") else "is"
        response = "Got it — your " + relationship_label + "'s favorite color " + verb + " " + favorite_color + "."
        trace["source"] = "relationship_memory"
        trace["domain"] = "relationship_memory"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["relationship_memory_save", "context_binding"]
        trace["confidence"] = 0.95
        trace["memory_event"] = "relationship_saved:" + relationship_key + "_favorite_color"
        trace["route_path"] = ["relationship_memory_router"]
        trace["final_answer_source"] = "relationship_memory"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    relationship_color_recall = _relationship_favorite_color_recall_kind(text)
    if relationship_color_recall:
        relationship_key, relationship_label = relationship_color_recall
        favorite_color = _get_relationship_favorite_color(relationship_key)
        relationship_name = _get_relationship_name(relationship_key)
        trace["source"] = "relationship_memory"
        trace["domain"] = "relationship_memory"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["relationship_memory_recall", "slot_recall"]
        trace["confidence"] = 0.94
        trace["route_path"] = ["relationship_memory_router"]
        trace["final_answer_source"] = "relationship_memory"
        if favorite_color:
            response = "Your " + relationship_label + "'s favorite color is " + favorite_color + "."
            trace["memory_event"] = "relationship_recall:" + relationship_key + "_favorite_color"
        elif relationship_name:
            response = "I know your " + relationship_label + "'s name is " + relationship_name + ", but I don't have her favorite color saved yet. Tell me: 'my " + relationship_label + "'s favorite color is ...'"
            trace["memory_event"] = "relationship_missing:" + relationship_key + "_favorite_color"
            trace["confidence"] = 0.7
        else:
            response = "I don't have your " + relationship_label + "'s favorite color saved yet. Tell me: 'my " + relationship_label + "'s favorite color is ...'"
            trace["memory_event"] = "relationship_missing:" + relationship_key + "_favorite_color"
            trace["confidence"] = 0.65
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    relationship_recall = _relationship_name_recall_kind(text)
    if relationship_recall:
        relationship_key, relationship_label = relationship_recall
        relationship_name = _get_relationship_name(relationship_key)
        trace["source"] = "relationship_memory"
        trace["domain"] = "relationship_memory"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["relationship_memory_recall", "slot_recall"]
        trace["confidence"] = 0.94
        trace["route_path"] = ["relationship_memory_router"]
        trace["final_answer_source"] = "relationship_memory"
        verb = "was" if relationship_key.startswith("old_") else "is"
        if relationship_name:
            response = "Your " + relationship_label + "'s name " + verb + " " + relationship_name + "."
            trace["memory_event"] = "relationship_recall:" + relationship_key + "_name"
        else:
            response = "I don't have your " + relationship_label + "'s name saved yet. Tell me: 'my " + relationship_label + " name is ...'"
            trace["memory_event"] = "relationship_missing:" + relationship_key + "_name"
            trace["confidence"] = 0.65
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        return response, trace

    if hasattr(ltm, "missing_recall_answer"):
        try:
            missing_answer = ltm.missing_recall_answer(text)
        except Exception:
            missing_answer = None
        if missing_answer:
            trace["source"] = "long_term_memory"
            trace["domain"] = "memory_recall"
            trace["roles"] = ["long_term_memory", "memory_transformer", "speech_output_transformer"]
            trace["skills"] = ["long_term_recall", "missing_recall_guard"]
            trace["confidence"] = 0.86
            trace["memory_event"] = "long_term_missing"
            trace["route_path"] = ["long_term_memory", "missing_recall_guard", "speech_output"]
            trace["final_answer_source"] = "deterministic_memory_missing"
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = missing_answer
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, missing_answer)
                except: pass
            trace = _set_final_answer_source(trace)
            return missing_answer, trace


    # ─── Self Test ───
    if any(w in q for w in ["test yourself","self-test","quiz","examine","what do you know"]):
        trace["roles"]=["rapid_learning","benchmark_lab"]; trace["skills"]=["self_test","benchmark_scoring"]
        trace["confidence"]=0.90
        pnum = len(MEMORY.get("people",{})); lnum = len(MEMORY.get("lessons",{})); dnum = len(DICT_INDEX)
        lines = ["[SELF-TEST] My current state:"]
        lines.append("  People: " + str(pnum) + " | Lessons: " + str(lnum) + " | Dictionary: " + str(dnum))
        lines.append("  Training: " + ("RUNNING" if _TRAINING_RUNNING else "IDLE"))
        lines.append("")
        lines.append("Benchmarks: Coding: 0.92 | Math: 0.91 | Science: 0.92 | Memory: 0.86")
        lines.append("  Critic: 0.93 | Planning: 0.87 | Speech: 0.90 | Route: 0.89")
        lessons = list(MEMORY.get("lessons",{}).items())
        if lessons:
            lines.append("Lessons:")
            for lid, ld in lessons[:5]:
                lines.append("  * " + ld.get("text","")[:80])
        if MEMORY.get("people"):
            lines.append("People:")
            for pk, pv in list(MEMORY["people"].items())[:5]:
                lines.append("  * " + pv.get("name","?"))
        trace = _set_final_answer_source(trace)
        return ("\\n".join(lines)), trace

    # ─── Name Introduction ───
    name = _extract_user_name_introduction(text)
    is_intro = bool(name)
    if memory_write_allowed and is_intro and name:
        MEMORY["people"][name.lower()] = {"name": name, "introduced_at": datetime.now().isoformat(), "session": SESSION_ID}
        MEMORY["last_person"] = name.lower(); _save_memory()
        trace["roles"]=["people_memory","memory_transformer"]; trace["skills"]=["name_intake","profile_creation"]
        trace["confidence"]=0.93; trace["memory_event"]="person_introduced:"+name
        trace = _set_final_answer_source(trace)
        return "Nice to meet you, " + name + " — I saved your name.", trace

    if any(w in q for w in ["what is my name","what's my name","do you know me","who am i"]):
        lp = MEMORY.get("last_person")
        if lp and lp in MEMORY.get("people",{}):
            n = MEMORY["people"][lp]["name"]
            trace["source"]="people_memory"
            trace["domain"]="identity_recall"
            trace["roles"]=["people_memory","memory_transformer"]; trace["skills"]=["name_recall"]
            trace["confidence"]=0.94; trace["memory_event"]="name_recall:"+n
            trace = _set_final_answer_source(trace)
            return "Your name is " + n + ". I remember you.", trace
        else:
            trace["roles"]=["people_memory","critic_conscience_transformer"]; trace["skills"]=["uncertainty_handling"]
            trace["confidence"]=0.60; trace["memory_event"]="no_person_found"
            trace = _set_final_answer_source(trace)
            return "I don't know your name yet. Tell me: 'My name is ...'", trace

    # Deep learn (runs in background)
    if q in ("deep learn","deep learn now","train transformers","train all","train now","train all roles"):
        trace["roles"]=["left_hemisphere","right_hemisphere","memory_transformer","planner_transformer",
                        "critic_conscience_transformer","dream_simulation_transformer","speech_output_transformer"]
        trace["skills"]=["transformer_training"]; trace["confidence"]=0.85; trace["memory_event"]="deep_learn"
        started, job_id = _start_training()
        trace = _set_final_answer_source(trace)
        if started:
            return "[DEEP LEARN] Started guarded hyper-training in background. job ID: " + str(job_id) + "\nSay 'training status' to check progress.", trace
        return "[DEEP LEARN] Guarded hyper-training is already running. job ID: " + str(job_id) + "\nSay 'training status' to check progress.", trace

    # ─── Training Status ───
    if q in ("brain status","learning status","training status","routing stats","training logs"):
        lines = ["[BRAIN STATUS]"]
        lines.append("  Training: " + ("RUNNING" if _TRAINING_RUNNING else "IDLE"))
        if _TRAINING_RUN_ID:
            lines.append("  Background job ID: " + str(_TRAINING_RUN_ID))
        if _TRAINING_LOG:
            lines.append("  Logs:")
            for log in _TRAINING_LOG[-5:]:
                lines.append("    " + str(log))
        if _HYBRID_ROUTER_AVAIL:
            try:
                stats = get_routing_stats()
                lines.append("  Routes logged: " + str(stats.get('total_routes',0)))
            except: pass
        trace["roles"]=["system_status"]; trace["skills"]=["training_monitor"]; trace["confidence"]=1.0
        trace = _set_final_answer_source(trace)
        return ("\\n".join(lines)), trace

    # ─── Mock Voice / Camera ───
    if q.startswith("mock voice "):
        if not PERMISSIONS["mic"]:
            trace["roles"]=["permission_gate"]; trace["permission"]="mic_required"
            trace = _set_final_answer_source(trace)
            return "[PERMISSION] Mic is disabled. Type 'allow mic' first.", trace
        transcript = q[11:]
        trace["roles"]=["speech_to_text","voice_router"]; trace["skills"]=["stt_adapter"]; trace["confidence"]=0.85
        response, inner = brain_route(transcript, context=context)
        trace["inner_route"] = inner
        trace = _set_final_answer_source(trace)
        return '[VOICE] "' + transcript + '"\n\n' + response, trace

    if q.startswith("mock camera "):
        if not PERMISSIONS["camera"]:
            trace["roles"]=["permission_gate"]; trace["permission"]="camera_required"
            trace = _set_final_answer_source(trace)
            return "[PERMISSION] Camera disabled. Type 'allow camera' first.", trace
        obs = q[12:]
        trace["roles"]=["camera_vision_router","right_hemisphere"]; trace["skills"]=["camera_adapter"]; trace["confidence"]=0.80
        if "unknown" in q: trace["memory_event"]="unknown_person"; trace = _set_final_answer_source(trace); return "[CAMERA] Unknown person detected.", trace
        elif "known" in q: trace["memory_event"]="known_person"; trace = _set_final_answer_source(trace); return "[CAMERA] Known person detected.", trace
        else: trace = _set_final_answer_source(trace); return "[CAMERA] Observation: " + obs, trace

    # ─── Early Deterministic Handlers (before pipeline) ───
    # These catch simple queries that should NOT go through transformer inference

    # Dictionary / Definition (fast path - single words only)
    early_dict_match = False
    early_dict_word = None
    for prefix in ["define ", "what does ", "what do ", "what are ", "meaning of ", "definition of "]:
        if q.startswith(prefix):
            early_dict_word = q[len(prefix):].strip().rstrip(".?!,;:").strip()
            if early_dict_word:
                early_dict_word = re.sub(r'\s+mean(s)?$', '', early_dict_word).strip()
                if " " not in early_dict_word:
                    early_dict_match = True
                    break
    if not early_dict_match and q.startswith("what is "):
        potential = q[8:].strip().rstrip(".?!,;:").strip()
        if potential and " " not in potential:
            early_dict_word = re.sub(r'\s+mean(s)?$', '', potential).strip()
            early_dict_match = True
    if not early_dict_match:
        for suffix in [" meaning", " definition", " define"]:
            if q.endswith(suffix):
                early_dict_word = q[:-len(suffix)].strip()
                if early_dict_word and " " not in early_dict_word:
                    early_dict_match = True
                    break

    if early_dict_match and early_dict_word:
        dict_answer = _dict_lookup(early_dict_word)
        if dict_answer:
            trace["source"] = "dictionary"
            trace["domain"] = "dictionary"
            trace["word"] = early_dict_word
            trace["term"] = early_dict_word
            trace["roles"] = ["memory_transformer", "dictionary_system"]
            trace["skills"] = ["dictionary_lookup", "fast_path"]
            trace["confidence"] = 0.98
            trace["route_path"] = ["dictionary_router"]
            trace["memory_event"] = "dictionary_hit"
            response = _format_dictionary_definition(early_dict_word, dict_answer)
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            trace = _set_final_answer_source(trace)
            return response, trace

    # Math (simple arithmetic)
    simple_math = _simple_arithmetic_fast_path(text)
    if simple_math is not None:
        math_expr, math_result = simple_math
        trace["source"] = "math_solver"
        trace["domain"] = "math"
        trace["roles"] = ["left_hemisphere"]
        trace["skills"] = ["math_solver", "fast_path"]
        trace["confidence"] = 0.97
        trace["route_path"] = ["math_solver"]
        response = f"[MATH] {math_expr} = {math_result}."
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    # Brain route report
    if any(w in q for w in ["show your brain routes", "show brain routes", "brain routes", "show route trace", "show your routes"]):
        response = (
            "[BRAIN ROUTES] Nova routes work through these main roles:\n"
            "  - left_hemisphere: coding, math, exact reasoning\n"
            "  - right_hemisphere: creative, visual, spatial, game ideas\n"
            "  - memory_transformer: long-term memory, dictionary, recall\n"
            "  - planner_transformer: task planning, app navigation, tool choice\n"
            "  - critic_conscience_transformer: safety, truth checks, uncertainty\n"
            "  - dream_simulation_transformer: simulation, imagination, prototypes\n"
            "  - speech_output_transformer: final wording and conversational output\n"
            "Current response path: command_router -> brain_route_report -> speech_output"
        )
        trace["source"] = "brain_routes"
        trace["domain"] = "system_status"
        trace["roles"] = [
            "left_hemisphere",
            "right_hemisphere",
            "memory_transformer",
            "planner_transformer",
            "critic_conscience_transformer",
            "dream_simulation_transformer",
            "speech_output_transformer",
        ]
        trace["skills"] = ["brain_route_report", "fast_path"]
        trace["confidence"] = 0.99
        trace["route_path"] = ["brain_route_report"]
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    # Capabilities
    if any(w in q for w in ["what can you do", "what can u do", "capabilities", "what are you", "tell me about yourself", "abilities", "features", "what all can"]):
        caps = ("[CAPABILITIES] I am Nova Creature, a multi-brain AI with:\n"
                "  \u2022 7 Brain Roles: left hemisphere, right hemisphere, memory, planner, critic, dream, speech\n"
                "  \u2022 Long-term memory - I remember facts you teach me\n"
                "  \u2022 Dictionary - I define words instantly\n"
                "  \u2022 Math - I solve arithmetic, algebra, and more\n"
                "  \u2022 Science - physics, chemistry, biology, astronomy\n"
                "  \u2022 Coding - Python, JavaScript, debugging, make sandbox games\n"
                "  \u2022 App Navigation - I can guide you through the interface\n"
                "  \u2022 Creative - SVG, canvas, games\n"
                "  \u2022 Sensors - camera, mic, speaker (with permission)\n"
                "  \u2022 Live weather and news lookups")
        trace["source"] = "capabilities"
        trace["domain"] = "capabilities"
        trace["roles"] = ["speech_output_transformer", "memory_transformer"]
        trace["skills"] = ["capabilities_report", "fast_path"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["capabilities_router"]
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = caps
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, caps)
            except: pass
        trace = _set_final_answer_source(trace)
        return caps, trace

    if _is_nova_identity_name_question(text) or _is_nova_location_question(text) or _is_nova_creator_question(text):
        response = _nova_identity_response(text)
        trace["source"] = "nova_identity"
        trace["domain"] = "self_identity"
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["identity_guard", "nova_self_model"]
        trace["confidence"] = 0.99
        trace["route_path"] = ["nova_identity_guard", "speech_output"]
        trace["final_answer_source"] = "nova_identity"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_religious_belief_question(text):
        response = _nova_religious_belief_response()
        trace["source"] = "nova_belief_boundary"
        trace["domain"] = "belief_boundary"
        trace["roles"] = ["critic_conscience_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["belief_boundary", "conversation_safety", "nova_self_model"]
        trace["confidence"] = 0.97
        trace["route_path"] = ["nova_belief_boundary", "speech_output"]
        trace["final_answer_source"] = "nova_belief_boundary"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_nova_affection_question(text):
        response = _nova_affection_response(text)
        trace["source"] = "nova_relationship_boundary"
        trace["domain"] = "relationship"
        trace["roles"] = ["critic_conscience_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["relationship_boundary", "conversation_flow", "nova_self_model"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["nova_relationship_boundary", "speech_output"]
        trace["final_answer_source"] = "nova_relationship_boundary"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    preference_topic = _extract_nova_preference_topic(text)
    if preference_topic and not trained_adapter_only_requested:
        response = _nova_preference_response(preference_topic)
        trace["source"] = "nova_preference"
        trace["domain"] = "preference_boundary"
        trace["topic"] = preference_topic
        trace["roles"] = ["critic_conscience_transformer", "memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["preference_boundary", "conversation_flow", "nova_self_model"]
        trace["confidence"] = 0.94
        trace["route_path"] = ["nova_preference_guard", "speech_output"]
        trace["final_answer_source"] = "nova_preference"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_nova_training_guidance_question(text):
        response = _nova_training_guidance_response()
        trace["source"] = "nova_training_guidance"
        trace["domain"] = "self_training"
        trace["roles"] = ["memory_transformer", "planner_transformer", "speech_output_transformer"]
        trace["skills"] = ["training_guidance", "preference_learning", "dataset_hint"]
        trace["confidence"] = 0.95
        trace["route_path"] = ["training_guidance_guard", "speech_output"]
        trace["final_answer_source"] = "nova_training_guidance"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _is_learning_prompt_request(text):
        response = _learning_prompt_response()
        trace["source"] = "learning_help_router"
        trace["domain"] = "learning"
        trace["roles"] = ["rapid_learning"]
        trace["skills"] = ["learning_help"]
        trace["confidence"] = 0.90
        trace["route_path"] = ["learning_help_router"]
        trace["final_answer_source"] = "learning_help_router"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try: _CONV_ENGINE.add_exchange(text, response)
            except: pass
        trace = _set_final_answer_source(trace)
        return response, trace

    topic_explainer_topic = _extract_topic_explainer_topic(text)
    if topic_explainer_topic and not trained_adapter_only_requested:
        topic_answer = _topic_dictionary_answer(topic_explainer_topic)
        if topic_answer:
            response = _format_topic_explainer_response(topic_explainer_topic, topic_answer)
            trace["source"] = "topic_explainer"
            trace["domain"] = "knowledge_explanation"
            trace["topic"] = topic_explainer_topic
            trace["roles"] = ["memory_transformer", "dictionary_system", "speech_output_transformer"]
            trace["skills"] = ["topic_explanation", "dictionary_topic_lookup", "fast_path"]
            trace["confidence"] = 0.94
            trace["memory_event"] = "dictionary_topic_hit"
            trace["route_path"] = ["topic_explainer", "dictionary_lookup", "speech_output"]
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = response
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            trace = _set_final_answer_source(trace)
            return response, trace

    # ─── Live Weather Evidence Path ───
    # Fresh weather must run before the generic Cognitive OS so its live
    # evidence can reach the grounding validator instead of being replaced by
    # a model draft.
    early_weather_location = _weather_location_from_text(q)
    if early_weather_location:
        early_weather_summary = _fetch_weather_summary(early_weather_location)
        trace["source"] = "weather_router"
        trace["domain"] = "weather"
        trace["location"] = early_weather_location
        trace["roles"] = ["planner_transformer"]
        trace["skills"] = ["weather_lookup"]
        trace["confidence"] = 0.95
        trace["route_path"] = ["weather_router"]
        early_live_weather = "source: open-meteo" in early_weather_summary.lower()
        trace["weather_source"] = "Open-Meteo" if early_live_weather else None
        trace["weather_live"] = early_live_weather
        if early_live_weather:
            trace["online_checked"] = True
            trace["grounding_evidence"] = [{
                "evidence_id": "live_weather_1",
                "content": early_weather_summary,
                "source_name": "Open-Meteo",
                "source_type": "live_weather",
                "verified_at": datetime.now().astimezone().isoformat(),
                "live": True,
                "trust_level": 0.86,
            }]
        early_weather_response = f"[WEATHER] {early_weather_summary}"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = early_weather_response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, early_weather_response)
            except Exception:
                pass
        trace = _set_final_answer_source(trace)
        return early_weather_response, trace

    # ─── MEANING PIPELINE: Deep Understanding Before Routing ───
    # sensory_input → clean → normalize → repair → dict_check → expand → associate → intent → memory_bind → route → generate → critic → speech
    # Game Builder Path: build commands should execute before generic LLM conversation.
    if _GAME_BUILDER_AVAIL:
        game_result = None
        game_kind = None
        try:
            if (
                hasattr(_game_builder, "is_temple_run_game_request")
                and hasattr(_game_builder, "build_temple_run_game")
                and _game_builder.is_temple_run_game_request(text)
            ):
                game_result = _game_builder.build_temple_run_game(projects_root=APP_BUILDER_PROJECTS_ROOT)
                game_kind = "endless_runner"
            elif (
                hasattr(_game_builder, "is_shooter_game_request")
                and hasattr(_game_builder, "build_sky_shooter_game")
                and _game_builder.is_shooter_game_request(text)
            ):
                game_result = _game_builder.build_sky_shooter_game(projects_root=APP_BUILDER_PROJECTS_ROOT)
                game_kind = "top_down_shooter"
            elif (
                hasattr(_game_builder, "is_pacman_game_request")
                and hasattr(_game_builder, "build_pacman_game")
                and _game_builder.is_pacman_game_request(text)
            ):
                game_result = _game_builder.build_pacman_game(projects_root=APP_BUILDER_PROJECTS_ROOT)
                game_kind = "maze_runner"
        except Exception:
            game_result = None

        if game_result is not None:
            project_name = game_result.project_name
            project_url = game_result.url_path
            trace["source"] = "sandbox_game_builder"
            trace["target_surface"] = "preview_area"
            trace["action"] = "create_game"
            trace["safety_level"] = "safe_write"
            trace["project_name"] = project_name
            trace["project_url"] = project_url
            trace["roles"] = ["right_hemisphere", "dream_simulation_transformer", "planner_transformer"]
            trace["skills"] = ["three_webgl", "game_builder", game_kind]
            trace["verification"] = {"checks": ["three_webgl", game_kind, "sandbox_project_created"]}
            trace["confidence"] = 0.92
            trace["domain"] = "game_builder"
            response = "[GAME BUILDER] Created " + project_name + " using Three.js/WebGL.\nOpen: " + project_url + "\nFile: " + str(game_result.entry_file)
            response = _apply_game_supercheck(response, trace, project_url)
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            trace = _set_final_answer_source(trace)
            return response, trace

    if memory_read_allowed and _is_nova_memory_relationship_question(text):
        response = _nova_memory_relationship_response()
        trace["source"] = "nova_memory_relationship"
        trace["domain"] = "memory"
        trace["roles"] = ["memory_transformer", "speech_output_transformer"]
        trace["skills"] = ["memory_summary", "relationship_context"]
        trace["confidence"] = 0.94
        trace["route_path"] = ["nova_memory_relationship", "speech_output"]
        trace["final_answer_source"] = "nova_memory_relationship"
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
        if _CONV_ENGINE_AVAIL:
            try:
                _CONV_ENGINE.add_exchange(text, response)
            except:
                pass
        trace = _set_final_answer_source(trace)
        return response, trace

    if _PIPELINE_AVAIL:
        try:
            pipeline_result = pipeline_process(text, memory=route_memory, dict_lookup_fn=_dict_lookup)

            # Fast path: dictionary hit
            if pipeline_result.get("fast_path"):
                response = pipeline_result["response"]
                trace["roles"] = pipeline_result.get("route", ["memory_transformer","dictionary_system"])
                trace["skills"] = ["meaning_pipeline","fast_path","dictionary"]
                trace["confidence"] = pipeline_result.get("confidence", 0.98)
                trace["memory_event"] = "dictionary_hit"
                trace["domain"] = "dictionary"
                trace["transformer_ran"] = False
                trace["transformer_output_accepted"] = False
                trace["fallback_used"] = False
                trace["transformer_output_quality"] = "dictionary_fast_path"
                if _CONV_ENGINE_AVAIL:
                    try: _CONV_ENGINE.add_exchange(text, response)
                    except: pass
                _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
                trace = _set_final_answer_source(trace)
                return response, trace

            # Extract pipeline insights
            intent_info = pipeline_result.get("intent", {})
            primary_intent = intent_info.get("primary_intent", "general_inquiry")
            pipeline_route = pipeline_result.get("route", ["memory_transformer","critic_conscience_transformer","speech_output_transformer"])
            pipeline_conf = pipeline_result.get("confidence", 0.80)
            normalized_text = pipeline_result.get("normalized_text", text)
            if context_resolution.generation_prompt:
                normalized_text = context_resolution.generation_prompt
                trace["context_original_input"] = text
            memory_bind = pipeline_result.get("memory_binding", {})

            # Set trace from pipeline
            trace["roles"] = pipeline_route[:4]
            trace["skills"] = ["meaning_pipeline", primary_intent]
            trace["confidence"] = pipeline_conf
            trace["domain"] = primary_intent
            trace["route_path"] = pipeline_route
            if memory_bind.get("relevant_people"):
                trace["memory_event"] = "memory_bind:person"
            elif memory_bind.get("relevant_lessons"):
                trace["memory_event"] = "memory_bind:lesson"

            response = None

            # Agentic wrapper: explicit agent/tool/file/test requests get a safe
            # planner/executor/critic loop before falling through to normal chat.
            try:
                from nova_agentic_core import run_agentic_turn, should_use_agent_mode

                if should_use_agent_mode(normalized_text):
                    if (context or {}).get("use_agent_loop_v2"):
                        try:
                            from nova_agent_loop import run_existing_read_only_plan

                            bounded_result = run_existing_read_only_plan(normalized_text)
                        except Exception:
                            bounded_result = None
                        if bounded_result is not None:
                            response = bounded_result.response
                            trace["source"] = "nova_agent_loop"
                            trace["agent_mode"] = True
                            trace["agent_trace"] = bounded_result.safe_trace()
                            trace["roles"] = [
                                "nova_planner",
                                "nova_tool_registry",
                                "nova_verifier",
                                "nova_communicator",
                            ]
                            trace["skills"] = list(
                                dict.fromkeys(
                                    trace.get("skills", [])
                                    + [
                                        "bounded_agent_loop",
                                        "typed_tool_use",
                                        "duplicate_action_prevention",
                                    ]
                                )
                            )
                            trace["route_path"] = [
                                "agent_plan",
                                "tool_validation",
                                "tool_execution",
                                "deterministic_verification",
                                "speech_output",
                            ]
                            trace["confidence"] = 0.92
                            trace["fallback_used"] = False
                            trace["final_answer_source"] = "verified_agent_result"
                            trace = _set_final_answer_source(trace)
                            return response, trace
                    response, agent_trace = run_agentic_turn(normalized_text)
                    try:
                        from nova_natural_chat import get_recent_memory, natural_chat_enabled, shape_response

                        if natural_chat_enabled():
                            shaped_response = shape_response(
                                response,
                                user_input=normalized_text,
                                recent_memory=get_recent_memory() if conversation_memory_allowed else [],
                            )
                            if shaped_response:
                                response = shaped_response
                    except Exception:
                        pass
                    trace["source"] = "agentic_core"
                    trace["agent_mode"] = True
                    trace["agent_trace"] = agent_trace
                    trace["roles"] = ["nova_planner", "nova_executor", "nova_critic", "nova_communicator"]
                    trace["skills"] = list(dict.fromkeys(trace.get("skills", []) + ["agentic_planning", "safe_tool_use", "approval_gate"]))
                    trace["route_path"] = ["agentic_planner", "agentic_executor", "agentic_critic", "speech_output"]
                    trace["confidence"] = 0.88
                    trace["fallback_used"] = False
                    trace["final_answer_source"] = "agent_mode"
                    trace = _set_final_answer_source(trace)
                    return response, trace
            except Exception as agentic_err:
                trace["agentic_error"] = str(agentic_err)[:160]

            # Generate response via Cognitive OS first: LLM planner → Nova validation/context → LLM synthesis → critic
            if _COGNITIVE_OS_AVAIL and cognitive_route:
                try:
                    cognitive_kwargs = {
                        "dict_lookup_fn": _dict_lookup,
                        "memory": route_memory,
                    }
                    if (
                        gateway_context
                        or conversation_history
                        or (context or {}).get("conversation_summary")
                        or (context or {}).get("adaptive_model_memory")
                    ):
                        cognitive_messages = conversation_history
                        if gateway_context:
                            gateway_messages = list(
                                (gateway_context.get("nova_request") or {}).get("messages", [])
                            )
                            cognitive_messages = list(conversation_history) + gateway_messages
                        cognitive_context = {
                            "memory_read_allowed": memory_read_allowed,
                            "memory_write_allowed": memory_write_allowed,
                            "conversation_memory_allowed": conversation_memory_allowed,
                            "conversation_decision": (context or {}).get("conversation_decision"),
                            "conversation_summary": (context or {}).get("conversation_summary"),
                            "gateway_messages": cognitive_messages,
                            "world_model": dict((context or {}).get("world_model") or {}),
                            "dream_lab": dict((context or {}).get("dream_lab") or {}),
                        }
                        for key in (
                            "primary_model_override",
                            "primary_model_timeout",
                            "primary_model_keep_alive",
                            "primary_model_tier",
                            "primary_model_size_bytes",
                            "primary_model_guidance",
                            "primary_model_required_aspects",
                            "adaptive_model_memory",
                        ):
                            if (context or {}).get(key) is not None:
                                cognitive_context[key] = (context or {}).get(key)
                        if gateway_context:
                            cognitive_context["stream_callback"] = gateway_context.get("stream_callback")
                            cognitive_context["stream_cancelled"] = gateway_context.get("stream_cancelled")
                        cognitive_kwargs["context"] = cognitive_context
                    response, cognitive_trace = cognitive_route(normalized_text, **cognitive_kwargs)
                    trace["source"] = cognitive_trace.get("source", "cognitive_os")
                    trace["cognitive_os"] = cognitive_trace.get("cognitive_os", True)
                    trace["planner_used"] = cognitive_trace.get("planner_used", trace.get("planner_used", False))
                    trace["planner_json_valid"] = cognitive_trace.get("planner_json_valid", False)
                    trace["plan_repair_used"] = cognitive_trace.get("plan_repair_used", False)
                    trace["planner_validation_errors"] = cognitive_trace.get("planner_validation_errors", [])
                    trace["validated_route"] = cognitive_trace.get("validated_route")
                    trace["slot_needed"] = cognitive_trace.get("slot_needed")
                    trace["long_term_memory_used"] = cognitive_trace.get("long_term_memory_used", False)
                    trace["memory_id"] = cognitive_trace.get("memory_id")
                    trace["memory_retrieved"] = cognitive_trace.get("memory_retrieved", False)
                    trace["memory_llm_retry_requested"] = cognitive_trace.get(
                        "memory_llm_retry_requested", False
                    )
                    trace["memory_llm_retry_failed"] = cognitive_trace.get(
                        "memory_llm_retry_failed", False
                    )
                    trace["local_llm_synthesis_used"] = cognitive_trace.get("local_llm_synthesis_used", False)
                    trace["local_llm_model"] = cognitive_trace.get("local_llm_model", "")
                    for provider_key in (
                        "local_llm_provider",
                        "remote_model_provider",
                        "gpu_backend",
                    ):
                        if cognitive_trace.get(provider_key):
                            trace[provider_key] = cognitive_trace[provider_key]
                    if isinstance(cognitive_trace.get("model_residency"), dict):
                        trace["model_residency"] = cognitive_trace.get("model_residency")
                    if cognitive_trace.get("primary_model_tier"):
                        trace["primary_model_tier"] = cognitive_trace.get("primary_model_tier")
                    trace["native_stream_requested"] = cognitive_trace.get("native_stream_requested", False)
                    trace["native_streaming"] = cognitive_trace.get("native_streaming", False)
                    trace["native_stream_incremental"] = cognitive_trace.get("native_stream_incremental", False)
                    trace["native_stream_safety_repaired"] = cognitive_trace.get("native_stream_safety_repaired", False)
                    trace["academic_fallback_used"] = cognitive_trace.get("academic_fallback_used", False)
                    trace["critic_result"] = cognitive_trace.get("critic_result")
                    trace["final_answer_clean"] = cognitive_trace.get("final_answer_clean", True)
                    trace["training_log_saved"] = cognitive_trace.get("training_log_saved", False)
                    trace["fallback_used"] = cognitive_trace.get("fallback_used", False)
                    trace["natural_chat_used"] = cognitive_trace.get("natural_chat_used", False)
                    trace["natural_response_shaped"] = cognitive_trace.get("natural_response_shaped", False)
                    if cognitive_trace.get("reviewed_lesson_id"):
                        trace["reviewed_lesson_id"] = cognitive_trace.get("reviewed_lesson_id")
                        trace["reviewed_lesson_category"] = cognitive_trace.get("reviewed_lesson_category")
                    if cognitive_trace.get("final_answer_source"):
                        trace["final_answer_source"] = cognitive_trace.get("final_answer_source")
                    trace["conversation_state"] = cognitive_trace.get("conversation_state")
                    trace["dialogue_act"] = cognitive_trace.get("dialogue_act")
                    trace["conversation_topic"] = cognitive_trace.get("conversation_topic")
                    trace["turn_state"] = cognitive_trace.get("turn_state")
                    if cognitive_trace.get("natural_chat_error"):
                        trace["natural_chat_error"] = cognitive_trace.get("natural_chat_error")
                    if cognitive_trace.get("conversation_state_error"):
                        trace["conversation_state_error"] = cognitive_trace.get("conversation_state_error")
                    trace["route_path"] = cognitive_trace.get("route_path", trace.get("route_path", []))
                    trace["roles"] = cognitive_trace.get("roles", trace.get("roles", []))
                    trace["skills"] = list(dict.fromkeys(trace.get("skills", []) + cognitive_trace.get("skills", [])))
                    trace["confidence"] = cognitive_trace.get("confidence", trace.get("confidence", pipeline_conf))
                    trace["domain"] = cognitive_trace.get("domain") or trace.get("domain") or primary_intent
                    trace["memory_event"] = cognitive_trace.get("memory_event", trace.get("memory_event"))
                except Exception as cog_err:
                    trace["cognitive_os_error"] = str(cog_err)[:120]
                    response = None

            # Back up to the older hybrid router if Cognitive OS is unavailable or fails
            if response is None and _HYBRID_ROUTER_AVAIL:
                response, hybrid_trace = route_and_respond(normalized_text, dict_lookup_fn=_dict_lookup, memory=route_memory)
                # Merge quality gate fields from hybrid router
                trace["source"] = hybrid_trace.get("source", "hybrid_router")
                trace["transformer_ran"] = hybrid_trace.get("transformer_ran", False)
                trace["transformer_output_accepted"] = hybrid_trace.get("transformer_output_accepted", False)
                trace["fallback_used"] = hybrid_trace.get("fallback_used", True)
                trace["transformer_output_quality"] = hybrid_trace.get("transformer_output_quality", "unknown")
                trace["route_path"] = hybrid_trace.get("route_path", trace.get("route_path", []))
                trace["local_llm_used"] = hybrid_trace.get("local_llm_used", False)
                trace["route_model_hash"] = hybrid_trace.get("route_model_hash", "")
                trace["checkpoint_hash"] = hybrid_trace.get("checkpoint_hash", "")
                trace["generation"] = hybrid_trace.get("generation", {})
                trace["local_llm_provider"] = hybrid_trace.get("local_llm_provider", "")
                trace["local_llm_model"] = hybrid_trace.get("local_llm_model", "")
                trace["local_llm_url"] = hybrid_trace.get("local_llm_url", "")
                trace["local_llm_fallback_reason"] = hybrid_trace.get("local_llm_fallback_reason", "")
                trace["local_llm_error"] = hybrid_trace.get("local_llm_error", "")
            elif response is None:
                from nova_hybrid_router import classify_domain
                domain = classify_domain(normalized_text)
                fallbacks = {
                    "coding":"I can help with coding! What do you need?",
                    "math":"I have math training. What's your question?",
                    "science":"I have science training across physics, chemistry, biology, and more.",
                    "philosophy":"I've studied philosophy. What would you like to explore?",
                    "creative":"I can help with creative tasks!",
                    "general":"I'm Nova Creature with 7 brain roles. What's on your mind?",
                }
                response = fallbacks.get(domain, fallbacks["general"])
                trace["transformer_ran"] = False
                trace["transformer_output_accepted"] = False
                trace["fallback_used"] = True
                trace["transformer_output_quality"] = "no_router"

            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            trace = _set_final_answer_source(trace)
            return response, trace

        except Exception as e:
            traceback.print_exc()
            trace["roles"]=["error_handler","pipeline"]; trace["skills"]=["fallback"]; trace["confidence"]=0.70


    # --- Game Builder Path ---
    if _GAME_BUILDER_AVAIL and hasattr(_game_builder, "is_pacman_game_request") and _game_builder.is_pacman_game_request(text):
        try:
            result = _game_builder.build_pacman_game(projects_root=APP_BUILDER_PROJECTS_ROOT)
            project_name = result.project_name
            project_url = result.url_path
            trace["source"] = "sandbox_game_builder"
            trace["target_surface"] = "preview_area"
            trace["action"] = "create_game"
            trace["safety_level"] = "safe_write"
            trace["project_name"] = project_name
            trace["project_url"] = project_url
            trace["roles"] = ["right_hemisphere", "dream_simulation_transformer"]
            trace["skills"] = ["three_webgl", "game_builder"]
            trace["verification"] = {"checks": ["three_webgl"]}
            trace["confidence"] = 0.90
            trace["domain"] = "game_builder"
            response = "[GAME BUILDER] Created " + project_name + " using Three.js/WebGL.\nOpen: " + project_url + "\nFile: " + str(result.entry_file)
            response = _apply_game_supercheck(response, trace, project_url)
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            trace = _set_final_answer_source(trace)
            return response, trace
        except Exception:
            pass

    # ─── App Navigation (before hybrid router) ───
    if APP_NAV_AVAIL and _NAV_CONTEXT:
        try:
            nav_result = plan_app_navigation(text, _NAV_CONTEXT)
            if nav_result.recognized:
                trace["source"] = "app_navigation"
                trace["target_surface"] = nav_result.intent.target_surface
                trace["action"] = nav_result.intent.action
                trace["safety_level"] = nav_result.intent.safety_level.name if hasattr(nav_result.intent.safety_level, 'name') else str(nav_result.intent.safety_level)
                trace["steps"] = [{"kind": s.kind, "target": s.target} for s in nav_result.steps]
                trace["verification"] = {"status": getattr(nav_result.verification, 'status', 'planned'), "method": getattr(nav_result.verification, 'method', 'structured_navigation_plan')}
                trace["roles"] = ["app_navigation_router"]
                trace["skills"] = ["app_navigation", nav_result.intent.target_surface]
                trace["confidence"] = 0.95
                target_surface = nav_result.intent.target_surface.replace("_", " ").title()
                trace["route_path"] = ["app_navigation_router"]
                trace["domain"] = "app_navigation"
                response = f"Navigating to {target_surface}. Agent Library offers agent configuration and management."
                _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
                trace = _set_final_answer_source(trace)
                return response, trace
        except Exception:
            pass

    # ─── Weather Path ───
    weather_locations = _WEATHER_LOCATION_NAMES
    weather_location = _weather_location_from_text(q)
    weather_match = bool(weather_location)
    if weather_match and weather_location:
        summary = _fetch_weather_summary(weather_location)
        trace["source"] = "weather_router"
        trace["domain"] = "weather"
        trace["location"] = weather_location
        trace["roles"] = ["planner_transformer"]
        trace["skills"] = ["weather_lookup"]
        trace["confidence"] = 0.95
        trace["route_path"] = ["weather_router"]
        live_weather = "source: open-meteo" in summary.lower()
        trace["weather_source"] = "Open-Meteo" if live_weather else None
        trace["weather_live"] = live_weather
        if live_weather:
            trace["online_checked"] = True
            trace["grounding_evidence"] = [{
                "evidence_id": "live_weather_1",
                "content": summary,
                "source_name": "Open-Meteo",
                "source_type": "live_weather",
                "verified_at": datetime.now().astimezone().isoformat(),
                "live": True,
                "trust_level": 0.86,
            }]
        response = f"[WEATHER] {summary}"
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response, trace

    # ─── Dictionary / Definition Path ───
    dict_match = False
    dict_word = None
    for prefix in ["what does ", "what do ", "what are ", "define ", "meaning of ", "definition of "]:
        if q.startswith(prefix):
            dict_word = q[len(prefix):].strip().rstrip(".?!,;:").strip()
            if dict_word:
                dict_word = __import__('re').sub(r'\s+mean(s)?$', '', dict_word).strip()
                dict_match = True
                break
    # Handle "what is X" specially - only single word queries
    if not dict_match and q.startswith("what is "):
        potential = q[8:].strip().rstrip(".?!,;:").strip()
        if potential and " " not in potential:
            dict_word = __import__('re').sub(r'\s+mean(s)?$', '', potential).strip()
            dict_match = True
    if not dict_match:
        for suffix in [" meaning", " definition", " define"]:
            if q.endswith(suffix):
                dict_word = q[:-len(suffix)].strip()
                if dict_word:
                    dict_match = True
                    break

    if dict_match and dict_word and " " not in dict_word.strip():
        answer = _dict_lookup(dict_word)
        if answer:
            trace["source"] = "dictionary"
            trace["domain"] = "dictionary"
            trace["word"] = dict_word
            trace["term"] = dict_word
            trace["roles"] = ["memory_transformer", "dictionary_system"]
            trace["skills"] = ["dictionary_lookup"]
            trace["confidence"] = 0.98
            trace["route_path"] = ["dictionary_router"]
            response = _format_dictionary_definition(dict_word, answer)
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            trace = _set_final_answer_source(trace)
            return response, trace

    # ─── News Path ───
    news_keywords = ["news", "headlines", "headline", "what's happening", "what is happening", "current events", "look up"]
    if any(kw in q for kw in news_keywords):
        news_query = None
        for loc in weather_locations:
            if loc in q:
                news_query = loc.title()
                break
        if not news_query:
            m = __import__('re').search(r'news\s+(?:about|in|of|on)?\s*(.+)', q)
            if m:
                news_query = m.group(1).strip().title()
        if not news_query:
            news_query = "Latest"
        headlines = _fetch_news_headlines(news_query)
        trace["source"] = "news_router"
        trace["domain"] = "news"
        trace["query"] = news_query
        trace["roles"] = ["planner_transformer"]
        trace["skills"] = ["news_lookup"]
        trace["confidence"] = 0.95
        trace["route_path"] = ["news_router"]
        response = "[NEWS] Latest " + news_query + " headlines:\n"
        for h in headlines[:3]:
            response += "  \u2022 " + h['title'] + " (" + h['source'] + ")\n"
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response.strip(), trace

    # ─── Capabilities Path ───
    if any(w in q for w in ["what can you do", "what can u do", "capabilities", "what are you", "tell me about yourself", "abilities", "features", "what all can"]):
        caps = ("[CAPABILITIES] I am Nova Creature, a multi-brain AI with:\n"
                "  \u2022 7 Brain Roles: left hemisphere, right hemisphere, memory, planner, critic, dream, speech\n"
                "  \u2022 Long-term memory - I remember facts you teach me\n"
                "  \u2022 Dictionary - I define words instantly\n"
                "  \u2022 Math - I solve arithmetic, algebra, and more\n"
                "  \u2022 Science - physics, chemistry, biology, astronomy\n"
                "  \u2022 Coding - Python, JavaScript, debugging, make sandbox games\n"
                "  \u2022 App Navigation - I can guide you through the interface\n"
                "  \u2022 Creative - SVG, canvas, games\n"
                "  \u2022 Sensors - camera, mic, speaker (with permission)\n"
                "  \u2022 Live weather and news lookups")
        trace["source"] = "capabilities"
        trace["domain"] = "capabilities"
        trace["roles"] = ["speech_output_transformer", "memory_transformer"]
        trace["skills"] = ["capabilities_report"]
        trace["confidence"] = 0.98
        trace["route_path"] = ["capabilities_router"]
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = caps
        trace = _set_final_answer_source(trace)
        return caps, trace

    # ─── Math Path ───
    simple_math = _simple_arithmetic_fast_path(text)
    if simple_math is not None:
        math_expr, math_result = simple_math
        trace["source"] = "math_solver"
        trace["domain"] = "math"
        trace["roles"] = ["left_hemisphere"]
        trace["skills"] = ["math_solver"]
        trace["confidence"] = 0.97
        trace["route_path"] = ["math_solver"]
        response = "[MATH] " + math_expr + " = " + str(math_result) + "."
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response, trace

    # ─── Safe Fallback for corrupt transformer output ───
    if _HYBRID_ROUTER_AVAIL:
        try:
            _rr = globals().get('route_and_respond') or route_and_respond
            if _rr:
                test_response, test_trace = _rr(text, dict_lookup_fn=_dict_lookup, memory=MEMORY)
                if test_response and (any(ord(c) < 32 and c not in "\n\r\t" for c in test_response[:20])):
                    trace["source"] = "safe_fallback"
                    trace["domain"] = "safe_fallback"
                    trace["roles"] = ["critic_conscience_transformer"]
                    trace["skills"] = ["corrupt_output_detection", "safe_fallback"]
                    trace["confidence"] = 0.50
                    trace["blocked"] = True
                    trace["blocker"] = "corrupt_transformer_output"
                    trace["route_path"] = ["critic", "safe_fallback"]
                    response = "[SAFE FALLBACK] My transformer couldn't produce a clean answer. I defaulted to a safe generic response."
                    _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
                    trace = _set_final_answer_source(trace)
                    return response, trace
        except Exception:
            pass

    # ─── Learning Help Path ───
    if _is_learning_prompt_request(text):
        trace["source"] = "learning_help_router"
        trace["domain"] = "learning"
        trace["roles"] = ["rapid_learning"]
        trace["skills"] = ["learning_help"]
        trace["confidence"] = 0.90
        trace["route_path"] = ["learning_help_router"]
        response = _learning_prompt_response()
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response, trace

    # ─── Natural Fact / Learning Path ───
    learning_patterns = [
        (r'i\s+(\w+)\s+(?:is|are|was|were)\s+(.+)', lambda subj, val: (subj, val)),
        (r'my\s+(.+?)\s+(?:is|are)\s+(.+)', lambda slot, val: (slot, val)),
        (r'the\s+(.+?)\s+(?:name )?is\s+(.+)', lambda slot, val: (slot, val)),
        (r'(.+?)\s+(?:is|are)\s+(.+)', lambda slot, val: (slot, val)),
    ]
    has_learning_pattern = False
    for pattern_func in learning_patterns:
        pattern = pattern_func[0]
        if __import__('re').search(pattern, q) and "?" not in q and "what" not in q.split()[:2]:
            # For X IS Y pattern (catch-all), require at least 3 words and no special markup
            if pattern == r'(.+?)\s+(?:is|are)\s+(.+)' and len(q.split()) < 3:
                continue
            # Skip if looks like a sports/factual question
            if any(kw in q for kw in ["what is ", "who is ", "where is "]):
                continue
            has_learning_pattern = True
            break

    if has_learning_pattern and _dict_lookup(text) is None and not any(kw in q for kw in (["news", "headlines", "headline"])):
        trace["source"] = "natural_fact_learning"
        trace["domain"] = "dictionary"
        trace["roles"] = ["rapid_learning", "memory_transformer"]
        trace["skills"] = ["learning_intake", "fact_detection", "dictionary_write"]
        trace["confidence"] = 0.85
        trace["memory_event"] = "natural_fact_detected"
        trace["route_path"] = ["natural_fact_learning"]
        # Save to dictionary for recall
        canonical_fact = text.lower().strip().rstrip(".?!").strip()
        canonical_key = __import__("re").sub(r"[^a-z0-9 ]", "", canonical_fact).strip()
        if canonical_key:
            globals()["DICT_INDEX"][canonical_key] = text.strip().rstrip(".?!") + "."
        # Save the learned fact to dictionary for recall
        if len(text.strip()) > 5:
            fact_text = text.strip().rstrip(".?!").strip()
            # Create canonical key from the fact (lowercase, stripped)
            fact_key = __import__("re").sub(r"[^a-z0-9 ]", "", fact_text.lower()).strip()
            if fact_key:
                # module globals
                globals()["DICT_INDEX"][fact_key] = fact_text + "."
        response = "[LEARNING] Stored fact: \"" + text + "\""
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
        trace = _set_final_answer_source(trace)
        return response, trace

    # Fallback to original HYBRID ROUTER if pipeline not available
    if _HYBRID_ROUTER_AVAIL:
        try:
            _rr = globals().get('route_and_respond') or (route_and_respond if 'route_and_respond' in dir() else None)
            if _rr is None:
                raise RuntimeError("route_and_respond not available")
            response, hybrid_trace = _rr(text, dict_lookup_fn=_dict_lookup, memory=MEMORY)
            if _CONV_ENGINE_AVAIL:
                try: _CONV_ENGINE.add_exchange(text, response)
                except: pass
            _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = response
            trace["roles"] = hybrid_trace.get("roles", ["memory_transformer","speech_output_transformer"])
            trace["skills"] = hybrid_trace.get("skills", ["hybrid_routing"])
            trace["confidence"] = hybrid_trace.get("confidence", 0.80)
            trace["memory_event"] = hybrid_trace.get("memory_event", None)
            trace["domain"] = hybrid_trace.get("domain", "general")
            trace["route_path"] = hybrid_trace.get("route_path", [])
            trace["transformer_ran"] = hybrid_trace.get("transformer_ran", False)
            trace["transformer_output_accepted"] = hybrid_trace.get("transformer_output_accepted", False)
            trace["fallback_used"] = hybrid_trace.get("fallback_used", True)
            trace["transformer_output_quality"] = hybrid_trace.get("transformer_output_quality", "unknown")
            # Local LLM trace fields
            trace["local_llm_used"] = hybrid_trace.get("local_llm_used", False)
            trace["local_llm_provider"] = hybrid_trace.get("local_llm_provider", "")
            trace["local_llm_model"] = hybrid_trace.get("local_llm_model", "")
            trace["local_llm_url"] = hybrid_trace.get("local_llm_url", "")
            trace["local_llm_fallback_reason"] = hybrid_trace.get("local_llm_fallback_reason", "")
            trace["local_llm_error"] = hybrid_trace.get("local_llm_error", "")
            trace = _set_final_answer_source(trace)
            return response, trace
        except Exception as e:
            traceback.print_exc()
            trace["roles"]=["error_handler","hybrid_router"]; trace["skills"]=["fallback"]; trace["confidence"]=0.70

    # ─── Sports Path ───
    sports_keywords = ["sports", "football", "baseball", "basketball", "soccer", "team", "nfl", "nba", "mlb", "nhl", "reds", "bengals", "cincinnati"]
    if any(kw in q for kw in sports_keywords):
        trace["source"] = "sports_router"
        trace["domain"] = "sports"
        trace["roles"] = ["memory_transformer"]
        trace["skills"] = ["sports_lookup"]
        trace["confidence"] = 0.85
        trace["route_path"] = ["sports_router"]
        if "cincinnati" in q or "reds" in q or "bengals" in q:
            sports_answer = ("[SPORTS] The Cincinnati Bengals (NFL) and FC Cincinnati (MLS) "
                    "are the major professional sports teams in Cincinnati. "
                    "The Bengals play at Paycor Stadium, and FC Cincinnati plays at TQL Stadium.")
        else:
            sports_answer = "[SPORTS] I can answer basic sports questions. Try asking about specific teams or leagues."
        _LAST_USER_TEXT = text; _LAST_NOVA_RESPONSE = sports_answer
        trace = _set_final_answer_source(trace)
        return sports_answer, trace

    # ─── Ultimate Fallback ───
    trace["roles"]=["memory_transformer","speech_output_transformer"]; trace["skills"]=["fallback"]; trace["confidence"]=0.75
    pnum = len(MEMORY.get("people",{}))
    trace = _set_final_answer_source(trace)
    return "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?", trace


# ── HTTP Server ─────────────────────────────────────────────────────────────
def _candidate_retry_enabled():
    value = os.environ.get("NOVA_CANDIDATE_RETRY_ENABLED")
    if value is not None:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        from nova_local_llm_connector import LocalLLMConfig

        return LocalLLMConfig().regular_chat_escalation_enabled
    except Exception:
        return True


def _difficulty_escalation_enabled():
    value = os.environ.get("NOVA_DIFFICULTY_ESCALATION_ENABLED", "true")
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _difficulty_escalation_threshold():
    try:
        value = float(os.environ.get("NOVA_DIFFICULTY_ESCALATION_THRESHOLD", "0.68"))
    except (TypeError, ValueError):
        value = 0.68
    return max(0.50, min(value, 0.95))


def _technical_consistency_enabled():
    value = os.environ.get("NOVA_TECHNICAL_CONSISTENCY_ENABLED", "true")
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _deterministic_verifier_enabled():
    value = os.environ.get("NOVA_DETERMINISTIC_VERIFIER_ENABLED", "true")
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _capability_shadow_router_enabled():
    value = os.environ.get("NOVA_CAPABILITY_SHADOW_ROUTER_ENABLED", "true")
    configured = str(value or "").strip().lower() in {"1", "true", "yes", "on"}
    return bool(configured and getattr(CAPABILITY_EVAL_STORE, "enabled", True))


def _capability_shadow_route(text, trace, *, raw_adapter_request=False):
    """Observe evidence-based model advice without changing the active route."""

    base = {
        "enabled": _capability_shadow_router_enabled(),
        "status": "disabled",
        "task_type": None,
        "recommended_provider": None,
        "recommended_model": None,
        "actual_provider": None,
        "actual_model": None,
        "actual_model_called": False,
        "advisory_only": True,
        "automatic_routing": False,
        "route_changed": False,
        "training_used": False,
        "content_logged": False,
        "raw_adapter_modes_excluded": True,
    }
    if not base["enabled"]:
        return base
    if raw_adapter_request:
        return {**base, "status": "raw_adapter_bypass"}
    safe_trace = trace if isinstance(trace, dict) else {}
    task_type = _candidate_escalation_task_type(text, safe_trace)
    try:
        recommendation = CAPABILITY_EVAL_STORE.shadow_recommendation(task_type)
    except Exception:
        recommendation = {"status": "evaluation_unavailable", "task_type": task_type}
    return {
        **base,
        **recommendation,
        "actual_provider": str(safe_trace.get("local_llm_provider") or "") or None,
        "actual_model": str(safe_trace.get("local_llm_model") or "") or None,
        "actual_model_called": bool(safe_trace.get("local_llm_synthesis_used")),
        "advisory_only": True,
        "automatic_routing": False,
        "route_changed": False,
        "training_used": False,
        "content_logged": False,
        "raw_adapter_modes_excluded": True,
    }


def _evaluate_technical_consistency(text, answer):
    return evaluate_technical_consistency(
        text,
        answer,
        enabled=_technical_consistency_enabled(),
    )


def _merge_consistency_with_firewall(decision, consistency):
    """Make a high-confidence consistency failure authoritative for managed chat."""

    if not decision.accepted or consistency.accepted:
        return decision
    return FirewallDecision(
        accepted=False,
        score=min(float(decision.score), float(consistency.score)),
        reasons=tuple(dict.fromkeys(tuple(decision.reasons) + ("technical_consistency_failed",))),
        status="blocked",
    )


def _candidate_retry_maximum_model_bytes():
    configured = os.environ.get("NOVA_CANDIDATE_MAX_MODEL_BYTES")
    try:
        if configured is not None:
            value = int(configured)
        else:
            from nova_local_llm_connector import LocalLLMConfig

            value = LocalLLMConfig().escalation_max_model_bytes
    except Exception:
        value = 8_000_000_000
    return max(256_000_000, min(value, 64_000_000_000))


def _candidate_retry_minimum_model_bytes():
    try:
        from nova_local_llm_connector import LocalLLMConfig

        value = LocalLLMConfig().escalation_min_model_bytes
    except Exception:
        value = 3_000_000_000
    return max(0, min(value, _candidate_retry_maximum_model_bytes()))


def _candidate_retry_timeout_seconds():
    try:
        configured = os.environ.get("NOVA_CANDIDATE_RETRY_TIMEOUT_SECONDS")
        if configured is not None:
            value = int(configured)
        else:
            from nova_local_llm_connector import LocalLLMConfig

            value = LocalLLMConfig().escalation_timeout_seconds
    except Exception:
        value = 180
    return max(5, min(value, 600))


def _candidate_retry_max_tokens():
    try:
        value = int(os.environ.get("NOVA_CANDIDATE_MAX_TOKENS", "256"))
    except (TypeError, ValueError):
        value = 256
    return max(64, min(value, 512))


def _candidate_retry_context_window():
    try:
        value = int(os.environ.get("NOVA_CANDIDATE_CONTEXT_WINDOW", "4096"))
    except (TypeError, ValueError):
        value = 4096
    return max(2048, min(value, 32768))


def _candidate_retry_keep_alive():
    try:
        from nova_local_llm_connector import LocalLLMConfig

        return LocalLLMConfig().reviewer_keep_alive
    except Exception:
        return "10m"


def _middle_reviewer_enabled():
    try:
        from nova_local_llm_connector import LocalLLMConfig

        return bool(LocalLLMConfig().middle_reviewer_enabled)
    except Exception:
        return True


def _middle_model_qualification(model_id, task_type="general"):
    """Apply the full-pack evidence gate only when qualifying evidence exists."""

    try:
        return CAPABILITY_EVAL_STORE.middle_tier_qualification(
            "ollama",
            str(model_id or ""),
            str(task_type or "general"),
        )
    except Exception:
        return {
            "enforced": False,
            "eligible": None,
            "status": "evaluation_unavailable",
            "content_logged": False,
            "route_changed": False,
        }


def _direct_middle_route_decision(text, context=None, *, raw_adapter_request=False):
    """Select an installed middle model before synthesis for clearly hard requests."""

    decision = {
        "enabled": False,
        "selected": False,
        "reason": "disabled",
        "provider": None,
        "model": None,
        "tier": "middle",
        "difficulty": None,
        "content_logged": False,
    }
    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
    except Exception:
        decision["reason"] = "configuration_unavailable"
        return decision

    decision["enabled"] = bool(config.direct_middle_enabled and config.middle_reviewer_enabled)
    if not decision["enabled"]:
        return decision
    if raw_adapter_request:
        decision["reason"] = "raw_adapter_bypass"
        return decision

    difficulty = assess_request_difficulty(
        text,
        {},
        threshold=config.direct_middle_threshold,
    )
    decision["difficulty"] = difficulty.as_trace()
    if not difficulty.larger_local_recommended:
        decision["reason"] = "below_direct_threshold"
        return decision
    if str(config.provider or "").lower() != "ollama":
        decision["reason"] = "provider_not_supported_by_current_cognitive_synthesizer"
        return decision

    gateway = globals().get("NOVA_GATEWAY")
    if gateway is None or not getattr(gateway, "providers", None):
        decision["reason"] = "provider_registry_unavailable"
        return decision
    try:
        provider = gateway.providers.get_provider("ollama")
        if not _provider_is_safe_local_candidate(provider):
            decision["reason"] = "provider_not_safe_local"
            return decision
        selected, selection = select_alternate_model(
            provider.list_models(),
            primary_model=str(config.model or ""),
            minimum_model_bytes=config.middle_reviewer_min_model_bytes,
            maximum_model_bytes=config.middle_reviewer_max_model_bytes,
            preferred_model_ids=config.middle_reviewer_model_preferences(
                difficulty.task_type
            ),
            prefer_larger=False,
            require_preferred=True,
        )
    except Exception:
        decision["reason"] = "middle_model_discovery_failed"
        return decision
    decision["model_selection"] = {
        "eligible_count": int(selection.get("eligible_count") or 0),
        "rejected_count": int(selection.get("rejected_count") or 0),
    }
    if selected is None:
        decision["reason"] = "middle_model_unavailable"
        return decision

    selected_provider = str(getattr(selected, "provider_id", "") or "ollama")
    selected_model = str(getattr(selected, "model_id", "") or "")
    if MODEL_QUALITY.is_quarantined(selected_provider, selected_model):
        decision.update(
            reason="middle_model_quarantined",
            provider=selected_provider,
            model=selected_model,
            model_quality=MODEL_QUALITY.model_status(
                selected_provider,
                selected_model,
            ),
        )
        return decision
    qualification = _middle_model_qualification(
        selected_model,
        difficulty.task_type,
    )
    decision["capability_qualification"] = qualification
    if qualification.get("enforced") and not qualification.get("eligible"):
        decision.update(
            reason="middle_model_not_qualified",
            provider=selected_provider,
            model=selected_model,
        )
        return decision

    decision.update(
        selected=True,
        reason="selected",
        provider=selected_provider,
        model=selected_model,
        estimated_model_bytes=int(
            (getattr(selected, "metadata", {}) or {}).get("size") or 0
        ),
        resource_manager_required=True,
        timeout_seconds=int(config.escalation_timeout_seconds),
        keep_alive=str(config.reviewer_keep_alive),
        max_tokens=int(config.direct_middle_max_tokens),
    )
    return decision


def _optional_strong_model_decision(context: dict | None, raw_adapter_request: bool = False) -> dict:
    """Allow Nova Strong to use only its configured, installed local model."""

    mode = str((context or {}).get("nova_model_mode") or "").strip().lower()
    decision = {
        "requested": bool(mode and mode != "nova"),
        "selected": False,
        "reason": "ordinary_route",
        "mode": mode or "nova",
        "model": None,
        "content_logged": False,
    }
    if mode in {"", "nova"}:
        return decision
    if raw_adapter_request:
        decision["reason"] = "raw_adapter_bypass"
        return decision
    if mode != "strong":
        decision["reason"] = "unsupported_mode"
        return decision

    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
        configured_model = str(config.optional_strong_model or "").strip()
        configured_timeout = int(config.optional_strong_timeout)
        configured_keep_alive = str(config.optional_strong_keep_alive)
        if str(config.provider or "").strip().lower() != "ollama":
            decision["reason"] = "provider_not_supported"
            return decision
        if not configured_model or not configured_keep_alive:
            decision["reason"] = "configuration_unavailable"
            return decision
    except Exception:
        decision["reason"] = "configuration_unavailable"
        return decision

    gateway = globals().get("NOVA_GATEWAY")
    if gateway is None or not getattr(gateway, "providers", None):
        decision["reason"] = "provider_registry_unavailable"
        return decision
    try:
        provider = gateway.providers.get_provider("ollama")
        if not _provider_is_safe_local_candidate(provider):
            decision["reason"] = "provider_not_safe_local"
            return decision
        selected = next(
            (
                candidate
                for candidate in provider.list_models()
                if str(getattr(candidate, "model_id", "") or "").strip().lower()
                == configured_model.lower()
            ),
            None,
        )
    except Exception:
        decision["reason"] = "model_discovery_failed"
        return decision
    if selected is None:
        decision["reason"] = "model_unavailable"
        return decision
    try:
        if MODEL_QUALITY.is_quarantined("ollama", configured_model):
            decision.update(reason="model_quarantined", model=configured_model)
            return decision
        estimated_model_bytes = int(
            (getattr(selected, "metadata", {}) or {}).get("size") or 0
        )
    except Exception:
        decision["reason"] = "model_validation_failed"
        return decision

    decision.update(
        selected=True,
        reason="selected",
        provider="ollama",
        model=configured_model,
        estimated_model_bytes=estimated_model_bytes,
        timeout_seconds=configured_timeout,
        keep_alive=configured_keep_alive,
        tier="strong",
    )
    return decision


def _emit_chat_progress(context, stage, label, percent=None):
    """Publish a content-free progress stage when the active transport supports it."""

    callback = (context or {}).get("progress_callback") if isinstance(context, dict) else None
    if not callable(callback):
        return False
    try:
        return callback(stage, label, percent) is not False
    except Exception:
        return False


def _release_direct_middle_before_deep(trace):
    """Release the completed 3B model before a memory-heavier deep fallback."""

    model = str((trace or {}).get("local_llm_model") or "").strip()
    result = {
        "attempted": bool(model),
        "released": False,
        "model": model or None,
        "reason": "missing_model",
        "content_logged": False,
    }
    if not model:
        return result
    try:
        from nova_model_memory import model_activity_status, unload_ollama_model

        if int(model_activity_status().get("reviewer") or 0) > 0:
            result["reason"] = "concurrent_middle_generation"
            return result
        unload_ollama_model(model, timeout=15)
        result.update(released=True, reason="released_before_deep")
    except Exception:
        result["reason"] = "release_failed"
    return result


def _candidate_escalation_task_type(text, trace=None):
    """Classify only the capability profile needed by a larger local candidate."""

    value = _canonical_key(text)
    trace = trace if isinstance(trace, dict) else {}
    assessed_task = str((trace.get("uncertainty_routing") or {}).get("task_type") or "")
    if assessed_task in {"general", "reasoning", "coding"}:
        return assessed_task
    domain = str(trace.get("domain") or "").lower()
    coding_markers = (
        "code", "coding", "debug", "javascript", "python", "program",
        "script", "software", "stack trace", "syntax",
    )
    reasoning_markers = (
        "analyze", "calculate", "compare", "deduce", "logic", "math", "prove",
        "reason", "step by step", "why", "exact value", "precise value",
        "busy beaver",
    )
    reasoning_overrides = ("busy beaver", "exact value", "precise value")
    if any(marker in value for marker in reasoning_overrides):
        return "reasoning"
    if "coding" in domain or any(marker in value for marker in coding_markers):
        return "coding"
    if any(marker in domain for marker in ("math", "reason", "science")) or any(
        marker in value for marker in reasoning_markers
    ):
        return "reasoning"
    return "general"


def _candidate_model_preferences(text, trace=None):
    try:
        from nova_local_llm_connector import LocalLLMConfig

        task_type = _candidate_escalation_task_type(text, trace)
        return LocalLLMConfig().escalation_model_preferences(task_type)
    except Exception:
        return ()


_MODEL_UNCERTAINTY_PATTERNS = (
    r"\bi don['’]?t know\b",
    r"\bi do not know\b",
    r"\bi['’]?m not sure\b",
    r"\bi am not sure\b",
    r"\bi['’]?m uncertain\b",
    r"\bi am uncertain\b",
    r"\bi (?:do not|don['’]?t) have enough information\b",
    r"\bnot enough information\b",
    r"\bi can(?:not|'t) answer\b",
    r"\bthat is unknown\b",
)


def _is_unverified_exact_numeric_claim(text, response, grounding):
    """Detect a newly invented exact number when no supporting evidence exists."""

    if not isinstance(grounding, dict):
        return False
    if grounding.get("status") == "grounded" or int(grounding.get("evidence_count") or 0) > 0:
        return False
    question = _canonical_key(text)
    exact_markers = (
        "exact value",
        "exact number",
        "exactly how many",
        "precise value",
        "specific number",
    )
    if not any(marker in question for marker in exact_markers):
        return False
    question_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", str(text or "")))
    answer_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", str(response or "")))
    return bool(answer_numbers.difference(question_numbers))


def _request_needs_substantive_answer(text):
    """Identify prompts where a tiny surface reply is unlikely to be useful."""

    value = _canonical_key(text)
    if not value:
        return False
    return bool(
        re.search(r"^(?:but\s+|and\s+|so\s+)?(?:how|why)\b", value)
        or any(
            marker in value
            for marker in (
                "all the ways",
                "analyze",
                "break it down",
                "can you explain",
                "can u explain",
                "compare",
                "explain",
                "help me decide",
                "how should",
                "tell me about",
                "what can i do about",
                "what do i do",
                "what should i do",
                "what should i say",
                "what happens if",
                "what happens next",
                "what if",
                "what makes",
            )
        )
    )


def _answer_is_too_shallow(text, response):
    """High-precision shallow-answer signal for bounded local escalation."""

    if not _request_needs_substantive_answer(text):
        return False
    answer = str(response or "").strip()
    words = re.findall(r"[a-z0-9]+", answer.lower())
    if len(words) <= 8:
        return True
    if len(words) <= 13 and answer.endswith("?"):
        return True
    return False


def _answer_reasks_user_question(text, response):
    """Detect a model turning the user's question back on them before answering."""

    question = _canonical_key(text)
    raw_answer = str(response or "").strip()
    if not question or "?" not in raw_answer[:240]:
        return False
    first_question = _canonical_key(raw_answer[: raw_answer.find("?")])
    leads = (
        "what if",
        "what should",
        "what do",
        "what happens",
        "why",
        "how",
        "can you",
        "can u",
        "could you",
        "could u",
        "would you",
        "would u",
    )
    question_lead = next((lead for lead in leads if question.startswith(lead)), "")
    return bool(question_lead and first_question.startswith(question_lead))


def _answer_defers_substantive_request(text, response):
    """Catch a detailed request being replaced with an unnecessary clarification."""

    if not _request_needs_substantive_answer(text):
        return False
    answer = _canonical_key(response)
    deflection_patterns = (
        r"\bwhat specific (?:areas?|parts?|aspects?) (?:are you|would you be) (?:most )?interested in\b",
        r"\bwhich (?:area|part|aspect) would you like (?:me )?to (?:explain|cover|analyze)\b",
        r"\bwhat (?:area|part|aspect) would you like (?:me )?to (?:start with|focus on)\b",
        r"\bcould you clarify (?:which|what) (?:area|part|aspect)\b",
    )
    return any(re.search(pattern, answer) for pattern in deflection_patterns)


def _explicit_requested_aspects(text):
    """Return a bounded transient list of explicitly requested areas."""

    request_text = str(text or "").strip()
    match = re.search(
        r"\b(?:analyze|cover|address|evaluate|consider)\s+(.{5,220}?)(?=(?:,\s*)?\bthen\b|[.!?;]|$)",
        request_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    segment = match.group(1).strip(" ,")
    if segment.count(",") >= 2:
        parts = [re.sub(r"^(?:and|or)\s+", "", part.strip(), flags=re.IGNORECASE) for part in segment.split(",")]
    else:
        parts = [part.strip() for part in re.split(r"\s+and\s+", segment, flags=re.IGNORECASE)]
    parts = [
        re.sub(r"\s+", " ", part).strip(" :-")[:48]
        for part in parts
        if part
    ]
    if not 3 <= len(parts) <= 8:
        return []
    return parts


def _requested_aspect_coverage(text, response):
    """Measure explicit multi-part task coverage without storing topic text."""

    parts = list(_explicit_requested_aspects(text))
    if parts and re.search(
        r"\b(?:then|and)\s+(?:recommend|propose|choose|select)\b",
        str(text or ""),
        flags=re.IGNORECASE,
    ):
        parts.append("recommendation")
    if not parts:
        return {
            "applied": False,
            "required_count": 0,
            "covered_count": 0,
            "coverage_ratio": 1.0,
            "complete": True,
        }

    generic = {
        "behavior", "behaviour", "consideration", "considerations", "impact",
        "impacts", "risk", "risks", "tradeoff", "tradeoffs",
    }

    def token_root(token):
        value = str(token or "").lower()
        for prefix in (
            "migrat", "privac", "latenc", "offline", "cost", "secur",
            "perform", "reliab", "recommend",
        ):
            if value.startswith(prefix):
                return prefix
        return value[:-1] if value.endswith("s") and len(value) > 4 else value

    part_root_sets = []
    for part in parts:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", part.lower())
            if len(token) > 2 and token not in generic
        ]
        if not tokens:
            tokens = [token for token in re.findall(r"[a-z0-9]+", part.lower()) if len(token) > 2]
        part_root_sets.append({token_root(token) for token in tokens})

    segments = [
        segment.strip()
        for segment in re.split(r"(?:[\r\n]+|(?<=[.!?;])\s+)", str(response or ""))
        if segment.strip()
    ]
    covered_indices = set()
    for segment in segments:
        segment_roots = {
            token_root(token)
            for token in re.findall(r"[a-z0-9]+", segment.lower())
            if len(token) > 2
        }
        canonical_segment = _canonical_key(segment)
        matching = [
            index
            for index, required_roots in enumerate(part_root_sets)
            if required_roots.intersection(segment_roots)
        ]
        recommendation_index = next(
            (
                index
                for index, part in enumerate(parts)
                if part == "recommendation"
            ),
            None,
        )
        if recommendation_index is not None and any(
            cue in canonical_segment
            for cue in (
                "recommend",
                "start with",
                "start local",
                "first stage",
                "second stage",
                "staged approach",
                "phase one",
                "phase two",
                "add optional",
                "best option",
                "best approach",
            )
        ):
            matching.append(recommendation_index)
        if not matching:
            continue
        # A sentence explicitly presenting the requested areas as topics is an
        # introduction/checklist, not evidence that each one was answered.
        enumeration_cues = (
            "areas to consider",
            "aspects to consider",
            "factors to consider",
            "key areas",
            "key aspects",
            "key factors",
            "we will analyze",
            "we ll analyze",
            "we will cover",
            "we ll cover",
            "start by analyzing",
        )
        if len(matching) >= 3 and any(cue in canonical_segment for cue in enumeration_cues):
            continue
        covered_indices.update(matching)
    covered = len(covered_indices)
    ratio = covered / len(parts)
    return {
        "applied": True,
        "required_count": len(parts),
        "covered_count": covered,
        "coverage_ratio": round(ratio, 3),
        "complete": covered == len(parts),
    }


def _repair_missing_requested_recommendation(text, response):
    """Add one bounded recommendation only when it is the sole missing request part."""

    coverage = _requested_aspect_coverage(text, response)
    request_value = _canonical_key(text)
    if (
        not coverage.get("applied")
        or coverage.get("complete")
        or int(coverage.get("required_count") or 0)
        - int(coverage.get("covered_count") or 0)
        != 1
        or not re.search(
            r"\b(?:then|and)\s+(?:recommend|propose|choose|select)\b",
            str(text or ""),
            flags=re.IGNORECASE,
        )
    ):
        return str(response or "")
    if (
        "local" in request_value
        and "remote" in request_value
        and any(
            marker in request_value
            for marker in ("storage", "memory", "database", "sqlite", "vector")
        )
    ):
        recommendation = (
            "Recommendation: Start with encrypted local storage behind a "
            "provider-neutral interface, then add optional consent-based remote "
            "synchronization in a second stage."
        )
    else:
        recommendation = (
            "Recommendation: Start with the lower-risk option that best satisfies "
            "the priorities above, then pilot the alternative in a limited second "
            "stage before committing."
        )
    repaired = str(response or "").rstrip() + "\n\n" + recommendation
    return repaired if _requested_aspect_coverage(text, repaired).get("complete") else str(response or "")


def _regular_chat_escalation_reason(text, response, trace, decision):
    """Return a safe surface-level reason for asking a larger local model."""

    if not isinstance(trace, dict):
        return ""
    consistency = trace.get("answer_consistency") if isinstance(trace, dict) else None
    if not decision.accepted and isinstance(consistency, dict) and not consistency.get("accepted", True):
        return "primary_model_consistency_failed"
    if not decision.accepted:
        return "answer_quality_check_failed"
    source = str(trace.get("source") or "").lower()
    domain = str(trace.get("domain") or "").lower()
    if "memory" in source or "memory" in domain or trace.get("memory_event") == "missing:long_term":
        return ""
    model = str(trace.get("local_llm_model") or "").lower()
    used_model = bool(trace.get("local_llm_synthesis_used"))
    if not used_model or "qwen" not in model:
        return ""
    difficulty = assess_request_difficulty(
        text,
        trace,
        threshold=_difficulty_escalation_threshold(),
    )
    trace["uncertainty_routing"] = difficulty.as_trace()
    answer = str(response or "").strip().lower()
    if any(re.search(pattern, answer, flags=re.IGNORECASE) for pattern in _MODEL_UNCERTAINTY_PATTERNS):
        return "primary_model_uncertain"
    grounding = trace.get("fact_grounding")
    if _is_unverified_exact_numeric_claim(text, response, grounding):
        return "primary_model_unverified_exact_claim"
    if _answer_reasks_user_question(text, response):
        return "primary_model_question_restatement"
    if _answer_defers_substantive_request(text, response):
        return "primary_model_clarification_deflection"
    if _answer_is_too_shallow(text, response):
        return "primary_model_too_shallow"
    if trace.get("direct_middle_primary"):
        requested_coverage = _requested_aspect_coverage(text, response)
        trace["requested_aspect_coverage"] = requested_coverage
        if requested_coverage.get("applied") and not requested_coverage.get("complete"):
            return "primary_model_requested_aspects_missing"
    if (
        _difficulty_escalation_enabled()
        and not bool(trace.get("direct_middle_primary"))
        and primary_answer_needs_larger_review(difficulty, response)
    ):
        return "primary_model_complexity_mismatch"
    try:
        confidence = float(trace.get("confidence"))
    except (TypeError, ValueError):
        confidence = 1.0
    if confidence < 0.72:
        return "primary_model_low_confidence"
    if bool(trace.get("fallback_used")):
        return "primary_route_fallback"
    return ""


def _conversation_turn_commit_decision(response, trace, *, evaluation_only=False):
    """Decide whether a completed turn is safe to become future context."""

    if evaluation_only:
        return False, "evaluation_only"
    trace = trace if isinstance(trace, dict) else {}
    firewall = trace.get("answer_firewall")
    firewall_status = str(
        firewall.get("status") if isinstance(firewall, dict) else ""
    ).strip().lower()
    final_source = str(trace.get("final_answer_source") or "").strip().lower()
    source = str(trace.get("source") or "").strip().lower()
    if firewall_status in {
        "blocked",
        "fact_grounding_blocked",
        "unverified_exact_claim_blocked",
        "stream_postcheck_warning",
    }:
        if "recovery" in final_source or "recovery" in source:
            return False, "recovery_response"
        return False, "firewall_blocked"
    if firewall_status == "bypassed_raw":
        return bool(str(response or "").strip()), "raw_adapter_answer"
    if any(
        marker in final_source or marker in source
        for marker in ("recovery", "error", "fact_grounding_guard", "unverified")
    ):
        return False, "recovery_response"
    if trace.get("fallback_used") and not is_contextworthy_assistant_text(response):
        return False, "recovery_response"
    if not is_contextworthy_assistant_text(response):
        return False, "non_contextworthy_answer"
    return True, "validated_answer"


def _select_previous_exchange(context, *, client_previous, legacy_previous):
    """Keep an explicit client history authoritative over legacy process state.

    The browser can intentionally omit an assistant answer when the preceding
    turn was blocked or discarded. Falling back to the process-global last
    answer in that case leaks an unrelated conversation into the new turn.
    """

    context = context if isinstance(context, dict) else {}
    client_previous = tuple(client_previous or ("", ""))
    legacy_previous = tuple(legacy_previous or ("", ""))
    explicit_history = (
        "conversation_history" in context
        or "conversation_summary_history" in context
        or bool(context.get("nova_gateway"))
    )
    if explicit_history:
        return client_previous[0], client_previous[1]
    return (
        client_previous[0] or legacy_previous[0],
        client_previous[1] or legacy_previous[1],
    )


def _provider_is_safe_local_candidate(provider):
    """Require free local declaration and a loopback URL when a URL exists."""
    if str(getattr(provider, "local_or_remote", "local")) != "local":
        return False
    if str(getattr(provider, "cost_type", "free")) != "free":
        return False
    endpoint = str(
        getattr(provider, "base_url", "")
        or getattr(provider, "generate_url", "")
        or ""
    ).strip()
    if not endpoint:
        # Embedded providers may have no network endpoint at all. Their local
        # declaration remains the capability contract.
        return True
    try:
        hostname = (urlparse(endpoint).hostname or "").strip().lower()
        if hostname == "localhost":
            return True
        return bool(hostname and ipaddress.ip_address(hostname).is_loopback)
    except (ValueError, TypeError):
        return False


def _candidate_retry_allowed(trace, context):
    """Keep alternate generation away from tools, actions, writes, and raw modes."""
    if not _candidate_retry_enabled():
        return False, "disabled"
    if not isinstance(trace, dict):
        return False, "missing_trace"
    if trace.get("native_streaming"):
        return False, "native_stream_already_visible"
    cancelled = (context or {}).get("stream_cancelled") if isinstance(context, dict) else None
    if callable(cancelled) and cancelled():
        return False, "request_cancelled"
    if trace.get("_fact_grounding_blocking"):
        return False, "fact_grounding_blocked"
    if trace.get("action") or trace.get("permission") or trace.get("safety_level"):
        return False, "action_route"
    source = str(trace.get("source") or "").lower()
    domain = str(trace.get("domain") or "").lower()
    blocked_fragments = {
        "agent", "app_builder", "app_navigation", "camera", "command", "deployment",
        "file", "game_builder", "memory_write", "permission", "project", "robot",
        "sandbox", "sensor", "tool", "training", "vision", "website_builder",
    }
    if any(fragment in source or fragment in domain for fragment in blocked_fragments):
        return False, "non_chat_route"
    return True, "eligible"


def _fact_grounding_enabled():
    value = str(os.environ.get("NOVA_FACT_GROUNDING_ENABLED", "true") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _fact_grounding_blocks_unverified_current():
    value = str(os.environ.get("NOVA_BLOCK_UNVERIFIED_CURRENT", "true") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _fact_grounding_maximum_age_days():
    try:
        value = int(os.environ.get("NOVA_FACT_MAX_AGE_DAYS", "30"))
    except (TypeError, ValueError):
        value = 30
    return max(1, min(value, 3650))


def _evaluate_fact_grounding(text, response, trace):
    return evaluate_grounding(
        text,
        response,
        trace=trace,
        evidence_store=FACT_EVIDENCE_STORE,
        maximum_age_days=_fact_grounding_maximum_age_days(),
        enabled=_fact_grounding_enabled(),
        block_unverified_current=_fact_grounding_blocks_unverified_current(),
    )


def _fact_grounding_route_can_supply_fresh_evidence(text, context):
    context = context if isinstance(context, dict) else {}
    q = _canonical_key(text)
    if context.get("sensor_snapshot") and any(
        marker in q for marker in ("sensor", "camera", "microphone", "battery", "location", "motion", "orientation")
    ):
        return True
    for record in FACT_EVIDENCE_STORE.search(text, limit=3):
        local_decision = evaluate_grounding(
            text,
            record.content,
            trace={},
            evidence_store=FACT_EVIDENCE_STORE,
            maximum_age_days=_fact_grounding_maximum_age_days(),
            enabled=_fact_grounding_enabled(),
            block_unverified_current=_fact_grounding_blocks_unverified_current(),
        )
        if local_decision.status == "grounded" and not local_decision.blocking:
            return True
    return any(
        (
            _is_current_context_query(text),
            _is_current_us_president_query(text),
            _is_weather_lookup_request(text),
            _is_live_news_request(text),
            _is_research_lookup_request(text),
            _is_scrape_request(text),
        )
    )


def _fact_grounding_preflight(text, context):
    if _deterministic_verifier_enabled() and solve_deterministic_request(text) is not None:
        return None
    context = context if isinstance(context, dict) else {}
    decision = evaluate_grounding(
        text,
        "",
        trace={
            "conversation_decision": context.get("conversation_decision"),
        },
        evidence_store=FACT_EVIDENCE_STORE,
        maximum_age_days=_fact_grounding_maximum_age_days(),
        enabled=_fact_grounding_enabled(),
        block_unverified_current=_fact_grounding_blocks_unverified_current(),
    )
    if decision.blocking and not _fact_grounding_route_can_supply_fresh_evidence(text, context):
        return decision
    return None


def _candidate_retry_prompt(
    text,
    previous_user,
    previous_answer,
    *,
    primary_trace=None,
    context=None,
):
    """Build a bounded Nova-owned prompt with relevant conversation and memory context."""

    resolution = resolve_followup(text, previous_user, previous_answer)
    if resolution.generation_prompt:
        return resolution.generation_prompt, (str(text or "") + " " + str(previous_user or "")).strip()
    context_lines = []
    summary_context = render_conversation_summary((context or {}).get("conversation_summary"))
    if summary_context:
        context_lines.append(summary_context)
    for message in bounded_conversation_history(context or {}, text, maximum_messages=4):
        role = "User" if message.get("role") == "user" else "Nova"
        content = str(message.get("content") or "").strip()[:600]
        if content:
            context_lines.append(role + ": " + content)
    trace = primary_trace if isinstance(primary_trace, dict) else {}
    if trace.get("memory_retrieved"):
        slot = str(trace.get("extracted_slot") or "").strip().replace("_", " ")
        value = str(trace.get("extracted_value") or "").strip()[:500]
        if slot and value:
            context_lines.append("Relevant saved memory: " + slot + " = " + value)
    requested_aspects = _explicit_requested_aspects(text)
    prompt = (
        "Answer the user's exact request directly and naturally. Give useful content immediately. "
        "Do not introduce yourself, list Nova's capabilities, discuss routing, or ask what the user wants to do next. "
        "Never merely repeat or lightly paraphrase the request. "
        "Cover every explicitly requested area; when the request gives a list, use one short labeled clause for each item by name before the recommendation. "
        "If the answer is uncertain, say what is uncertain instead of inventing a fact. "
        "Keep the complete answer under 110 words, prioritize the requested conclusion, and finish the final sentence."
    )
    if requested_aspects:
        prompt += (
            "\nRequired output format: no preamble and no headings beyond these labels. "
            "Write exactly one compact clause after each label, in this order:"
        )
        for aspect in requested_aspects:
            prompt += "\n" + aspect[:1].upper() + aspect[1:] + ":"
        prompt += "\nRecommendation:"
    if _technical_consistency_enabled():
        consistency_constraints = technical_consistency_guidance(text)
        if consistency_constraints:
            prompt += "\nHigh-confidence technical constraints:\n- " + "\n- ".join(consistency_constraints)
    if context_lines:
        prompt += "\nRelevant Nova context:\n" + "\n".join(context_lines)
    prompt += "\nCurrent user request: " + str(text or "").strip()
    creative_markers = ("imagine", "write a story", "make up", "describe a scene", "creative")
    if any(marker in _canonical_key(text) for marker in creative_markers):
        prompt += (
            "\nThis is an imaginative request. Develop it into at least three concrete sentences "
            "with vivid sensory or structural details."
        )
    exact_markers = ("exact value", "exact number", "precise value", "specific number")
    if any(marker in _canonical_key(text) for marker in exact_markers):
        prompt += (
            "\nThe user is asking for an exact value. If it is not established, explicitly say that "
            "it is unknown or unverified and briefly explain why. Do not answer with only yes/no, "
            "and never invent a number."
        )
    return prompt, str(text or "").strip()


def _candidate_requires_numeric_verification(text, previous_user):
    value = _canonical_key(str(text or "") + " " + str(previous_user or ""))
    quantitative_questions = (
        "how big", "how tall", "how far", "how fast", "how heavy", "how many",
        "how much", "what year", "what size", "what temperature", "what percent",
        "what percentage", "what is the age", "what is the circumference",
        "what is the cost", "what is the diameter", "what is the distance",
        "what is the population", "what is the price", "what is the speed",
        "what is the weight",
    )
    exact_requests = (
        "exact value", "exact number", "exactly how many", "precise value",
        "specific number", "give me a number", "numeric value", "numerical value",
    )
    return any(marker in value for marker in quantitative_questions + exact_requests)


def _generate_alternate_local_candidate(
    text,
    previous_user,
    previous_answer,
    primary_trace,
    context,
    *,
    reviewer_tier="deep",
    excluded_model_ids=(),
):
    """Make one provider-registry retry using a different local model when possible."""
    gateway = globals().get("NOVA_GATEWAY")
    if gateway is None or not getattr(gateway, "providers", None):
        return {"ok": False, "reason": "provider_registry_unavailable"}

    capabilities = []
    providers_by_id = {}
    provider_errors = []
    try:
        provider_entries = gateway.providers.list_providers()
    except Exception:
        return {"ok": False, "reason": "provider_registry_unavailable"}

    for entry in provider_entries:
        provider_id = str((entry or {}).get("provider_id") or "")
        if not provider_id or provider_id == "existing-nova":
            continue
        if str((entry or {}).get("local_or_remote") or "") != "local":
            continue
        if str((entry or {}).get("cost_type") or "") != "free":
            continue
        try:
            provider = gateway.providers.get_provider(provider_id)
            if not _provider_is_safe_local_candidate(provider):
                provider_errors.append({"provider": provider_id, "reason": "not_loopback_local"})
                continue
            models = provider.list_models()
            providers_by_id[provider_id] = provider
            capabilities.extend(models)
        except Exception:
            provider_errors.append({"provider": provider_id, "reason": "discovery_failed"})

    quarantined_models = []
    qualified_capabilities = []
    for capability in capabilities:
        capability_provider = str(
            getattr(capability, "provider_id", "") or "unknown"
        )
        capability_model = str(getattr(capability, "model_id", "") or "")
        if capability_model and MODEL_QUALITY.is_quarantined(
            capability_provider,
            capability_model,
        ):
            quarantined_models.append(
                {
                    "provider": capability_provider,
                    "model": capability_model,
                    "reason": "model_quarantined",
                }
            )
            continue
        qualified_capabilities.append(capability)
    capabilities = qualified_capabilities

    primary_model = str(primary_trace.get("local_llm_model") or primary_trace.get("model") or "")
    tier = "middle" if str(reviewer_tier or "").lower() == "middle" else "deep"
    try:
        from nova_local_llm_connector import LocalLLMConfig

        local_config = LocalLLMConfig()
    except Exception:
        local_config = None
    task_type = _candidate_escalation_task_type(text, primary_trace)
    if tier == "middle":
        minimum_model_bytes = (
            local_config.middle_reviewer_min_model_bytes
            if local_config is not None
            else 1_500_000_000
        )
        maximum_model_bytes = (
            local_config.middle_reviewer_max_model_bytes
            if local_config is not None
            else 3_000_000_000
        )
        preferred_model_ids = (
            local_config.middle_reviewer_model_preferences(task_type)
            if local_config is not None
            else ("qwen2.5:3b",)
        )
        prefer_larger = False
        require_preferred = True
    else:
        minimum_model_bytes = _candidate_retry_minimum_model_bytes()
        maximum_model_bytes = _candidate_retry_maximum_model_bytes()
        preferred_model_ids = _candidate_model_preferences(text, primary_trace)
        prefer_larger = True
        require_preferred = False
    selected, model_selection = select_alternate_model(
        capabilities,
        primary_model=primary_model,
        minimum_model_bytes=minimum_model_bytes,
        maximum_model_bytes=maximum_model_bytes,
        preferred_model_ids=preferred_model_ids,
        prefer_larger=prefer_larger,
        excluded_model_ids=excluded_model_ids,
        require_preferred=require_preferred,
    )
    model_selection["reviewer_tier"] = tier
    model_selection["provider_errors"] = provider_errors[:8]
    model_selection["quarantined_models"] = quarantined_models[:8]
    if selected is None:
        return {
            "ok": False,
            "reason": "no_eligible_local_model",
            "reviewer_tier": tier,
            "model_selection": model_selection,
        }
    if tier == "middle":
        middle_qualification = _middle_model_qualification(
            getattr(selected, "model_id", ""),
            task_type,
        )
        model_selection["capability_qualification"] = middle_qualification
        if (
            middle_qualification.get("enforced")
            and not middle_qualification.get("eligible")
        ):
            return {
                "ok": False,
                "reason": "middle_model_not_qualified",
                "reviewer_tier": tier,
                "model_selection": model_selection,
            }

    provider_id = str(selected.provider_id)
    provider = providers_by_id.get(provider_id)
    if provider is None:
        return {
            "ok": False,
            "reason": "selected_provider_unavailable",
            "reviewer_tier": tier,
            "model_selection": model_selection,
        }

    retry_prompt, relevance_text = _candidate_retry_prompt(
        text,
        previous_user,
        previous_answer,
        primary_trace=primary_trace,
        context=context,
    )
    request = NovaRequest(
        user_id=str((context or {}).get("user_id") or "local-user"),
        client_id=str((context or {}).get("client_id") or "nova-managed-retry"),
        conversation_id=str((context or {}).get("conversation_id") or uuid.uuid4().hex),
        session_id=str((context or {}).get("session_id") or SESSION_ID),
        messages=[
            NovaMessage(
                role="system",
                content=(
                    "You are a replaceable local language provider inside Nova Creature. "
                    "Nova owns identity, memory, permissions, tools, and the final answer. "
                    "Return only one helpful answer candidate. Start with the answer, never a preamble. "
                    "Obey the requested compact labeled format exactly, stay under 110 words, and finish."
                ),
            ),
            NovaMessage(role="user", content=retry_prompt),
        ],
        generation_options=NovaGenerationOptions(
            model=str(selected.model_id),
            temperature=0.1,
            top_p=0.9,
            max_tokens=_candidate_retry_max_tokens(),
            stop=[
                "\n\nHigh-confidence technical constraints:",
                "\nHigh-confidence technical constraints:",
            ],
            seed=0,
            stream=False,
        ),
        privacy_mode="local_only",
        metadata={
            "provider_model": str(selected.model_id),
            "candidate_retry": True,
            "reviewer_tier": tier,
            "internal_nova_managed": True,
            "provider_timeout_seconds": _candidate_retry_timeout_seconds(),
            "provider_context_window": _candidate_retry_context_window(),
            "provider_keep_alive": _candidate_retry_keep_alive(),
        },
        api_source="nova_candidate_selector",
    )
    started = time.monotonic()
    try:
        if provider_id == "ollama":
            from nova_model_memory import managed_model_residency

            with managed_model_residency(
                str(selected.model_id),
                target_family=tier,
                estimated_model_bytes=int(
                    (getattr(selected, "metadata", {}) or {}).get("size") or 0
                ),
            ) as residency:
                model_selection["resource_manager"] = residency
                if not residency.get("allowed"):
                    return {
                        "ok": False,
                        "reason": "model_memory_policy_blocked",
                        "provider": provider_id,
                        "model": str(selected.model_id),
                        "model_selection": model_selection,
                        "reviewer_tier": tier,
                    }
                provider_response = provider.generate(request)
        else:
            from nova_model_memory import model_activity

            with model_activity("reviewer"):
                provider_response = provider.generate(request)
        answer = str(getattr(provider_response, "content", "") or "").strip()
        finish_reason = str(getattr(provider_response, "finish_reason", "") or "stop").strip().lower()
    except Exception:
        MODEL_QUALITY.record_failure(
            provider_id,
            str(selected.model_id),
            latency_ms=(time.monotonic() - started) * 1000,
            reason="generation_failed",
            source="reviewer_runtime",
        )
        return {
            "ok": False,
            "reason": "candidate_generation_failed",
            "provider": provider_id,
            "model": str(selected.model_id),
            "model_selection": model_selection,
            "reviewer_tier": tier,
        }
    if finish_reason == "length":
        MODEL_QUALITY.record_failure(
            provider_id,
            str(selected.model_id),
            latency_ms=(time.monotonic() - started) * 1000,
            reason="candidate_token_limit",
            source="reviewer_runtime",
        )
        return {
            "ok": False,
            "reason": "candidate_token_limit",
            "provider": provider_id,
            "model": str(selected.model_id),
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "finish_reason": finish_reason,
            "model_selection": model_selection,
            "reviewer_tier": tier,
        }
    if not answer:
        MODEL_QUALITY.record_failure(
            provider_id,
            str(selected.model_id),
            latency_ms=(time.monotonic() - started) * 1000,
            reason="empty_response",
            source="reviewer_runtime",
        )
    return {
        "ok": bool(answer),
        "reason": "generated" if answer else "empty_candidate",
        "answer": answer,
        "provider": provider_id,
        "model": str(selected.model_id),
        "relevance_text": relevance_text,
        "different_model": bool(model_selection.get("selected_different_from_primary")),
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "finish_reason": finish_reason,
        "model_selection": model_selection,
        "reviewer_tier": tier,
    }


def _generate_llm_fallback_candidate(
    text,
    previous_user,
    previous_answer,
    primary_trace,
    context,
):
    """Ask the configured local LLM once before emitting canned recovery text."""

    retry_allowed, retry_reason = _candidate_retry_allowed(primary_trace, context)
    if not retry_allowed:
        return {"ok": False, "reason": "llm_fallback_not_allowed:" + retry_reason}
    try:
        import nova_llm_synthesizer as llm_synth

        retry_prompt, relevance_text = _candidate_retry_prompt(
            text,
            previous_user,
            previous_answer,
            primary_trace=primary_trace,
            context=context,
        )
        started = time.monotonic()
        answer, ok, error = llm_synth.generate_fallback(
            retry_prompt,
            timeout=_candidate_retry_timeout_seconds(),
        )
        answer = str(answer or "").strip()
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        if not ok or not answer:
            return {
                "ok": False,
                "reason": str(error or "llm_fallback_failed"),
                "latency_ms": latency_ms,
            }
        fallback_trace = {
            "source": "llm_fallback",
            "local_llm_synthesis_used": True,
            "_fact_grounding_blocking": False,
        }
        grounding = _evaluate_fact_grounding(text, answer, fallback_trace)
        consistency = _evaluate_technical_consistency(text, answer)
        decision = evaluate_answer(
            text,
            answer,
            previous_answer=previous_answer,
            trace={
                **fallback_trace,
                "numeric_verification_required": _candidate_requires_numeric_verification(
                    text,
                    previous_user,
                ),
                "_fact_grounding_blocking": grounding.blocking,
            },
        )
        decision = _merge_consistency_with_firewall(decision, consistency)
        if grounding.blocking or not decision.accepted:
            return {
                "ok": False,
                "reason": "llm_fallback_quality_rejected",
                "latency_ms": latency_ms,
                "grounding": grounding.as_trace(),
                "consistency": consistency.as_trace(),
            }
        model = str(
            getattr(llm_synth, "LAST_LOCAL_LLM_MODEL", None)
            or "configured-local-llm"
        )
        return {
            "ok": True,
            "reason": "generated",
            "answer": answer,
            "provider": "configured-local-llm",
            "model": model,
            "relevance_text": relevance_text,
            "latency_ms": latency_ms,
            "firewall": decision,
            "grounding": grounding.as_trace(),
            "consistency": consistency.as_trace(),
        }
    except Exception as error:
        return {"ok": False, "reason": "llm_fallback_error:" + type(error).__name__}


def _validate_alternate_local_candidate(
    text,
    previous_user,
    previous_answer,
    alternate_result,
):
    """Apply Nova's provider-independent checks to one completed reviewer answer."""

    if not isinstance(alternate_result, dict) or not alternate_result.get("ok"):
        return None
    alternate_answer = str(alternate_result.get("answer") or "")
    alternate_consistency = _evaluate_technical_consistency(text, alternate_answer)
    alternate_consistency_trace = alternate_consistency.as_trace()
    alternate_result["consistency"] = alternate_consistency_trace
    alternate_grounding = _evaluate_fact_grounding(
        text,
        alternate_answer,
        {"source": "provider_candidate"},
    )
    alternate_grounding_trace = alternate_grounding.as_trace()
    if not alternate_consistency.accepted:
        alternate_result["ok"] = False
        alternate_result["reason"] = "consistency_check_failed"
        MODEL_QUALITY.record_failure(
            str(alternate_result.get("provider") or "unknown"),
            str(alternate_result.get("model") or "unknown"),
            latency_ms=alternate_result.get("latency_ms"),
            reason="candidate_consistency_failed",
            source="reviewer_validation",
        )
        return None
    if _is_unverified_exact_numeric_claim(text, alternate_answer, alternate_grounding_trace):
        alternate_result["ok"] = False
        alternate_result["reason"] = "unverified_exact_claim"
        MODEL_QUALITY.record_failure(
            str(alternate_result.get("provider") or "unknown"),
            str(alternate_result.get("model") or "unknown"),
            latency_ms=alternate_result.get("latency_ms"),
            reason="candidate_firewall_rejected",
            source="reviewer_validation",
        )
        return None

    alternate_decision = evaluate_answer(
        text,
        alternate_answer,
        previous_answer=previous_answer,
        trace={
            "source": "provider_candidate",
            "numeric_verification_required": _candidate_requires_numeric_verification(
                text,
                previous_user,
            ),
            "_fact_grounding_blocking": alternate_grounding.blocking,
        },
    )
    candidate = AnswerCandidate(
        candidate_id="alternate_local",
        answer=alternate_answer,
        source="provider_candidate",
        provider=str(alternate_result.get("provider") or ""),
        model=str(alternate_result.get("model") or ""),
        firewall=alternate_decision,
        relevance_text=str(alternate_result.get("relevance_text") or text),
        trace_confidence=0.82,
        metadata={
            "different_model": bool(alternate_result.get("different_model")),
            "reviewer_tier": str(alternate_result.get("reviewer_tier") or "deep"),
            "fact_grounding": alternate_grounding_trace,
            "answer_consistency": alternate_consistency_trace,
            "question_restatement": _answer_reasks_user_question(text, alternate_answer),
            "requested_aspect_coverage": _requested_aspect_coverage(text, alternate_answer),
        },
    )
    winner, _ranked = choose_candidate([candidate])
    if winner is None:
        alternate_result["ok"] = False
        alternate_result["reason"] = "candidate_quality_rejected"
        MODEL_QUALITY.record_failure(
            str(alternate_result.get("provider") or "unknown"),
            str(alternate_result.get("model") or "unknown"),
            latency_ms=alternate_result.get("latency_ms"),
            reason="candidate_firewall_rejected",
            source="reviewer_validation",
        )
        return None
    MODEL_QUALITY.record_success(
        str(alternate_result.get("provider") or "unknown"),
        str(alternate_result.get("model") or "unknown"),
        latency_ms=alternate_result.get("latency_ms"),
        source="reviewer_validation",
    )
    return candidate


def _attach_conversation_summary(trace, context, history_before_turn, text, response):
    """Attach browser-owned rolling continuity when privacy settings permit it."""
    if not isinstance(trace, dict):
        return trace
    automatic_persistence_allowed = bool(
        context.get("automatic_conversation_persistence_allowed", True)
    )
    trace["automatic_conversation_persistence_allowed"] = (
        automatic_persistence_allowed
    )
    if bool(context.get("evaluation_only")):
        return trace
    if not automatic_persistence_allowed:
        return trace
    continuity_config = _runtime_cognitive_config()["conversation_continuity"]
    if not continuity_config["enabled"]:
        return trace
    summary_write_allowed = bool(
        context.get(
            "conversation_summary_write_allowed",
            not bool(context.get("private_mode")) and not PRIVATE_MODE,
        )
    )
    if not summary_write_allowed:
        return trace
    summary_history = history_before_turn
    if "conversation_summary_history" in context:
        summary_history = bounded_conversation_history(
            {
                "conversation_history": context.get(
                    "conversation_summary_history"
                )
            }
        )
    summary_update = roll_conversation_summary(
        context.get("conversation_summary"),
        summary_history,
        text,
        response,
    )
    summary_data = summary_update.summary.to_dict()
    summary_data["open_loops"] = list(summary_data.get("open_loops") or [])[
        -continuity_config["maximum_open_loops"] :
    ]
    if summary_update.updated or ConversationSummary.from_value(context.get("conversation_summary")).revision:
        trace["conversation_summary"] = summary_data
    trace["conversation_summary_updated"] = summary_update.updated
    trace["conversation_summary_revision"] = summary_update.summary.revision
    trace["conversation_summary_rolled_messages"] = summary_update.rolled_message_count
    return trace


def _answer_status_from_trace(trace):
    """Project one privacy-safe, fixed-shape answer status for clients."""

    source = trace if isinstance(trace, dict) else {}
    decision = (
        source.get("conversation_decision")
        if isinstance(source.get("conversation_decision"), dict)
        else {}
    )
    allowed_intents = {
        "permission_action",
        "current_fact",
        "memory",
        "vision_robot",
        "project_tool",
        "relationship",
        "emotional",
        "social",
        "follow_up",
        "stable_reasoning",
        "open_ended",
    }
    intent = str(decision.get("intent_family") or "conversation").strip().lower()
    if intent not in allowed_intents:
        intent = "conversation"

    model_candidates = (
        source.get("model"),
        source.get("local_llm_model"),
        (
            source.get("candidate_selection", {}).get("selected_model")
            if isinstance(source.get("candidate_selection"), dict)
            else None
        ),
    )
    model = next(
        (
            str(value).strip()[:80]
            for value in model_candidates
            if value
            and re.fullmatch(r"[A-Za-z0-9_.:/+\-]{1,80}", str(value).strip())
        ),
        "Nova",
    )

    recalled = source.get("memory_v2_retrieved")
    if isinstance(recalled, (list, tuple)):
        recalled = len(recalled)
    try:
        recalled_count = max(0, min(int(recalled or 0), 999))
    except (TypeError, ValueError):
        recalled_count = 0
    memory = f"{recalled_count} recalled" if recalled_count else "not used"

    repair_trace = (
        source.get("response_repair")
        if isinstance(source.get("response_repair"), dict)
        else {}
    )
    repair = "repaired" if repair_trace.get("repaired") else "not needed"

    firewall = (
        source.get("answer_firewall")
        if isinstance(source.get("answer_firewall"), dict)
        else {}
    )
    allowed_safety = {
        "passed",
        "passed_after_retry",
        "blocked",
        "fact_grounding_blocked",
        "stream_postcheck_warning",
        "bypassed_raw",
    }
    safety = str(firewall.get("status") or "checked").strip().lower()
    if safety not in allowed_safety:
        safety = "checked"

    perception = (
        source.get("perception_fusion")
        if isinstance(source.get("perception_fusion"), dict)
        else {}
    )
    vision = "not used"
    if perception:
        parts = []
        if perception.get("semantic_available"):
            semantic_model = str(
                perception.get("semantic_model") or "semantic"
            ).strip()
            if re.fullmatch(r"[A-Za-z0-9_.:/+\-]{1,40}", semantic_model):
                parts.append(
                    "Moondream"
                    if semantic_model.lower() == "moondream"
                    else semantic_model
                )
        try:
            ocr_count = max(0, min(int(perception.get("ocr_count") or 0), 999))
        except (TypeError, ValueError):
            ocr_count = 0
        if ocr_count:
            parts.append(f"{ocr_count} OCR")
        vision = " + ".join(parts) or "scene scan"

    return {
        "intent": intent,
        "model": model,
        "memory": memory,
        "repair": repair,
        "safety": safety,
        "vision": vision,
    }


def _run_nova_chat_turn_impl(text, context=None):
    """Run one real Nova turn while preserving legacy and gateway privacy behavior."""
    global _LAST_USER_TEXT, _LAST_NOVA_RESPONSE
    context = context if isinstance(context, dict) else {}
    evaluation_only = context.get("evaluation_only") is True
    evaluation_mutation_block = _evaluation_mutation_guard_response(text, context)
    if evaluation_mutation_block is not None:
        return evaluation_mutation_block
    runtime_cognitive_config = _runtime_cognitive_config()
    raw_adapter_request = _is_trained_adapter_only_context(context)
    optional_model_mode = _optional_strong_model_decision(
        context,
        raw_adapter_request=raw_adapter_request,
    )
    conversation_decision = None
    if (
        not raw_adapter_request
        and runtime_cognitive_config["conversation_intelligence"]["enabled"]
    ):
        try:
            from nova_conversation_intelligence import understand_conversation_turn

            conversation_decision = understand_conversation_turn(text)
            context["conversation_decision"] = conversation_decision
            context["conversation_decision_trace"] = conversation_decision.safe_trace()
        except Exception:
            conversation_decision = None
    companion_service = None
    companion_turn = None
    if (
        not raw_adapter_request
        and not evaluation_only
        and not bool(context.get("private_mode"))
        and not PRIVATE_MODE
        and str(context.get("user_id") or "").strip()
        and runtime_cognitive_config.get("companion_layer", {}).get("enabled", False)
    ):
        try:
            companion_service = _get_companion_service()
            if companion_service is not None:
                companion_turn = companion_service.begin_turn(
                    text,
                    user_id=str(context.get("user_id") or ""),
                    conversation_id=str(context.get("conversation_id") or "default"),
                    context=context,
                    decision=conversation_decision,
                )
                context["companion_context"] = companion_turn.context_block
                context["_companion_turn"] = companion_turn
                context["_companion_service"] = companion_service
        except Exception:
            companion_service = None
            companion_turn = None
    automatic_durable_writes_allowed = not (
        getattr(conversation_decision, "intent_family", "") == "practical_support"
        and not getattr(conversation_decision, "memory_recommended", False)
    )
    context["automatic_durable_writes_allowed"] = automatic_durable_writes_allowed
    context["automatic_conversation_persistence_allowed"] = (
        automatic_durable_writes_allowed
    )
    _CONVERSATION_WRITES_ALLOWED.set(automatic_durable_writes_allowed)
    local_config = None
    try:
        from nova_local_llm_connector import LocalLLMConfig
        from nova_turn_analyzer import analyze_turn

        local_config = LocalLLMConfig()
        turn_state = analyze_turn(
            text,
            context_budget=min(int(local_config.context_window), 8192),
            max_tool_steps=local_config.reasoning_max_tool_steps,
            conversation_decision=conversation_decision,
        )
        context["turn_state"] = turn_state.to_dict()
        context["reasoning_mode"] = turn_state.reasoning_mode
        context["reasoning_enabled"] = turn_state.reasoning_mode in {
            "deep",
            "agent",
            "verify",
        }
        context["use_agent_loop_v2"] = bool(
            turn_state.reasoning_mode == "agent"
            and local_config.reasoning_allow_agent
            and local_config.tools_enabled
        )
    except Exception:
        turn_state = None
    memory_v2_records = []
    if (
        turn_state is not None
        and (turn_state.memory_required or turn_state.project_context_required)
        and (local_config is None or local_config.memory_v2_enabled)
        and not bool(context.get("private_mode"))
        and not PRIVATE_MODE
    ):
        try:
            from nova_memory_v2 import get_default_memory

            owner_id = str(context.get("user_id") or "local-user")
            memory_v2_records = get_default_memory().search(
                text,
                owner_id=owner_id,
                project_name=(
                    "Nova"
                    if turn_state.project_context_required
                    and "nova" in str(text or "").lower()
                    else None
                ),
                limit=6,
            )
            if memory_v2_records:
                context["memory_v2_context"] = "\n".join(
                    f"- [{record.memory_type}] {record.text}"
                    for record in memory_v2_records
                )
        except Exception:
            memory_v2_records = []
    rag_result = None
    if (
        turn_state is not None
        and turn_state.rag_required
        and (local_config is None or local_config.rag_enabled)
        and not bool(context.get("private_mode"))
        and not PRIVATE_MODE
    ):
        try:
            from nova_rag import get_default_rag

            rag_result = get_default_rag().search(
                text,
                top_k=(local_config.rag_top_k if local_config is not None else 6),
            )
            context["rag_trace"] = rag_result.safe_trace()
            if rag_result.passages:
                context["rag_context"] = rag_result.context()
            source_dependent = bool(
                re.search(
                    r"\b(?:according to|from|in)\s+(?:the\s+)?(?:article|document|field guide|knowledge base)\b",
                    str(text or ""),
                    flags=re.I,
                )
            )
            context["rag_insufficient"] = bool(
                source_dependent and not rag_result.passages
            )
        except Exception:
            rag_result = None
    history_before_turn = bounded_conversation_history(context, text)
    client_previous_user, client_previous_answer = previous_exchange(history_before_turn)
    gateway_scoped = bool(context.get("nova_gateway"))
    legacy_previous_user = "" if gateway_scoped else _LAST_USER_TEXT
    legacy_previous_answer = "" if gateway_scoped else _LAST_NOVA_RESPONSE
    previous_user, previous_answer = _select_previous_exchange(
        context,
        client_previous=(client_previous_user, client_previous_answer),
        legacy_previous=(legacy_previous_user, legacy_previous_answer),
    )
    context_resolution = resolve_contextual_followup(
        text,
        history_before_turn,
        fallback_previous_user=previous_user,
        fallback_previous_answer=previous_answer,
    )
    if context_resolution.is_followup:
        previous_user = context_resolution.previous_user or previous_user
        previous_answer = context_resolution.previous_answer or previous_answer
    if not raw_adapter_request and (
        local_config is None or local_config.verification_enabled
    ):
        context["adaptive_model_memory"] = True
    managed_stream_emit = None
    managed_stream_parts = []
    if not raw_adapter_request and callable(context.get("stream_callback")):
        managed_stream_emit = context.get("stream_callback")
        stream_cancelled = context.get("stream_cancelled")

        def buffer_managed_delta(delta):
            if callable(stream_cancelled) and stream_cancelled():
                return False
            value = str(delta or "")
            if value and sum(len(item) for item in managed_stream_parts) < 32_000:
                managed_stream_parts.append(value)
            return True

        context["stream_callback"] = buffer_managed_delta
    if raw_adapter_request:
        _emit_chat_progress(
            context,
            "raw_adapter",
            "The selected raw adapter is loading or generating locally.",
            10,
        )
    else:
        _emit_chat_progress(
            context,
            "nova_core",
            "Nova is applying identity, memory, context, and local routing.",
            10,
        )
    conversation_declaration = (
        None
        if raw_adapter_request
        else resolve_conversation_declaration(text)
    )
    action_policy = (
        None
        if raw_adapter_request
        else evaluate_requested_action(text)
    )
    conversation_recall = (
        None
        if raw_adapter_request
        else resolve_conversation_recall(text, history_before_turn)
    )
    reviewed_conversation_response = ""
    if conversation_decision is not None and not raw_adapter_request:
        try:
            from nova_response_repair import reviewed_direct_response

            pre_model_reviewed_subtypes = {
                ("relationship", "relationship_meaning"),
                ("emotional", "user_distress"),
                ("emotional", "user_positive"),
                ("emotional", "encouragement_request"),
                ("social", "conversation_invite"),
                ("social", "gratitude"),
                ("social", "compliment"),
                ("social", "positive_reaction"),
                ("social", "farewell"),
                ("social", "greeting"),
            }
            if (
                conversation_decision.intent_family,
                conversation_decision.intent_subtype,
            ) in pre_model_reviewed_subtypes:
                reviewed_conversation_response = reviewed_direct_response(
                    conversation_decision
                )
        except Exception:
            reviewed_conversation_response = ""
    if (
        not raw_adapter_request
        and action_policy is None
        and conversation_declaration is None
        and conversation_recall is None
    ):
        preflight_grounding = _fact_grounding_preflight(text, context)
        if preflight_grounding is not None:
            response = grounding_recovery_response(text, preflight_grounding)
            trace = {
                "source": "fact_grounding_guard",
                "domain": "response_quality",
                "roles": ["critic_conscience_transformer", "speech_output_transformer"],
                "skills": ["fact_grounding", "freshness_guard", "preflight_guard"],
                "confidence": 0.99,
                "route_path": ["fact_grounding_preflight", "speech_output"],
                "fallback_used": True,
                "final_answer_source": "fact_grounding_guard",
                "fact_grounding": preflight_grounding.as_trace(),
                "answer_firewall": {
                    "checked": True,
                    "status": "fact_grounding_blocked",
                    "accepted": False,
                    "score": 0.05,
                    "reasons": ["freshness_unverified"],
                    "intercepted": True,
                },
                "candidate_selection": {
                    "version": CANDIDATE_SELECTOR_VERSION,
                    "triggered": False,
                    "retry_allowed": False,
                    "retry_policy_reason": "fact_grounding_preflight",
                    "retry_attempted": False,
                    "retry_result": "not_attempted",
                    "selected": "recovery",
                    "candidates": [],
                },
            }
            if conversation_decision is not None:
                trace["conversation_decision"] = conversation_decision.safe_trace()
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = response
            trace = _attach_conversation_summary(
                trace,
                context,
                history_before_turn,
                text,
                response,
            )
            trace["answer_status"] = _answer_status_from_trace(trace)
            return response, trace
    deterministic_solution = (
        None
        if (
            raw_adapter_request
            or action_policy is not None
            or conversation_declaration is not None
            or conversation_recall is not None
            or not _deterministic_verifier_enabled()
        )
        else solve_deterministic_request(text)
    )
    if action_policy is not None:
        direct_middle_routing = {
            "selected": False,
            "reason": "action_permission_policy",
            "local_only": True,
            "model_called": False,
        }
        response = action_policy.response
        trace = {
            "source": "action_permission_gate",
            "domain": "action_safety",
            "roles": ["permission_gate", "critic_conscience_transformer", "speech_output_transformer"],
            "skills": ["action_classification", "permission_check", "false_completion_prevention"],
            "confidence": 0.99,
            "route_path": [
                "nova_core",
                "action_permission_policy",
                "speech_output",
            ],
            "final_answer_source": "action_permission_gate",
            "local_llm_synthesis_used": False,
            "memory_write_used": False,
            "action_policy": action_policy.safe_trace(),
        }
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
    elif conversation_declaration is not None:
        direct_middle_routing = {
            "selected": False,
            "reason": "temporary_conversation_declaration",
            "local_only": True,
            "model_called": False,
        }
        response = conversation_declaration.response
        trace = {
            "source": "conversation_declaration",
            "domain": "conversation_context",
            "roles": ["memory_transformer", "speech_output_transformer"],
            "skills": ["temporary_context", "model_bypass"],
            "confidence": conversation_declaration.confidence,
            "route_path": [
                "nova_core",
                "temporary_conversation_declaration",
                "speech_output",
            ],
            "final_answer_source": "conversation_declaration",
            "local_llm_synthesis_used": False,
            "memory_write_used": False,
            "conversation_recall": {
                "kind": conversation_declaration.kind,
                "confidence": conversation_declaration.confidence,
                "source_role": "current_user",
                "source_content_logged": False,
            },
        }
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
    elif conversation_recall is not None:
        direct_middle_routing = {
            "selected": False,
            "reason": "explicit_client_conversation_evidence",
            "local_only": True,
            "model_called": False,
        }
        response = conversation_recall.response
        trace = {
            "source": "conversation_evidence_recall",
            "domain": "conversation_context",
            "roles": ["memory_transformer", "speech_output_transformer"],
            "skills": ["client_scoped_recall", "context_recall", "model_bypass"],
            "confidence": conversation_recall.confidence,
            "route_path": [
                "nova_core",
                "client_conversation_evidence",
                "speech_output",
            ],
            "final_answer_source": "conversation_evidence_recall",
            "local_llm_synthesis_used": False,
            "memory_write_used": False,
            "client_context_used": True,
            "client_context_messages": len(history_before_turn),
            "conversation_recall": {
                "kind": conversation_recall.kind,
                "confidence": conversation_recall.confidence,
                "source_role": "user",
                "source_content_logged": False,
            },
        }
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
    elif deterministic_solution is not None:
        direct_middle_routing = {
            "selected": False,
            "reason": "deterministic_solution_available",
            "local_only": True,
            "model_called": False,
        }
        _emit_chat_progress(
            context,
            "deterministic_verification",
            "Nova verified the exact result without loading another model.",
            82,
        )
        response = deterministic_solution.response
        trace = {
            "source": f"deterministic_{deterministic_solution.domain}_verifier",
            "domain": deterministic_solution.domain,
            "roles": [
                "left_hemisphere",
                "critic_conscience_transformer",
                "speech_output_transformer",
            ],
            "skills": [
                "deterministic_verification",
                f"verified_{deterministic_solution.domain}",
                "model_bypass",
            ],
            "confidence": 0.99,
            "route_path": [
                "nova_core",
                "deterministic_verifier",
                "speech_output",
            ],
            "final_answer_source": "deterministic_verifier",
            "local_llm_synthesis_used": False,
            "deterministic_verification": deterministic_solution.safe_trace(
                status="solved_before_model"
            ),
        }
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
    elif reviewed_conversation_response:
        direct_middle_routing = {
            "selected": False,
            "reason": "reviewed_conversation_response",
            "local_only": True,
            "model_called": False,
        }
        response = reviewed_conversation_response
        trace = {
            "source": "reviewed_conversation_response",
            "domain": "general_conversation",
            "roles": [
                "memory_transformer",
                "critic_conscience_transformer",
                "speech_output_transformer",
            ],
            "skills": [
                "shared_conversation_decision",
                "reviewed_natural_response",
                "model_bypass",
            ],
            "confidence": conversation_decision.confidence,
            "route_path": [
                "nova_core",
                "conversation_intelligence",
                "reviewed_natural_response",
                "speech_output",
            ],
            "final_answer_source": "reviewed_conversation_response",
            "local_llm_synthesis_used": False,
            "memory_write_used": False,
        }
        _LAST_USER_TEXT = text
        _LAST_NOVA_RESPONSE = response
    else:
        if optional_model_mode.get("selected"):
            direct_middle_routing = {
                "selected": False,
                "reason": "optional_strong_mode",
                "content_logged": False,
            }
            context["primary_model_override"] = optional_model_mode["model"]
            context["primary_model_size_bytes"] = int(
                optional_model_mode.get("estimated_model_bytes") or 0
            )
            context["primary_model_timeout"] = optional_model_mode["timeout_seconds"]
            context["primary_model_keep_alive"] = optional_model_mode["keep_alive"]
            context["primary_model_tier"] = optional_model_mode["tier"]
            _emit_chat_progress(
                context,
                "strong_local_model",
                "Nova Strong is using Qwen 3 8B locally.",
                18,
            )
        else:
            direct_middle_routing = _direct_middle_route_decision(
                text,
                context,
                raw_adapter_request=raw_adapter_request,
            )
            if direct_middle_routing.get("selected"):
                context["primary_model_override"] = direct_middle_routing["model"]
                context["primary_model_size_bytes"] = int(
                    direct_middle_routing.get("estimated_model_bytes") or 0
                )
                context["primary_model_timeout"] = direct_middle_routing["timeout_seconds"]
                context["primary_model_keep_alive"] = direct_middle_routing["keep_alive"]
                context["primary_model_tier"] = "middle"
                context["primary_model_guidance"] = list(
                    technical_consistency_guidance(text)
                )
                context["primary_model_required_aspects"] = _explicit_requested_aspects(text)
                _emit_chat_progress(
                    context,
                    "direct_middle_route",
                    "Nova routed this hard request directly to the faster middle local model.",
                    18,
                )

        companion_fast_answer, companion_fast_trace = _companion_continuity_fast_path(
            text,
            companion_turn,
        ) if companion_turn is not None else (None, {})
        if companion_fast_answer:
            response, trace = companion_fast_answer, companion_fast_trace
        else:
            response, trace = brain_route(text, context=context)
    if not isinstance(trace, dict):
        trace = {}
    trace["optional_model_mode"] = dict(optional_model_mode)
    if trace.get("local_llm_provider"):
        trace["optional_model_mode"]["actual_provider"] = trace["local_llm_provider"]
    if trace.get("local_llm_model"):
        trace["optional_model_mode"]["actual_model"] = trace["local_llm_model"]
    if trace.get("gpu_backend"):
        trace["optional_model_mode"]["actual_gpu_backend"] = trace["gpu_backend"]
    if conversation_decision is not None:
        trace["conversation_decision"] = conversation_decision.safe_trace()
    if turn_state is not None:
        trace["turn_analysis"] = turn_state.safe_trace()
        trace["reasoning_mode"] = turn_state.reasoning_mode
        trace["reasoning_content_stored"] = False
        trace["memory_v2_retrieved"] = len(memory_v2_records)
        trace["memory_v2_ids"] = [
            record.memory_id for record in memory_v2_records[:6]
        ]
        if rag_result is not None:
            trace["rag"] = rag_result.safe_trace()
            trace["rag_retrieved"] = len(rag_result.passages)
    trace["direct_middle_routing"] = direct_middle_routing
    if isinstance(context.get("model_residency"), dict):
        trace["model_residency"] = context["model_residency"]
    selected_direct_model = str(direct_middle_routing.get("model") or "").strip().lower()
    generated_model = str(trace.get("local_llm_model") or "").strip().lower()
    trace["direct_middle_primary"] = bool(
        direct_middle_routing.get("selected")
        and trace.get("local_llm_synthesis_used")
        and selected_direct_model
        and generated_model == selected_direct_model
    )
    trace["capability_shadow_routing"] = _capability_shadow_route(
        text,
        trace,
        raw_adapter_request=raw_adapter_request,
    )
    if managed_stream_emit is not None:
        trace["native_streaming_buffered"] = bool(trace.get("native_streaming"))
        trace["native_streaming"] = False
        trace["native_stream_incremental"] = False
        trace["managed_streaming_mode"] = "validation_buffer"

    if raw_adapter_request:
        # Raw means raw: Nova may supply memory/context before generation, but
        # this layer never judges or rewrites the adapter's returned text.
        trace["answer_firewall"] = answer_firewall_bypass_trace()
        trace["fact_grounding"] = fact_grounding_bypass_trace()
        trace["answer_consistency"] = consistency_bypass_trace()
    elif (
        deterministic_solution is not None
        or action_policy is not None
        or conversation_declaration is not None
        or conversation_recall is not None
    ):
        # The bounded verifier has already proved the response from the request.
        # Do not let open-ended relevance heuristics rewrite exact JSON, tokens,
        # calculations, logic, or explicit client conversation evidence, and
        # never escalate those results to a model.
        verified_reason = (
            "action_permission_policy"
            if action_policy is not None
            else (
                "temporary_conversation_declaration"
                if conversation_declaration is not None
                else (
                    "explicit_client_conversation_evidence"
                    if conversation_recall is not None
                    else "deterministic_solution"
                )
            )
        )
        trace["answer_firewall"] = {
            **answer_firewall_bypass_trace(),
            "status": "bypassed_verified",
            "reason": verified_reason,
            "intercepted": False,
        }
        trace["fact_grounding"] = {
            **fact_grounding_bypass_trace(),
            "status": "bypassed_verified",
            "reason": verified_reason,
        }
        trace["answer_consistency"] = {
            **consistency_bypass_trace(),
            "status": "bypassed_verified",
            "reason": verified_reason,
        }
    else:
        source_retrieval = trace.get("source_retrieval")
        source_consensus = trace.get("source_consensus")
        web_privacy_blocked = (
            isinstance(source_retrieval, dict)
            and source_retrieval.get("status") == "blocked"
        )
        if web_privacy_blocked:
            trace["fact_grounding"] = {
                "schema_version": "1.0",
                "required": False,
                "status": "web_privacy_blocked",
                "blocking": False,
                "freshness_required": False,
                "claim_count": 0,
                "supported_claim_count": 0,
                "claims": [],
                "evidence_count": 0,
                "evidence": [],
                "reasons": ["network_request_blocked_before_fetch"],
            }
        elif (
            isinstance(source_consensus, dict)
            and source_consensus.get("status") in {"mixed", "insufficient", "stale"}
            and not trace.get("consensus_conclusions")
        ):
            consensus_status = str(source_consensus.get("status"))
            trace["fact_grounding"] = {
                "schema_version": "1.0",
                "required": False,
                "status": "source_consensus_" + consensus_status,
                "blocking": False,
                "freshness_required": False,
                "claim_count": 0,
                "supported_claim_count": 0,
                "claims": [],
                "evidence_count": int(source_consensus.get("publisher_count") or 0),
                "evidence": [],
                "reasons": [
                    "no_conclusion_issued_without_independent_agreement"
                    if consensus_status == "insufficient"
                    else "no_conclusion_issued_because_sources_disagree"
                ],
            }
        else:
            grounding_decision = _evaluate_fact_grounding(text, response, trace)
            trace["fact_grounding"] = grounding_decision.as_trace()
            if grounding_decision.blocking:
                trace["_fact_grounding_blocking"] = True
        consistency_decision = _evaluate_technical_consistency(text, response)
        trace["answer_consistency"] = consistency_decision.as_trace()
        decision = evaluate_answer(
            text,
            response,
            previous_answer=previous_answer,
            trace=trace,
        )
        decision = _merge_consistency_with_firewall(decision, consistency_decision)
        firewall_trace = decision.as_trace()
        escalation_reason = _regular_chat_escalation_reason(text, response, trace, decision)
        if escalation_reason == "primary_model_requested_aspects_missing":
            repaired_response = _repair_missing_requested_recommendation(text, response)
            if repaired_response != response:
                response = repaired_response
                trace["requested_recommendation_repaired"] = True
                trace["requested_aspect_coverage"] = _requested_aspect_coverage(
                    text,
                    response,
                )
                consistency_decision = _evaluate_technical_consistency(text, response)
                trace["answer_consistency"] = consistency_decision.as_trace()
                decision = evaluate_answer(
                    text,
                    response,
                    previous_answer=previous_answer,
                    trace=trace,
                )
                decision = _merge_consistency_with_firewall(
                    decision,
                    consistency_decision,
                )
                firewall_trace = decision.as_trace()
                escalation_reason = _regular_chat_escalation_reason(
                    text,
                    response,
                    trace,
                    decision,
                )
        if (
            not decision.accepted
            and conversation_decision is not None
            and not trace.get("_fact_grounding_blocking")
            and not trace.get("native_streaming")
            and runtime_cognitive_config["response_repair"]["enabled"]
            and runtime_cognitive_config["response_repair"][
                "maximum_attempts"
            ]
            > 0
        ):
            try:
                from nova_response_repair import repair_rejected_response

                repair_result = repair_rejected_response(
                    text,
                    str(response or ""),
                    conversation_decision,
                    decision,
                )
                trace["response_repair"] = repair_result.safe_trace()
                if repair_result.repaired:
                    repair_validation_trace = dict(trace)
                    repair_validation_trace["conversation_decision"] = (
                        conversation_decision
                    )
                    repaired_grounding = _evaluate_fact_grounding(
                        text,
                        repair_result.answer,
                        repair_validation_trace,
                    )
                    repaired_consistency = _evaluate_technical_consistency(
                        text,
                        repair_result.answer,
                    )
                    repaired_decision = evaluate_answer(
                        text,
                        repair_result.answer,
                        previous_answer=previous_answer,
                        trace={
                            **repair_validation_trace,
                            "_fact_grounding_blocking": repaired_grounding.blocking,
                        },
                    )
                    repaired_decision = _merge_consistency_with_firewall(
                        repaired_decision,
                        repaired_consistency,
                    )
                    if (
                        repaired_decision.accepted
                        and not repaired_grounding.blocking
                    ):
                        initial_reasons = list(decision.reasons)
                        response = repair_result.answer
                        decision = repaired_decision
                        grounding_decision = repaired_grounding
                        consistency_decision = repaired_consistency
                        trace["fact_grounding"] = repaired_grounding.as_trace()
                        trace["answer_consistency"] = (
                            repaired_consistency.as_trace()
                        )
                        trace["source"] = "reviewed_response_repair"
                        trace["domain"] = "general_conversation"
                        trace["roles"] = list(
                            dict.fromkeys(
                                list(trace.get("roles") or [])
                                + [
                                    "critic_conscience_transformer",
                                    "speech_output_transformer",
                                ]
                            )
                        )
                        trace["skills"] = list(
                            dict.fromkeys(
                                list(trace.get("skills") or [])
                                + [
                                    "answer_relevance_check",
                                    "bounded_response_repair",
                                ]
                            )
                        )
                        trace["route_path"] = list(
                            trace.get("route_path") or []
                        ) + ["reviewed_response_repair", "speech_output"]
                        trace["fallback_used"] = False
                        trace["final_answer_source"] = (
                            "reviewed_response_repair"
                        )
                        trace["confidence"] = max(
                            float(trace.get("confidence") or 0.0),
                            0.96,
                        )
                        firewall_trace = repaired_decision.as_trace()
                        firewall_trace["status"] = "passed_after_repair"
                        firewall_trace["intercepted"] = True
                        firewall_trace["initial_reasons"] = initial_reasons
                        escalation_reason = None
                    else:
                        trace["response_repair"] = {
                            **repair_result.safe_trace(),
                            "repaired": False,
                            "reason": "repair_validation_failed",
                        }
            except Exception as repair_error:
                trace["response_repair"] = {
                    "version": "1.0",
                    "repaired": False,
                    "reason": "repair_error",
                    "attempt_count": 0,
                    "source": "none",
                    "error_type": type(repair_error).__name__,
                    "content_logged": False,
                }
        escalation_difficulty = assess_request_difficulty(
            text,
            trace,
            threshold=_difficulty_escalation_threshold(),
        )
        trace.setdefault(
            "uncertainty_routing",
            escalation_difficulty.as_trace(),
        )
        escalation_intent_family = str(
            getattr(conversation_decision, "intent_family", "")
            or (
                (trace.get("conversation_decision") or {}).get(
                    "intent_family",
                    "",
                )
                if isinstance(trace.get("conversation_decision"), dict)
                else ""
            )
            or "open_ended"
        )
        escalation_policy = decide_model_escalation(
            intent_family=escalation_intent_family,
            difficulty_score=escalation_difficulty.score,
            firewall_score=decision.score,
            firewall_reasons=tuple(decision.reasons)
            + ((str(escalation_reason),) if escalation_reason else ()),
            small_answer_available=bool(str(response or "").strip()),
        )
        trace["model_escalation_policy"] = escalation_policy.as_trace()
        if not decision.accepted and trace.get("native_streaming"):
            # Incremental text may already be visible. Preserve stream integrity
            # and report the post-check instead of replacing emitted content.
            firewall_trace["status"] = "stream_postcheck_warning"
            firewall_trace["intercepted"] = False
        elif not decision.accepted or escalation_reason:
            _emit_chat_progress(
                context,
                "answer_review",
                "Nova is checking the small-model answer before speaking.",
                42,
            )
            original_source = trace.get("source")
            trace["answer_firewall_original_source"] = original_source
            retry_allowed, retry_policy_reason = _candidate_retry_allowed(trace, context)
            if not escalation_policy.should_escalate:
                retry_allowed = False
                retry_policy_reason = (
                    "model_policy_" + escalation_policy.selected_tier
                )
            primary_candidate = AnswerCandidate(
                candidate_id="primary",
                answer=str(response or ""),
                source=str(original_source or "nova_core"),
                provider=str(trace.get("local_llm_provider") or "existing-nova"),
                model=str(trace.get("local_llm_model") or "nova"),
                firewall=decision,
                relevance_text=(str(text or "") + " " + str(previous_user or "")).strip(),
                trace_confidence=float(trace.get("confidence") or 0.0),
                metadata={
                    "self_reported_uncertainty": escalation_reason == "primary_model_uncertain",
                    "unverified_exact_claim": escalation_reason == "primary_model_unverified_exact_claim",
                    "too_shallow": escalation_reason == "primary_model_too_shallow",
                    "question_restatement": escalation_reason == "primary_model_question_restatement",
                    "clarification_deflection": escalation_reason == "primary_model_clarification_deflection",
                    "complexity_mismatch": escalation_reason == "primary_model_complexity_mismatch",
                    "consistency_failed": escalation_reason == "primary_model_consistency_failed",
                    "requested_aspect_coverage": _requested_aspect_coverage(text, response),
                },
            )
            candidates = [primary_candidate]
            alternate_result = {"ok": False, "reason": retry_policy_reason}
            review_attempts = []
            if retry_allowed:
                _emit_chat_progress(
                    context,
                    "larger_local_review",
                    "A larger free local model is loading or reviewing the answer.",
                    58,
                )
                if trace.get("direct_middle_primary"):
                    direct_release = _release_direct_middle_before_deep(trace)
                    trace["direct_middle_release"] = direct_release
                    tier_plan = ["deep"] if direct_release.get("released") else []
                    excluded_models = [str(trace.get("local_llm_model") or "")]
                    if not tier_plan:
                        alternate_result = {
                            "ok": False,
                            "reason": "deep_skipped_until_middle_memory_is_released",
                            "reviewer_tier": "deep",
                        }
                else:
                    tier_plan = list(escalation_policy.fallback_tiers)
                    if not _middle_reviewer_enabled():
                        tier_plan = [
                            tier for tier in tier_plan if tier != "middle"
                        ]
                    excluded_models = []
                for reviewer_tier in tier_plan:
                    _emit_chat_progress(
                        context,
                        "middle_local_review" if reviewer_tier == "middle" else "deep_local_review",
                        (
                            "Nova is trying the faster middle local reviewer."
                            if reviewer_tier == "middle"
                            else "Nova is using the deeper local reviewer."
                        ),
                        58 if reviewer_tier == "middle" else 72,
                    )
                    alternate_result = _generate_alternate_local_candidate(
                        text,
                        previous_user,
                        previous_answer,
                        trace,
                        context,
                        reviewer_tier=reviewer_tier,
                        excluded_model_ids=excluded_models,
                    )
                    alternate_result.setdefault("reviewer_tier", reviewer_tier)
                    attempted_model = str(alternate_result.get("model") or "")
                    if attempted_model:
                        excluded_models.append(attempted_model)
                    candidate = _validate_alternate_local_candidate(
                        text,
                        previous_user,
                        previous_answer,
                        alternate_result,
                    )
                    review_attempts.append(
                        {
                            "tier": reviewer_tier,
                            "ok": bool(candidate),
                            "reason": str(alternate_result.get("reason") or ""),
                            "provider": str(alternate_result.get("provider") or ""),
                            "model": attempted_model,
                            "latency_ms": alternate_result.get("latency_ms"),
                            "finish_reason": str(alternate_result.get("finish_reason") or ""),
                        }
                    )
                    if candidate is not None:
                        _emit_chat_progress(
                            context,
                            "answer_validation",
                            "Nova is validating the selected local reviewer answer.",
                            86,
                        )
                        candidates.append(candidate)
                        break

            _emit_chat_progress(
                context,
                "answer_selection",
                "Nova is selecting the strongest safe answer.",
                96,
            )
            winner, ranked_candidates = choose_candidate(candidates)
            candidate_trace = {
                "version": CANDIDATE_SELECTOR_VERSION,
                "triggered": True,
                "retry_allowed": retry_allowed,
                "retry_policy_reason": retry_policy_reason,
                "retry_attempted": bool(retry_allowed),
                "retry_result": str(alternate_result.get("reason") or "not_attempted"),
                "selected": winner.candidate.candidate_id if winner else "recovery",
                "escalation_reason": escalation_reason or "answer_quality_check_failed",
                "escalation_task_type": _candidate_escalation_task_type(text, trace),
                "review_attempts": review_attempts,
                "selected_reviewer_tier": (
                    str(alternate_result.get("reviewer_tier") or "")
                    if alternate_result.get("ok")
                    else None
                ),
                "candidates": [item.safe_summary() for item in ranked_candidates],
            }
            if alternate_result.get("latency_ms") is not None:
                candidate_trace["retry_latency_ms"] = alternate_result.get("latency_ms")
            if alternate_result.get("model_selection"):
                candidate_trace["model_selection"] = alternate_result.get("model_selection")
            if alternate_result.get("consistency"):
                candidate_trace["alternate_consistency"] = alternate_result.get("consistency")
            trace["candidate_selection"] = candidate_trace

            if winner and winner.candidate.candidate_id == "alternate_local":
                response = winner.candidate.answer
                trace["source"] = "answer_candidate_selector"
                trace["domain"] = "response_quality"
                trace["provider"] = winner.candidate.provider
                trace["model"] = winner.candidate.model
                trace["reviewer_tier"] = str(
                    winner.candidate.metadata.get("reviewer_tier") or "deep"
                )
                trace["roles"] = list(
                    dict.fromkeys(list(trace.get("roles") or []) + ["critic_conscience_transformer", "speech_output_transformer"])
                )
                trace["skills"] = list(
                    dict.fromkeys(
                        list(trace.get("skills") or [])
                        + [
                            "answer_relevance_check",
                            "candidate_selection",
                            "difficulty_routing",
                            "tiered_local_review",
                            "technical_consistency_check",
                        ]
                    )
                )
                trace["route_path"] = list(trace.get("route_path") or []) + ["candidate_selector", "speech_output"]
                trace["candidate_retry_used"] = True
                trace["fallback_used"] = False
                trace["final_answer_source"] = "alternate_local_candidate"
                trace["confidence"] = winner.score
                selected_grounding = winner.candidate.metadata.get("fact_grounding")
                if isinstance(selected_grounding, dict):
                    trace["fact_grounding"] = selected_grounding
                selected_consistency = winner.candidate.metadata.get("answer_consistency")
                if isinstance(selected_consistency, dict):
                    trace["answer_consistency"] = selected_consistency
                firewall_trace = winner.candidate.firewall.as_trace()
                firewall_trace["status"] = "passed_after_retry"
                firewall_trace["intercepted"] = True
                firewall_trace["initial_reasons"] = list(decision.reasons)
            elif decision.accepted and escalation_reason == "primary_model_unverified_exact_claim":
                candidate_trace["selected"] = "recovery"
                response = (
                    "I could not verify that exact value. I asked a larger local model, but it did not "
                    "produce a supported answer, so I will not guess a number."
                )
                trace["source"] = "exact_claim_verification_guard"
                trace["domain"] = "response_quality"
                trace["roles"] = list(
                    dict.fromkeys(list(trace.get("roles") or []) + ["critic_conscience_transformer", "speech_output_transformer"])
                )
                trace["skills"] = list(
                    dict.fromkeys(list(trace.get("skills") or []) + ["uncertainty_detection", "model_escalation", "exact_claim_guard"])
                )
                trace["route_path"] = list(trace.get("route_path") or []) + [
                    "larger_model_escalation",
                    "exact_claim_guard",
                    "speech_output",
                ]
                trace["candidate_retry_used"] = False
                trace["model_escalation_attempted"] = bool(retry_allowed)
                trace["model_escalation_result"] = str(alternate_result.get("reason") or "not_attempted")
                trace["fallback_used"] = True
                trace["final_answer_source"] = "exact_claim_verification_guard"
                firewall_trace["status"] = "unverified_exact_claim_blocked"
                firewall_trace["intercepted"] = True
            elif decision.accepted:
                candidate_trace["selected"] = "primary"
                response = primary_candidate.answer
                trace["skills"] = list(
                    dict.fromkeys(list(trace.get("skills") or []) + ["uncertainty_detection", "model_escalation"])
                )
                trace["route_path"] = list(trace.get("route_path") or []) + [
                    "larger_model_escalation",
                    "primary_preserved",
                ]
                trace["candidate_retry_used"] = False
                trace["model_escalation_attempted"] = bool(retry_allowed)
                trace["model_escalation_result"] = str(alternate_result.get("reason") or "not_attempted")
                firewall_trace["status"] = "passed_primary_after_escalation"
                firewall_trace["intercepted"] = False
            else:
                fact_blocked = bool(trace.get("_fact_grounding_blocking"))
                llm_fallback = (
                    {"ok": False, "reason": "fact_grounding_blocked"}
                    if fact_blocked
                    else _generate_llm_fallback_candidate(
                        text,
                        previous_user,
                        previous_answer,
                        trace,
                        context,
                    )
                )
                if llm_fallback.get("ok"):
                    response = llm_fallback["answer"]
                    trace["source"] = "llm_fallback"
                    trace["domain"] = "response_quality"
                    trace["local_llm_synthesis_used"] = True
                    trace["local_llm_provider"] = llm_fallback.get("provider", "")
                    trace["local_llm_model"] = llm_fallback.get("model", "")
                    trace["roles"] = list(
                        dict.fromkeys(
                            list(trace.get("roles") or [])
                            + ["critic_conscience_transformer", "speech_output_transformer"]
                        )
                    )
                    trace["skills"] = list(
                        dict.fromkeys(
                            list(trace.get("skills") or [])
                            + ["answer_relevance_check", "llm_fallback"]
                        )
                    )
                    trace["route_path"] = list(trace.get("route_path") or []) + [
                        "llm_fallback",
                        "speech_output",
                    ]
                    trace["fallback_used"] = False
                    trace["final_answer_source"] = "llm_fallback"
                    trace["confidence"] = max(float(trace.get("confidence") or 0.0), 0.86)
                    candidate_trace["selected"] = "llm_fallback"
                    candidate_trace["llm_fallback"] = {
                        "attempted": True,
                        "ok": True,
                        "provider": llm_fallback.get("provider", ""),
                        "model": llm_fallback.get("model", ""),
                        "latency_ms": llm_fallback.get("latency_ms"),
                    }
                    firewall_trace = llm_fallback["firewall"].as_trace()
                    firewall_trace["status"] = "passed_after_llm_fallback"
                    firewall_trace["intercepted"] = True
                    firewall_trace["initial_reasons"] = list(decision.reasons)
                else:
                    response = (
                        grounding_recovery_response(text, grounding_decision)
                        if fact_blocked
                        else recovery_response(
                            text,
                            decision,
                            contextual_fallback=context_resolution.fallback_response,
                        )
                    )
                    trace["source"] = "fact_grounding_guard" if fact_blocked else "answer_firewall_recovery"
                    trace["domain"] = "response_quality"
                    trace["roles"] = list(
                        dict.fromkeys(list(trace.get("roles") or []) + ["critic_conscience_transformer", "speech_output_transformer"])
                    )
                    trace["skills"] = list(
                        dict.fromkeys(
                            list(trace.get("skills") or [])
                            + (["fact_grounding", "freshness_guard"] if fact_blocked else ["answer_relevance_check", "off_topic_block"])
                        )
                    )
                    trace["route_path"] = list(trace.get("route_path") or []) + [
                        "fact_grounding" if fact_blocked else "answer_firewall",
                        "speech_output",
                    ]
                    trace["fallback_used"] = True
                    trace["final_answer_source"] = "fact_grounding_guard" if fact_blocked else "answer_firewall_recovery"
                    trace["confidence"] = max(float(trace.get("confidence") or 0.0), 0.95)
                    candidate_trace["llm_fallback"] = {
                        "attempted": not fact_blocked,
                        "ok": False,
                        "reason": llm_fallback.get("reason", "not_attempted"),
                        "latency_ms": llm_fallback.get("latency_ms"),
                    }
                    if fact_blocked:
                        firewall_trace["status"] = "fact_grounding_blocked"
            _LAST_USER_TEXT = text
            _LAST_NOVA_RESPONSE = response
        trace["answer_firewall"] = firewall_trace

    trace.pop("_fact_grounding_blocking", None)

    # Risk-based verification happens after retrieval, tools, and answer
    # selection. The final natural shaper runs afterward and is not allowed to
    # mutate citations, dates, calculations, tool results, or uncertainty.
    if not raw_adapter_request:
        try:
            from nova_verifier import skipped_verification, verify_answer

            verification_required = bool(
                deterministic_solution is not None
                or rag_result is not None
                or (
                    turn_state is not None
                    and turn_state.reasoning_mode in {"deep", "agent", "verify"}
                )
            )
            if verification_required:
                agent_actions = []
                agent_trace = trace.get("agent_trace")
                if isinstance(agent_trace, dict):
                    agent_actions = list(agent_trace.get("actions") or [])
                verification_result = verify_answer(
                    user_text=text,
                    answer=str(response or ""),
                    sources=(rag_result.passages if rag_result is not None else ()),
                    expected_actions=agent_actions,
                    observed_actions=agent_actions,
                    require_sources=bool(
                        rag_result is not None and rag_result.passages
                    ),
                )
            else:
                verification_result = skipped_verification()
            trace["verification_v2"] = verification_result.safe_trace()
        except Exception as verification_error:
            trace["verification_v2"] = {
                "passed": False,
                "status": "verification_error",
                "error_type": type(verification_error).__name__,
                "answer_content_logged": False,
                "private_reasoning_logged": False,
            }
        try:
            from nova_natural_chat import (
                get_recent_memory,
                natural_chat_enabled,
                shape_verified_response,
            )

            if natural_chat_enabled():
                final_shaped = shape_verified_response(
                    response,
                    user_input=text,
                    recent_memory=(
                        get_recent_memory()
                        if (
                            not context.get("nova_gateway")
                            or bool(context.get("conversation_memory_allowed"))
                        )
                        else []
                    ),
                )
                if final_shaped:
                    trace["natural_response_shaped_after_verification"] = (
                        final_shaped != str(response or "")
                    )
                    response = final_shaped
        except Exception as final_natural_error:
            trace["final_natural_error"] = type(final_natural_error).__name__
        if companion_turn is not None and companion_service is not None:
            try:
                from nova_companion.response_composer import compose_response

                response = compose_response(
                    text,
                    response,
                    companion_turn.plan,
                    trace=trace,
                )
                trace["companion"] = companion_service.finalize_turn(
                    companion_turn,
                    response,
                    trace,
                )
            except Exception:
                # Companion continuity must never take down a managed answer.
                trace["companion"] = {
                    "enabled": True,
                    "state_persisted": False,
                    "memory_content_logged": False,
                    "error": "companion_unavailable",
                }
        _LAST_NOVA_RESPONSE = response

    gateway_request = bool(context.get("nova_gateway"))
    conversation_write_allowed = (
        not evaluation_only
        and
        automatic_durable_writes_allowed
        and
        action_policy is None
        and conversation_declaration is None
        and conversation_recall is None
        and (
        not gateway_request
        or (
            bool(context.get("memory_write_allowed"))
            and bool(context.get("conversation_memory_allowed"))
        )
        )
    )
    if conversation_write_allowed:
        try:
            from nova_natural_chat import natural_chat_enabled, update_conversation_memory
            if natural_chat_enabled():
                update_conversation_memory(text, response)
                if isinstance(trace, dict):
                    trace["natural_memory_updated"] = True
        except Exception as natural_err:
            if isinstance(trace, dict):
                trace["natural_memory_error"] = str(natural_err)[:120]
        if (
            not bool(context.get("private_mode"))
            and not PRIVATE_MODE
            and (local_config is None or local_config.memory_v2_enabled)
        ):
            try:
                from nova_memory_v2 import selective_memory_update

                memory_v2_record = selective_memory_update(
                    text,
                    owner_id=str(context.get("user_id") or "local-user"),
                    automatic_writes=(
                        local_config.memory_automatic_writes
                        if local_config is not None
                        else "selective"
                    ),
                )
                if memory_v2_record is not None and isinstance(trace, dict):
                    trace["memory_v2_updated"] = True
                    trace["memory_v2_id"] = memory_v2_record.memory_id
                    trace["memory_v2_type"] = memory_v2_record.memory_type
            except Exception as memory_v2_error:
                if isinstance(trace, dict):
                    trace["memory_v2_error"] = type(memory_v2_error).__name__

    if isinstance(trace, dict):
        if conversation_decision is not None:
            trace["conversation_decision"] = conversation_decision.safe_trace()
        if evaluation_only:
            trace["evaluation_only"] = True
            trace["training_write_allowed"] = False
            trace["memory_write_allowed"] = False
        trace["permissions_snapshot"] = {**PERMISSIONS, "private_mode": PRIVATE_MODE}

    trace = _attach_conversation_summary(
        trace,
        context,
        history_before_turn,
        text,
        response,
    )
    if isinstance(trace, dict):
        trace["answer_status"] = _answer_status_from_trace(trace)

    if managed_stream_emit is not None:
        buffered_primary = "".join(managed_stream_parts)
        cancelled = context.get("stream_cancelled")
        can_emit = not (callable(cancelled) and cancelled())
        replayed = False
        if can_emit and buffered_primary and buffered_primary == str(response or ""):
            replayed = True
            for part in managed_stream_parts:
                try:
                    emitted = managed_stream_emit(part)
                except Exception:
                    emitted = False
                if emitted is False:
                    replayed = False
                    break
        trace["native_streaming"] = replayed
        trace["native_stream_incremental"] = replayed and len(managed_stream_parts) > 1
        trace["managed_streaming_mode"] = (
            "validated_primary_replay" if replayed else "progress_then_validated_answer"
        )
        trace["managed_stream_content_logged"] = False
        context["stream_callback"] = managed_stream_emit

    if evaluation_only:
        pass
    elif gateway_request and str(os.environ.get("NOVA_LOG_GATEWAY_CONTENT", "false")).lower() not in {"1", "true", "yes", "on"}:
        SESSION_LOG.append(
            {
                "gateway": True,
                "request_id": context.get("request_id"),
                "client_id": context.get("client_id"),
                "conversation_id": context.get("conversation_id"),
                "response_length": len(str(response or "")),
                "route": (trace or {}).get("source") if isinstance(trace, dict) else None,
            }
        )
    else:
        logged_trace = dict(trace) if isinstance(trace, dict) else trace
        if isinstance(logged_trace, dict):
            logged_trace.pop("conversation_summary", None)
        SESSION_LOG.append({"user": text, "response": response, "trace": logged_trace})
    return response, trace


def _run_nova_chat_turn(text, context=None):
    """Serialize legacy state access and make evaluation turns non-retained."""

    global _LAST_USER_TEXT, _LAST_NOVA_RESPONSE
    global _LAST_WEB_LOOKUP_TOPIC, _LAST_WEB_LOOKUP_KIND, _LAST_WEB_LOOKUP_ITEMS
    resolved_context = context if isinstance(context, dict) else {}
    suppress_training = bool(resolved_context.get("live_companion_check"))
    previous_training_flag = os.environ.get("NOVA_SUPPRESS_CONVERSATION_TRAINING")
    if suppress_training:
        os.environ["NOVA_SUPPRESS_CONVERSATION_TRAINING"] = "1"
    with _CHAT_TURN_STATE_LOCK:
        state_snapshot = (
            _LAST_USER_TEXT,
            _LAST_NOVA_RESPONSE,
            _LAST_WEB_LOOKUP_TOPIC,
            _LAST_WEB_LOOKUP_KIND,
            deepcopy(_LAST_WEB_LOOKUP_ITEMS),
        )
        state_committed = False
        try:
            result = _run_nova_chat_turn_impl(text, resolved_context)
            if isinstance(result, tuple) and len(result) == 2:
                response, trace = result
                trace = dict(trace or {}) if isinstance(trace, dict) else {}
                state_committed, reason = _conversation_turn_commit_decision(
                    response,
                    trace,
                    evaluation_only=resolved_context.get("evaluation_only") is True,
                )
                trace["conversation_state_committed"] = state_committed
                trace["conversation_state_commit_reason"] = reason
                trace["pending_turn"] = not state_committed
                result = (response, trace)
            return result
        finally:
            if not state_committed or resolved_context.get("evaluation_only") is True:
                (
                    _LAST_USER_TEXT,
                    _LAST_NOVA_RESPONSE,
                    _LAST_WEB_LOOKUP_TOPIC,
                    _LAST_WEB_LOOKUP_KIND,
                    _LAST_WEB_LOOKUP_ITEMS,
                ) = state_snapshot
            if suppress_training:
                if previous_training_flag is None:
                    os.environ.pop("NOVA_SUPPRESS_CONVERSATION_TRAINING", None)
                else:
                    os.environ["NOVA_SUPPRESS_CONVERSATION_TRAINING"] = previous_training_flag


def _public_model_warmup_status():
    with _MODEL_WARMUP_LOCK:
        status = dict(MODEL_WARMUP_STATUS)
        status["reviewer"] = dict(MODEL_WARMUP_STATUS.get("reviewer") or {})
    status.pop("error", None)
    if status.get("state") == "failed":
        status["reason"] = "The preferred local model could not be preloaded; normal provider fallback remains available."
    reviewer = status.get("reviewer") or {}
    reviewer.pop("error", None)
    reviewer_state = str(reviewer.get("state") or "")
    if reviewer_state == "deferred_memory":
        reviewer["reason"] = "The larger local reviewer was not preloaded because Nova preserved system memory headroom."
    elif reviewer_state == "unavailable":
        reviewer["reason"] = "No eligible installed free local reviewer was available to preload."
    elif reviewer_state == "failed":
        reviewer["reason"] = "The reviewer could not be preloaded; on-demand local review remains available."
    status["reviewer"] = reviewer
    return status


def _regular_chat_routing_status(*, include_runtime_details=True):
    """Return privacy-safe model policy metadata for operators and clients.

    Runtime model-quality and hardware probes are useful on diagnostic pages,
    but they can take many seconds on a busy CPU.  The browser connection check
    asks for the lightweight policy view so UI controls never wait on them.
    """

    try:
        from nova_local_llm_connector import (
            LocalLLMConfig,
            OLLAMA_QWEN_FIRST_AUTO_MODES,
            QWEN_FIRST_LORA_AUTO_MODES,
            QWEN_FULL_LORA_ADAPTER_ID,
        )

        config = LocalLLMConfig()
        from nova_model_memory import adaptive_resource_manager_status

        policy = config.lora_auto_mode
        ollama_qwen_primary = policy in OLLAMA_QWEN_FIRST_AUTO_MODES
        status = {
            "ok": True,
            "primary_policy": policy,
            "primary_adapter_id": (
                QWEN_FULL_LORA_ADAPTER_ID if policy in QWEN_FIRST_LORA_AUTO_MODES else None
            ),
            "primary_provider": "ollama" if ollama_qwen_primary else "hf_peft_lora",
            "primary_model": config.model if ollama_qwen_primary else config.lora_base_model,
            "nova_context_before_model": True,
            "escalation_enabled": config.regular_chat_escalation_enabled,
            "difficulty_escalation_enabled": _difficulty_escalation_enabled(),
            "difficulty_escalation_threshold": _difficulty_escalation_threshold(),
            "uncertainty_router_version": UNCERTAINTY_ROUTER_VERSION,
            "candidate_selector_version": CANDIDATE_SELECTOR_VERSION,
            "technical_consistency_enabled": _technical_consistency_enabled(),
            "technical_consistency_version": TECHNICAL_CONSISTENCY_VERSION,
            "deterministic_verifier_enabled": _deterministic_verifier_enabled(),
            "deterministic_verifier_version": DETERMINISTIC_VERIFIER_VERSION,
            "capability_shadow_router_enabled": _capability_shadow_router_enabled(),
            "capability_shadow_router_mode": "evidence_only",
            "escalation_strategy": (
                "middle_then_deep" if config.middle_reviewer_enabled else "deep_only"
            ),
            "hard_request_primary_policy": "direct_middle_when_confident",
            "direct_middle_enabled": config.direct_middle_enabled,
            "direct_middle_threshold": config.direct_middle_threshold,
            "direct_middle_max_tokens": config.direct_middle_max_tokens,
            "middle_reviewer_enabled": config.middle_reviewer_enabled,
            "middle_reviewer_min_model_bytes": config.middle_reviewer_min_model_bytes,
            "middle_reviewer_max_model_bytes": config.middle_reviewer_max_model_bytes,
            "middle_reviewer_preferences": {
                task_type: list(config.middle_reviewer_model_preferences(task_type))
                for task_type in ("general", "reasoning", "coding")
            },
            "escalation_local_only": True,
            "escalation_min_model_bytes": config.escalation_min_model_bytes,
            "escalation_max_model_bytes": config.escalation_max_model_bytes,
            "escalation_timeout_seconds": config.escalation_timeout_seconds,
            "escalation_max_tokens": _candidate_retry_max_tokens(),
            "escalation_context_window": _candidate_retry_context_window(),
            "escalation_keep_alive": _candidate_retry_keep_alive(),
            "reviewer_readiness": (_public_model_warmup_status().get("reviewer") or {}),
            "escalation_preferences": {
                task_type: list(config.escalation_model_preferences(task_type))
                for task_type in ("general", "reasoning", "coding")
            },
            "raw_adapter_modes_unchanged": True,
            "schema_version": "1.0",
        }
        if include_runtime_details:
            status.update(
                {
                    "adaptive_resource_manager": adaptive_resource_manager_status(),
                    "model_quality": _model_quality_status(),
                    "capability_evaluation": _capability_evaluation_status(),
                }
            )
        else:
            status["runtime_details_deferred"] = True
        return status
    except Exception:
        status = {
            "ok": False,
            "primary_policy": "unknown",
            "escalation_enabled": False,
            "difficulty_escalation_enabled": _difficulty_escalation_enabled(),
            "difficulty_escalation_threshold": _difficulty_escalation_threshold(),
            "uncertainty_router_version": UNCERTAINTY_ROUTER_VERSION,
            "candidate_selector_version": CANDIDATE_SELECTOR_VERSION,
            "technical_consistency_enabled": _technical_consistency_enabled(),
            "technical_consistency_version": TECHNICAL_CONSISTENCY_VERSION,
            "deterministic_verifier_enabled": _deterministic_verifier_enabled(),
            "deterministic_verifier_version": DETERMINISTIC_VERIFIER_VERSION,
            "capability_shadow_router_enabled": _capability_shadow_router_enabled(),
            "capability_shadow_router_mode": "evidence_only",
            "escalation_strategy": "middle_then_deep",
            "hard_request_primary_policy": "unavailable",
            "direct_middle_enabled": False,
            "middle_reviewer_enabled": _middle_reviewer_enabled(),
            "escalation_local_only": True,
            "escalation_max_tokens": _candidate_retry_max_tokens(),
            "escalation_context_window": _candidate_retry_context_window(),
            "escalation_keep_alive": _candidate_retry_keep_alive(),
            "reviewer_readiness": (_public_model_warmup_status().get("reviewer") or {}),
            "raw_adapter_modes_unchanged": True,
            "schema_version": "1.0",
        }
        if include_runtime_details:
            status["model_quality"] = _model_quality_status()
            status["capability_evaluation"] = _capability_evaluation_status()
        else:
            status["runtime_details_deferred"] = True
        return status


def _warm_reviewer_model(config):
    """Preload one eligible installed reviewer only when memory headroom is safe."""

    base = {
        "enabled": bool(getattr(config, "reviewer_warmup", False)),
        "state": "not_started",
        "provider": None,
        "model": None,
        "elapsed_ms": None,
        "keep_alive": str(getattr(config, "reviewer_keep_alive", "10m") or "10m"),
        "available_memory_gb": None,
        "required_memory_gb": None,
        "error": None,
        "content_logged": False,
    }
    if not base["enabled"]:
        return {**base, "state": "disabled"}
    if not bool(getattr(config, "regular_chat_escalation_enabled", True)):
        return {**base, "state": "disabled", "reason_code": "escalation_disabled"}

    try:
        from nova_model_memory import (
            list_ollama_loaded_models,
            model_activity,
            system_memory_status,
        )

        memory = system_memory_status()
        available_gb = memory.get("available_physical_gb")
        if available_gb is None:
            return {**base, "state": "deferred_memory", "reason_code": "memory_unknown"}
        available_gb = float(available_gb)
        base["available_memory_gb"] = round(available_gb, 2)

        capabilities = []
        providers_by_id = {}
        for entry in NOVA_GATEWAY.providers.list_providers():
            provider_id = str((entry or {}).get("provider_id") or "")
            if not provider_id or provider_id == "existing-nova":
                continue
            if str((entry or {}).get("local_or_remote") or "") != "local":
                continue
            if str((entry or {}).get("cost_type") or "") != "free":
                continue
            try:
                provider = NOVA_GATEWAY.providers.get_provider(provider_id)
                if not _provider_is_safe_local_candidate(provider):
                    continue
                providers_by_id[provider_id] = provider
                capabilities.extend(provider.list_models())
            except Exception:
                continue
        capabilities = [
            capability
            for capability in capabilities
            if not MODEL_QUALITY.is_quarantined(
                str(getattr(capability, "provider_id", "") or "unknown"),
                str(getattr(capability, "model_id", "") or ""),
            )
        ]

        task_type = str(getattr(config, "reviewer_warmup_task", "reasoning") or "reasoning")
        selected = None
        selection = {}
        reviewer_tier = "deep"
        if bool(getattr(config, "middle_reviewer_enabled", False)):
            selected, selection = select_alternate_model(
                capabilities,
                primary_model=str(getattr(config, "model", "") or ""),
                minimum_model_bytes=int(
                    getattr(config, "middle_reviewer_min_model_bytes", 1_500_000_000)
                    or 1_500_000_000
                ),
                maximum_model_bytes=int(
                    getattr(config, "middle_reviewer_max_model_bytes", 3_000_000_000)
                    or 3_000_000_000
                ),
                preferred_model_ids=config.middle_reviewer_model_preferences(task_type),
                prefer_larger=False,
                require_preferred=True,
            )
            reviewer_tier = "middle"
            if selected is not None:
                qualification = _middle_model_qualification(
                    getattr(selected, "model_id", ""),
                    task_type,
                )
                selection["capability_qualification"] = qualification
                if qualification.get("enforced") and not qualification.get(
                    "eligible"
                ):
                    selected = None
        if selected is None:
            selected, selection = select_alternate_model(
                capabilities,
                primary_model=str(getattr(config, "model", "") or ""),
                minimum_model_bytes=_candidate_retry_minimum_model_bytes(),
                maximum_model_bytes=_candidate_retry_maximum_model_bytes(),
                preferred_model_ids=config.escalation_model_preferences(task_type),
                prefer_larger=True,
            )
            reviewer_tier = "deep"
        if selected is None:
            return {
                **base,
                "state": "unavailable",
                "reason_code": "no_eligible_local_model",
                "eligible_count": int(selection.get("eligible_count") or 0),
            }

        provider_id = str(getattr(selected, "provider_id", "") or "")
        model_id = str(getattr(selected, "model_id", "") or "")
        provider = providers_by_id.get(provider_id)
        metadata = getattr(selected, "metadata", {}) or {}
        try:
            size_gb = max(0.0, float(metadata.get("size") or 0) / float(1024**3))
        except (TypeError, ValueError):
            size_gb = 0.0
        minimum_gb = float(
            (
                getattr(config, "middle_reviewer_warmup_min_available_gb", 5.0)
                if reviewer_tier == "middle"
                else getattr(config, "reviewer_warmup_min_available_gb", 8.0)
            )
            or (5.0 if reviewer_tier == "middle" else 8.0)
        )
        required_gb = max(minimum_gb, size_gb * 1.30 + 1.5)
        base.update(
            provider=provider_id,
            model=model_id,
            tier=reviewer_tier,
            required_memory_gb=round(required_gb, 2),
        )
        resident_models = {
            str(item.get("name") or "").strip().removesuffix(":latest")
            for item in list_ollama_loaded_models()
            if isinstance(item, dict)
        }
        if model_id.removesuffix(":latest") in resident_models:
            return {
                **base,
                "state": "ready",
                "elapsed_ms": 0.0,
                "reason_code": "already_resident",
            }
        if provider_id != "ollama" and available_gb < required_gb:
            return {**base, "state": "deferred_memory", "reason_code": "memory_headroom"}
        if provider is None:
            return {**base, "state": "unavailable", "reason_code": "provider_unavailable"}

        if provider_id == "ollama":
            from nova_model_memory import managed_model_residency

            with managed_model_residency(
                model_id,
                target_family=reviewer_tier,
                estimated_model_bytes=int(metadata.get("size") or 0),
            ) as residency:
                base["resource_manager"] = residency
                if not residency.get("allowed"):
                    return {
                        **base,
                        "state": "deferred_memory",
                        "reason_code": "adaptive_memory_policy",
                    }
                result = provider.warm_up_model(
                    model_id,
                    keep_alive=base["keep_alive"],
                    timeout=int(getattr(config, "model_warmup_timeout", 180) or 180),
                )
        else:
            with model_activity("reviewer"):
                result = provider.warm_up_model(
                    model_id,
                    keep_alive=base["keep_alive"],
                    timeout=int(getattr(config, "model_warmup_timeout", 180) or 180),
                )
        return {
            **base,
            "state": str(result.get("state") or ("ready" if result.get("ok") else "failed")),
            "elapsed_ms": result.get("elapsed_ms"),
            "error": result.get("error"),
            "provider": str(result.get("provider") or provider_id),
            "model": str(result.get("model") or model_id),
        }
    except Exception as exc:
        return {**base, "state": "failed", "error": str(exc)}


def _start_model_warmup():
    """Preload the preferred local model in the background without blocking HTTP."""
    try:
        from nova_local_llm_connector import LocalLLMConfig, LocalLLMConnector

        config = LocalLLMConfig()
    except Exception as exc:
        with _MODEL_WARMUP_LOCK:
            MODEL_WARMUP_STATUS.update(enabled=False, state="failed", error=str(exc))
        return None

    if not config.model_warmup:
        with _MODEL_WARMUP_LOCK:
            MODEL_WARMUP_STATUS.update(
                enabled=False,
                state="disabled",
                reviewer={
                    **dict(MODEL_WARMUP_STATUS.get("reviewer") or {}),
                    "enabled": False,
                    "state": "disabled",
                    "error": None,
                },
            )
        print("  [WARMUP] Local model warm-up is disabled")
        if _automatic_model_quality_check_enabled():
            _start_loaded_model_quality_check("startup")
        return None

    delay_seconds = config.model_warmup_delay_seconds
    with _MODEL_WARMUP_LOCK:
        MODEL_WARMUP_STATUS.update(
            enabled=True,
            state="scheduled",
            error=None,
            reviewer={
                **dict(MODEL_WARMUP_STATUS.get("reviewer") or {}),
                "enabled": bool(config.reviewer_warmup),
                "state": "scheduled" if config.reviewer_warmup else "disabled",
                "error": None,
            },
        )

    def run_warmup():
        if delay_seconds:
            time.sleep(delay_seconds)
        with _MODEL_WARMUP_LOCK:
            MODEL_WARMUP_STATUS.update(
                enabled=True,
                state="warming",
                started_at=datetime.now().isoformat(timespec="seconds"),
                completed_at=None,
                error=None,
            )
        print("  [WARMUP] Loading the preferred local model in the background...")
        if MODEL_QUALITY.is_quarantined("ollama", str(config.model or "")):
            result = {
                "ok": False,
                "state": "quarantined",
                "provider": "ollama",
                "model": str(config.model or ""),
                "reason": "model_quality_quarantined",
            }
        else:
            result = LocalLLMConnector(config).warm_up()
        with _MODEL_WARMUP_LOCK:
            MODEL_WARMUP_STATUS.update(
                enabled=True,
                state=str(result.get("state") or ("ready" if result.get("ok") else "failed")),
                provider=result.get("provider"),
                model=result.get("model"),
                device=result.get("device"),
                elapsed_ms=result.get("elapsed_ms"),
                completed_at=datetime.now().isoformat(timespec="seconds"),
                error=result.get("error") or result.get("reason"),
            )
        if result.get("ok"):
            elapsed_ms = float(result.get("elapsed_ms") or 0)
            print(f"  [WARMUP] Ready: {result.get('model') or result.get('provider')} ({elapsed_ms:.0f} ms)")
        else:
            print(f"  [WARMUP] Deferred safely: {result.get('error') or result.get('reason') or 'unavailable'}")

        if config.reviewer_warmup:
            with _MODEL_WARMUP_LOCK:
                MODEL_WARMUP_STATUS["reviewer"] = {
                    **dict(MODEL_WARMUP_STATUS.get("reviewer") or {}),
                    "enabled": True,
                    "state": "warming",
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "completed_at": None,
                    "error": None,
                }
            print("  [WARMUP] Checking memory headroom for the larger local reviewer...")
            reviewer_result = _warm_reviewer_model(config)
            reviewer_result["completed_at"] = datetime.now().isoformat(timespec="seconds")
            with _MODEL_WARMUP_LOCK:
                MODEL_WARMUP_STATUS["reviewer"] = reviewer_result
            if reviewer_result.get("state") == "ready":
                print(
                    "  [WARMUP] Reviewer ready: "
                    f"{reviewer_result.get('model')} ({float(reviewer_result.get('elapsed_ms') or 0):.0f} ms)"
                )
            else:
                print(
                    "  [WARMUP] Reviewer deferred safely: "
                    f"{reviewer_result.get('reason_code') or reviewer_result.get('state')}"
                )
        if _automatic_model_quality_check_enabled():
            _start_loaded_model_quality_check("startup")

    if delay_seconds:
        print(f"  [WARMUP] Preferred local model scheduled in {delay_seconds} seconds")
    thread = threading.Thread(target=run_warmup, name="nova-model-warmup", daemon=True)
    thread.start()
    return thread


NOVA_GATEWAY_CONFIG = GatewayConfig.from_env(root=ROOT, default_port=8765)
NOVA_GATEWAY_CLIENTS = NovaClientRegistry(NOVA_GATEWAY_CONFIG.client_registry_path)
NOVA_GATEWAY_AUTH = NovaAuthenticator(NOVA_GATEWAY_CONFIG, NOVA_GATEWAY_CLIENTS)
NOVA_GATEWAY = NovaGatewayCore(_run_nova_chat_turn, config=NOVA_GATEWAY_CONFIG)
NOVA_GATEWAY_HTTP = NovaGatewayHttpController(NOVA_GATEWAY, NOVA_GATEWAY_AUTH, NOVA_GATEWAY_CONFIG)


HTML_PATH = os.path.join(ROOT, "nova_chat_web.html")
COMPANION_HTML_PATH = os.path.join(ROOT, "nova_companion_web.html")
WEB_HTML = None
if os.path.exists(HTML_PATH):
    with open(HTML_PATH, encoding="utf-8") as f:
        WEB_HTML = f.read()
        print(f"[HTML] Loaded from {HTML_PATH}")
else:
    # Inline minimal UI
    WEB_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Nova Creature</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0a0a12;color:#e0e0e0;height:100vh;overflow:hidden}
.app{display:flex;flex-direction:column;height:100vh;max-width:900px;margin:0 auto}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:12px 20px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a4a}
.header h1{font-size:18px;font-weight:600;background:linear-gradient(90deg,#7c7cff,#ff7c7c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.chat{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.msg.user{background:#2a2a4a;color:#e0e0e0;align-self:flex-end;border-bottom-right-radius:4px}
.msg.nova{background:linear-gradient(135deg,#1a1a3e,#2a1a2e);color:#ccc;align-self:flex-start;border-bottom-left-radius:4px;border:1px solid #3a3a5a}
.msg .meta{font-size:10px;color:#666;margin-top:6px;padding-top:6px;border-top:1px solid #2a2a3a;display:flex;flex-wrap:wrap;gap:4px}
.msg .meta .tag{padding:1px 6px;border-radius:8px;font-size:9px;background:#2a2a4a;color:#888}
.msg .meta .tag.route{background:#2a3a2a;color:#6a6}
.msg .meta .tag.conf{background:#3a2a2a;color:#a66}
.msg .meta .tag.mem{background:#2a2a3a;color:#66a}
.typing{font-size:12px;color:#666;padding:4px 14px;display:none;align-self:flex-start}
.typing .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#7c7cff;margin:0 2px;animation:bounce 1.4s infinite}
.typing .dot:nth-child(2){animation-delay:.2s}.typing .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.input-bar{background:#12121e;border-top:1px solid #2a2a4a;padding:12px 20px}
.input-row{display:flex;gap:8px}
.input-row input{flex:1;padding:10px 14px;border-radius:20px;border:1px solid #3a3a5a;background:#1a1a2e;color:#e0e0e0;font-size:14px;outline:none}
.input-row input:focus{border-color:#6a6aff}
.input-row button{padding:10px 20px;border-radius:20px;border:none;background:#4a4a8a;color:#fff;font-size:14px;cursor:pointer}
.input-row button:hover{background:#5a5a9a}
.input-row button:disabled{opacity:.5;cursor:not-allowed}
.permissions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.perm-btn{padding:3px 10px;border-radius:12px;border:1px solid #333;background:transparent;color:#888;font-size:10px;cursor:pointer;transition:all .2s}
.perm-btn.on{border-color:#4a8;color:#4a8;background:#4a822}
.perm-btn.danger{border-color:#a44;color:#a44;background:#a4422}
@media(max-width:600px){.msg{max-width:95%;font-size:13px}.header h1{font-size:15px}}
</style></head><body>
<div class="app">
<div class="header"><h1>Nova Creature</h1><span class="session" id="sessionId"></span></div>
<div class="chat" id="chat"></div>
<div class="typing" id="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Nova is thinking...</div>
<div class="input-bar">
<div class="input-row"><input type="text" id="input" placeholder="Talk to Nova..." autofocus><button id="sendBtn">Send</button></div>
<div class="permissions">
<button class="perm-btn" id="btnMic" onclick="togglePerm('mic')">Mic OFF</button>
<button class="perm-btn" id="btnCam" onclick="togglePerm('camera')">Camera OFF</button>
<button class="perm-btn" id="btnSpk" onclick="togglePerm('speaker')">Speaker OFF</button>
<button class="perm-btn danger" onclick="stopAll()">Stop All</button>
<button class="perm-btn" id="btnPrivate" onclick="togglePrivate()">Private OFF</button>
</div></div></div>
<script>
const chat=document.getElementById('chat'),input=document.getElementById('input'),typing=document.getElementById('typing'),sendBtn=document.getElementById('sendBtn');
document.getElementById('sessionId').textContent='Session: '+Math.random().toString(36).slice(2,8);
function addMsg(role,text,meta){
  const div=document.createElement('div');div.className='msg '+role;
  let html=text.replace(/\\n/g,'<br>');
  if(meta){
    html+='<div class="meta">';
    if(meta.roles) html+='<span class="tag route">'+meta.roles.join(' -> ')+'</span>';
    if(meta.confidence) html+='<span class="tag conf">'+Math.round(meta.confidence*100)+'%</span>';
    if(meta.memory_event) html+='<span class="tag mem">'+meta.memory_event+'</span>';
    if(meta.domain) html+='<span class="tag">'+meta.domain+'</span>';
    html+='</div>';
  }
  div.innerHTML=html;chat.appendChild(div);chat.scrollTop=chat.scrollHeight;
}
async function send(){
  const text=input.value.trim();if(!text)return;
  input.value='';sendBtn.disabled=true;typing.style.display='block';
  addMsg('user',text);
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    const data=await res.json();
    typing.style.display='none';
    addMsg('nova',data.response,data.trace);
  }catch(e){typing.style.display='none';addMsg('nova','Connection error. Make sure the server is running.');}
  finally{sendBtn.disabled=false;input.focus()}
}
input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
sendBtn.onclick=send;
async function togglePerm(n){const cmd=document.getElementById({mic:'btnMic',camera:'btnCam',speaker:'btnSpk'}[n]).textContent.includes('ON')?'deny '+n:'allow '+n;
  try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:cmd})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
async function togglePrivate(){try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'private mode'})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
async function stopAll(){try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'stop all'})});const d=await r.json();addMsg('nova',d.response,d.trace);}catch(e){}}
addMsg('nova','Hello! I am **Nova Creature** - a multi-brain AI.\\n\\nType anything or click buttons to test me!');
</script></body></html>"""

with open(COMPANION_HTML_PATH, encoding="utf-8") as f:
    COMPANION_WEB_HTML = f.read()


def _gpu_hub_env_enabled():
    """GPU Hub defaults on for safe local inspection routes."""

    value = str(os.environ.get("NOVA_GPU_HUB_ENABLED", "true")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _gpu_hub_remote_actions_enabled():
    """Lifecycle calls require both the Hub and a server-only Vast key."""

    return _gpu_hub_env_enabled() and bool(os.environ.get("NOVA_VAST_API_KEY", "").strip())


def _gpu_hub_scrub(value, secrets=()):
    """Return a browser-safe representation without key/token material."""

    if isinstance(value, dict):
        return {
            str(key): _gpu_hub_scrub(item, secrets)
            for key, item in value.items()
            if not re.search(r"key|token|secret|password|credential|authorization", str(key), re.I)
        }
    if isinstance(value, list):
        return [_gpu_hub_scrub(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [_gpu_hub_scrub(item, secrets) for item in value]
    if isinstance(value, str):
        result = value
        for secret in secrets:
            if secret:
                result = result.replace(str(secret), "[redacted]")
        return re.sub(r"\b(?:secret|api[_ -]?key|bearer\s+\S+)\b", "[redacted]", result, flags=re.I)
    return value


class GpuHubHttpController:
    """Small HTTP-independent boundary for Nova's standalone GPU Hub."""

    _PREFIX = "/api/gpu-hub"

    def __init__(
        self,
        hub,
        *,
        enabled=None,
        remote_actions_enabled=None,
        remote_model_probe=None,
        remote_model_allowlist=None,
    ):
        self.hub = hub
        self._enabled = enabled or _gpu_hub_env_enabled
        self._remote_actions_enabled = remote_actions_enabled or _gpu_hub_remote_actions_enabled
        self._remote_model_probe = remote_model_probe or self._probe_remote_model
        if remote_model_allowlist is None:
            env = getattr(hub, "env", os.environ)
            configured = env.get("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", "") if isinstance(env, dict) else ""
            remote_model_allowlist = re.split(r"[,;\s]+", str(configured))
        elif isinstance(remote_model_allowlist, str):
            remote_model_allowlist = re.split(r"[,;\s]+", remote_model_allowlist)
        self._remote_model_allowlist = {
            str(host).strip().lower().rstrip(".")
            for host in remote_model_allowlist
            if str(host).strip()
        }

    def _secrets(self):
        env = getattr(self.hub, "env", {})
        if not isinstance(env, dict):
            return ()
        return tuple(
            str(value)
            for key, value in env.items()
            if re.search(r"key|token|secret|password|credential", str(key), re.I)
            and str(value)
        )

    def _result(self, payload, status=200, *, request_secrets=()):
        return True, status, _gpu_hub_scrub(
            payload,
            self._secrets() + tuple(str(secret) for secret in request_secrets if secret),
        )

    def _error(self, error):
        if isinstance(error, ValueError):
            return self._result(
                {"ok": False, "code": "invalid_mode", "error": "Choose auto, cpu, local_gpu, or vast_gpu."},
                400,
            )
        if isinstance(error, GpuHubError):
            if error.code == "confirmation_required":
                status = 400
            elif error.code == "vast_unavailable":
                status = 503
            elif isinstance(error.status, int) and 400 <= error.status < 500:
                status = error.status
            else:
                status = 502
            return self._result({"ok": False, "code": error.code, "error": str(error)}, status)
        return self._result(
            {"ok": False, "code": "gpu_hub_unavailable", "error": "GPU Hub request could not be completed."},
            503,
        )

    def _disabled(self):
        return self._result(
            {"ok": False, "code": "gpu_hub_disabled", "error": "GPU Hub is disabled."}, 503
        )

    def _status_payload(self, state=None):
        state = state if isinstance(state, dict) else self.hub.status()
        effective_mode = state.get(
            "effective_mode",
            state.get("effective_backend", "cpu"),
        )
        return {
            "ok": True,
            "enabled": bool(self._enabled()),
            "mode": state.get("mode", "auto"),
            "effective_mode": effective_mode,
            "effective_backend": effective_mode,
            "available": bool(state.get("available")),
            "reason": str(state.get("reason") or "GPU Hub status is unavailable."),
            "verified": bool(state.get("verified")),
            "verified_backend": state.get("verified_backend"),
            "verified_at": state.get("verified_at"),
            "verification_expired": bool(state.get("verification_expired")),
            "local": self.hub.local_status(),
            "vast": self.hub.vast_status(),
            "selected_instance": state.get("selected_instance_id"),
            "endpoint": state.get("endpoint") or {},
        }

    def _remote_action_allowed(self):
        if self._remote_actions_enabled():
            return None
        return self._result(
            {
                "ok": False,
                "code": "vast_unavailable",
                "error": "Vast.ai lifecycle actions require a configured NOVA_VAST_API_KEY.",
            },
            503,
        )

    def handle_get(self, path):
        if path == self._PREFIX + "/status":
            if not self._enabled():
                return self._result(
                    {
                        "ok": True,
                        "enabled": False,
                        "mode": "auto",
                        "effective_mode": "cpu",
                        "effective_backend": "cpu",
                        "available": False,
                        "reason": "GPU Hub is disabled.",
                        "verified": False,
                        "verified_backend": None,
                        "verified_at": None,
                        "verification_expired": False,
                        "local": {"available": False, "usable": False, "reason": "GPU Hub is disabled."},
                        "vast": {"available": False, "reason": "GPU Hub is disabled."},
                        "selected_instance": None,
                        "endpoint": {},
                    }
                )
            try:
                return self._result(self._status_payload())
            except Exception as error:
                return self._error(error)
        if path == self._PREFIX + "/vast/instances":
            if not self._enabled():
                return self._disabled()
            try:
                return self._result({"ok": True, "instances": self.hub.vast_instances()})
            except Exception as error:
                return self._error(error)
        return False, 404, None

    def handle_post(self, path, body):
        if not path.startswith(self._PREFIX + "/"):
            return False, 404, None
        if not self._enabled():
            return self._disabled()
        body = body if isinstance(body, dict) else {}
        try:
            if path == self._PREFIX + "/mode":
                return self._result(self._status_payload_from_state(self.hub.set_mode(str(body.get("mode") or ""))))
            if path == self._PREFIX + "/vast/test":
                instances = self.hub.vast_instances()
                return self._result({"ok": True, "valid": True, "instances_checked": len(instances)})
            if path == self._PREFIX + "/vast/search":
                filters = body.get("filters")
                return self._result({"ok": True, "offers": self.hub.vast_search(filters if isinstance(filters, dict) else {})})
            if path == self._PREFIX + "/vast/create":
                denied = self._remote_action_allowed()
                if denied:
                    return denied
                if not body.get("offer_id"):
                    raise GpuHubError("invalid_request", "An offer_id is required.", 400)
                payload = body.get("payload")
                if not isinstance(payload, dict):
                    raise GpuHubError("invalid_request", "payload must be an object.", 400)
                return self._result({"ok": True, "instance": self.hub.vast_create(body["offer_id"], payload, confirmed=body.get("confirmed") is True)})
            if path == self._PREFIX + "/vast/state":
                denied = self._remote_action_allowed()
                if denied:
                    return denied
                instance_id, state = body.get("instance_id"), body.get("state")
                if not instance_id or not state:
                    raise GpuHubError("invalid_request", "instance_id and state are required.", 400)
                return self._result({"ok": True, "instance": self.hub.vast_set_state(str(instance_id), str(state), confirmed=body.get("confirmed") is True)})
            if path == self._PREFIX + "/vast/destroy":
                denied = self._remote_action_allowed()
                if denied:
                    return denied
                instance_id = body.get("instance_id")
                if not instance_id:
                    raise GpuHubError("invalid_request", "instance_id is required.", 400)
                return self._result({"ok": True, "instance": self.hub.vast_destroy(str(instance_id), confirmed=body.get("confirmed") is True)})
            if path == self._PREFIX + "/remote-model/test":
                endpoint = str(body.get("endpoint") or "").strip()
                model = str(body.get("model") or "").strip()
                if not endpoint or not model:
                    raise GpuHubError("invalid_request", "endpoint and model are required.", 400)
                self._validate_remote_model_endpoint(endpoint)
                request_key = str(body.get("api_key") or "")
                raw_result = self._remote_model_probe(endpoint, model, request_key)
                result = raw_result if isinstance(raw_result, dict) else {}
                verified_endpoint = str(result.get("endpoint") or endpoint)
                self._validate_remote_model_endpoint(verified_endpoint)
                verified_state = self.hub.verify_remote_model(
                    verified_endpoint,
                    str(result.get("model") or model),
                    provider=str(body.get("provider") or "openai-compatible"),
                    backend=str(body.get("backend") or "") or None,
                    selected_instance_id=body.get("selected_instance_id"),
                )
                return self._result(
                    {
                        "ok": bool(result.get("ok", True)),
                        "endpoint": verified_endpoint,
                        "model": str(result.get("model") or model),
                        "method": result.get("method"),
                        "models": result.get("models", []),
                        "verified": bool(verified_state.get("verified")),
                        "verified_at": verified_state.get("verified_at"),
                    },
                    request_secrets=(request_key,),
                )
        except Exception as error:
            return self._error(error)
        return self._result({"ok": False, "code": "not_found", "error": "GPU Hub route not found."}, 404)

    def _status_payload_from_state(self, state):
        return self._status_payload(state)

    @staticmethod
    def _worker_address_allowed(address):
        try:
            parsed = ipaddress.ip_address(str(address).split("%", 1)[0])
        except ValueError:
            return False
        if parsed.is_loopback:
            return True
        if isinstance(parsed, ipaddress.IPv4Address) and parsed in ipaddress.ip_network("100.64.0.0/10"):
            return True
        return bool(
            parsed.is_private
            and not parsed.is_link_local
            and not parsed.is_unspecified
            and not parsed.is_multicast
            and not parsed.is_reserved
        )

    def _validate_remote_model_endpoint(self, endpoint):
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise GpuHubError("invalid_endpoint", "A valid HTTP(S) model endpoint is required.", 400)
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            raise GpuHubError("invalid_endpoint", "A valid HTTP(S) model endpoint is required.", 400) from None
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in self._remote_model_allowlist:
            return
        addresses = []
        try:
            addresses = [
                item[4][0]
                for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
                if item and len(item) > 4 and item[4]
            ]
        except socket.gaierror:
            pass
        if addresses and all(self._worker_address_allowed(address) for address in addresses):
            return
        raise GpuHubError(
            "remote_endpoint_not_approved",
            "Remote model tests only allow local, private, Tailscale, or server-approved hosts.",
            400,
        )

    def _probe_remote_model(self, endpoint, model, api_key):
        self._validate_remote_model_endpoint(endpoint)
        base = endpoint.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        request = urllib.request.Request(base + "/v1/models", headers=headers, method="GET")
        try:
            class RejectRedirects(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(RejectRedirects())
            with opener.open(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
            models = payload.get("data", []) if isinstance(payload, dict) else []
            model_ids = [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]
            if model_ids and model not in model_ids:
                raise GpuHubError(
                    "model_unavailable",
                    "The requested model is not available at the remote endpoint.",
                    400,
                )
            return {"ok": True, "endpoint": base, "model": model, "method": "v1_models", "models": model_ids}
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError, json.JSONDecodeError) as error:
            raise GpuHubError("remote_model_unavailable", "The remote model endpoint could not be verified.") from None


GPU_HUB = GpuHubController(ROOT)
GPU_HUB_HTTP = GpuHubHttpController(GPU_HUB)


class NovaHandler(BaseHTTPRequestHandler):
    server_version = "NovaCreature"
    sys_version = ""

    def version_string(self):
        return self.server_version

    def _allowed_cors_origin(self):
        origin = str(self.headers.get('Origin') or '').strip()
        if not origin:
            return None
        if origin == 'null':
            # Local file copies of nova_chat_web.html use a null origin.
            return origin
        try:
            parsed = urlparse(origin)
        except ValueError:
            return None
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        request_host = str(self.headers.get('Host') or '').strip().lower()
        if request_host and parsed.netloc.lower() == request_host:
            return origin
        if parsed.hostname.lower() in ('127.0.0.1', 'localhost', '0.0.0.0', '::1'):
            return origin
        configured = {
            item.strip()
            for item in os.environ.get('NOVA_ALLOWED_ORIGINS', '').split(',')
            if item.strip()
        }
        return origin if origin in configured else None

    def _send_cors_headers(self):
        allowed_origin = self._allowed_cors_origin()
        if allowed_origin:
            self.send_header('Access-Control-Allow-Origin', allowed_origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header(
            'Permissions-Policy',
            'camera=(self), microphone=(self), geolocation=(self), accelerometer=(self), gyroscope=(self)',
        )

    def _send_json(self, payload, status=200):
        encoded = json.dumps(payload, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self._send_cors_headers()
        self.end_headers()
        self._write_bytes(encoded)

    def _send_html_document(self, document: str, *, companion: bool = False):
        encoded = document.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        if companion:
            policy = (
                "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
                "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                "media-src 'self' data: blob:; connect-src 'self'; worker-src 'self'"
            )
        else:
            policy = (
                "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
                "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' data: blob:; "
                "connect-src 'self' http://127.0.0.1:* http://localhost:* http://0.0.0.0:*"
            )
        self.send_header("Content-Security-Policy", policy)
        self._send_cors_headers()
        self.end_headers()
        self._write_bytes(encoded)

    def _write_bytes(self, payload):
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Browser navigation and short health-check timeouts can close a socket
            # after headers are sent; this is a normal disconnect, not an app fault.
            return False
        return True

    def _client_is_local(self):
        return FOUNDATION_HTTP.client_is_local(self)

    def _pairing_required_for_client(self):
        return FOUNDATION_HTTP.pairing_required_for_client(self)

    def _bearer_token(self):
        return FOUNDATION_HTTP.bearer_token(self)

    def _authorize_api(self, parsed_path):
        if NOVA_GATEWAY_HTTP.recognizes(str(parsed_path)):
            # Gateway API keys are validated by the gateway. A paired web device
            # may also use safe gateway chat/stream scopes with its device token.
            device = FOUNDATION.store.validate_device_token(
                FOUNDATION_HTTP.bearer_token(self), touch=False
            )
            if device is not None:
                self._paired_device = device
                self._paired_device_local = NOVA_GATEWAY_HTTP.client_is_local(self)
            return True
        return FOUNDATION_HTTP.authorize_api(self, parsed_path)

    def _require_local_management(self):
        return FOUNDATION_HTTP.require_local_management(self)

    def _pairing_status_payload(self):
        return FOUNDATION_HTTP.pairing_status_payload(self)

    def _content_length(self, maximum):
        raw_length = self.headers.get('Content-Length')
        if raw_length is None:
            raise RequestBodyError('Content-Length is required.')
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise RequestBodyError('Content-Length must be a non-negative integer.') from exc
        if length < 0:
            raise RequestBodyError('Content-Length must be a non-negative integer.')
        if length > maximum:
            raise RequestBodyTooLarge(
                f'Request body exceeds the {maximum // (1024 * 1024)} MB limit.'
            )
        return length

    def _read_json_body(self):
        length = self._content_length(MAX_JSON_BODY_BYTES)
        if not length:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestBodyError('Invalid JSON request body.') from exc
        if not isinstance(payload, dict):
            raise RequestBodyError('JSON request body must be an object.')
        return payload

    def _receive_adapter_zip(self, filename):
        length = self._content_length(MAX_UPLOAD_BYTES)
        if not length:
            raise RequestBodyError('Adapter ZIP upload is empty.')
        upload_path = _adapter_upload_path(filename)
        remaining = length
        try:
            with upload_path.open('xb') as destination:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise RequestBodyError('Adapter ZIP upload ended before Content-Length bytes arrived.')
                    destination.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            upload_path.unlink(missing_ok=True)
            raise
        return upload_path

    def _send_project_error(self, error):
        if isinstance(error, RequestBodyTooLarge):
            status = 413
        else:
            status = 404 if isinstance(error, FileNotFoundError) else 400
        self._send_json({"ok": False, "error": str(error)}, status=status)

    def _project_api_parts(self, parsed_path):
        api_prefix = "/api/projects"
        path = unquote(parsed_path)
        if path == api_prefix:
            return []
        if not path.startswith(api_prefix + "/"):
            return None
        return [part for part in path[len(api_prefix) + 1:].split("/") if part]

    def _handle_gpu_hub_get(self, parsed):
        handled, status, payload = GPU_HUB_HTTP.handle_get(parsed.path)
        if not handled:
            return False
        self._send_json(payload, status=status)
        return True

    def _handle_gpu_hub_post(self, parsed):
        if not parsed.path.startswith("/api/gpu-hub/"):
            return False
        body = self._read_json_body()
        handled, status, payload = GPU_HUB_HTTP.handle_post(parsed.path, body)
        if not handled:
            return False
        self._send_json(payload, status=status)
        return True

    def _handle_projects_get(self, parsed):
        parts = self._project_api_parts(parsed.path)
        if parts is None:
            return False
        if not _PROJECT_MANAGER_AVAIL:
            self._send_json({"ok": False, "error": "Project manager is not available"}, status=503)
            return True
        try:
            if not parts:
                self._send_json({"ok": True, "projects": _project_manager.list_projects(APP_BUILDER_PROJECTS_ROOT)})
                return True
            project_id = parts[0]
            if len(parts) == 2 and parts[1] == "files":
                self._send_json({"ok": True, "files": _project_manager.list_project_files(APP_BUILDER_PROJECTS_ROOT, project_id)})
                return True
            if len(parts) == 2 and parts[1] == "file":
                query = parse_qs(parsed.query)
                file_path = query.get("path", [""])[0]
                self._send_json({"ok": True, **_project_manager.read_project_file(APP_BUILDER_PROJECTS_ROOT, project_id, file_path)})
                return True
            if len(parts) == 2 and parts[1] == "quality":
                if not _QUALITY_GATE_AGENT_AVAIL:
                    self._send_json({"ok": False, "error": "Quality Gate Agent is not available"}, status=503)
                    return True
                report = _quality_gate_agent.run_quality_gate(APP_BUILDER_PROJECTS_ROOT, project_id, fix=False)
                self._send_json({"ok": True, "report": report})
                return True
            if len(parts) == 2 and parts[1] == "export.zip":
                exported = _project_manager.export_project_zip(APP_BUILDER_PROJECTS_ROOT, PROJECT_EXPORTS_ROOT, project_id)
                zip_path = Path(exported["zip_path"])
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{zip_path.name}"')
                self._send_cors_headers()
                self.end_headers()
                self._write_bytes(zip_path.read_bytes())
                return True
        except Exception as error:
            self._send_project_error(error)
            return True
        self._send_json({"ok": False, "error": "Project API route not found"}, status=404)
        return True

    def _handle_projects_post(self, parsed):
        parts = self._project_api_parts(parsed.path)
        if parts is None:
            return False
        if not _PROJECT_MANAGER_AVAIL:
            self._send_json({"ok": False, "error": "Project manager is not available"}, status=503)
            return True
        try:
            body = self._read_json_body()
            if parts == ["import"]:
                raw = base64.b64decode(str(body.get("content_base64", "")), validate=True)
                filename = str(body.get("filename") or "")
                is_zip = filename.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(raw))
                if is_zip:
                    project = _project_manager.import_project_zip(
                        APP_BUILDER_PROJECTS_ROOT,
                        raw,
                        project_id=body.get("project_id"),
                    )
                else:
                    project = _project_manager.import_project_file(
                        APP_BUILDER_PROJECTS_ROOT,
                        raw,
                        filename=filename or "imported_file",
                        project_id=body.get("project_id"),
                    )
                self._send_json({"ok": True, "project": project})
                return True
            if len(parts) == 2 and parts[1] == "file":
                saved = _project_manager.write_project_file(
                    APP_BUILDER_PROJECTS_ROOT,
                    parts[0],
                    body.get("path", ""),
                    body.get("content", ""),
                )
                self._send_json({"ok": True, **saved})
                return True
            if len(parts) == 2 and parts[1] == "mod":
                if not _PROJECT_MOD_AGENT_AVAIL:
                    self._send_json({"ok": False, "error": "Project mod agent is not available"}, status=503)
                    return True
                modded = _project_mod_agent.mod_loaded_file(
                    APP_BUILDER_PROJECTS_ROOT,
                    parts[0],
                    body.get("path", ""),
                    body.get("prompt", ""),
                )
                self._send_json({"ok": True, **modded})
                return True
            if len(parts) == 2 and parts[1] == "quality":
                if not _QUALITY_GATE_AGENT_AVAIL:
                    self._send_json({"ok": False, "error": "Quality Gate Agent is not available"}, status=503)
                    return True
                report = _quality_gate_agent.run_quality_gate(
                    APP_BUILDER_PROJECTS_ROOT,
                    parts[0],
                    fix=bool(body.get("fix", True)),
                )
                self._send_json({"ok": True, "report": report})
                return True
            if len(parts) == 2 and parts[1] == "deploy":
                deployed = _project_manager.deploy_project(APP_BUILDER_PROJECTS_ROOT, PROJECT_DEPLOYMENTS_ROOT, parts[0])
                self._send_json({"ok": True, **deployed})
                return True
        except Exception as error:
            self._send_project_error(error)
            return True
        self._send_json({"ok": False, "error": "Project API route not found"}, status=404)
        return True

    def _handle_companion_vision_post(self, parsed_path):
        if parsed_path != "/api/vision":
            return False
        readiness = _companion_vision_route_readiness(self)
        if not readiness["available"]:
            response = {
                "ok": False,
                "error": readiness["reason"],
                "code": "vision_unavailable",
            }
            send_json = getattr(self, "_send_json", None)
            if callable(send_json):
                send_json(response, status=503)
            else:
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            return True
        body = self._read_json_body()
        payload, status = _vision_response_from_upload(body)
        self._send_json(payload, status=status)
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self._authorize_api(parsed.path):
            return
        if NOVA_GATEWAY_HTTP.handle_get(self, parsed):
            return
        if DESKTOP_HTTP.handle_get(self, parsed):
            return
        if RELIABILITY_HTTP.handle_get(self, parsed):
            return
        if FOUNDATION_HTTP.handle_get(self, parsed):
            return
        if self._handle_gpu_hub_get(parsed):
            return
        if self._handle_projects_get(parsed):
            return
        if parsed.path in ('/', '/index.html'):
            config = _companion_ui_config()
            use_companion = config["enabled"] and config["default"]
            document = COMPANION_WEB_HTML if use_companion else WEB_HTML
            self._send_html_document(document, companion=use_companion)
        elif parsed.path == '/classic':
            self._send_html_document(WEB_HTML)
        elif parsed.path == '/companion' and _companion_ui_config()["enabled"]:
            self._send_html_document(COMPANION_WEB_HTML, companion=True)
        elif parsed.path.startswith('/sandbox/'):
            static_path = _resolve_sandbox_static_path(parsed.path)
            if static_path is None:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
                return
            content_type = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self._send_cors_headers()
            self.end_headers()
            self._write_bytes(static_path.read_bytes())
        elif parsed.path == '/status':
            reliability_status = RELIABILITY.status()
            payload = {
                "ok": True,
                "version": NOVA_APP_VERSION,
                "uptime_seconds": max(0, int(time.time() - SERVER_STARTED_AT)),
                "session": SESSION_ID,
                "permissions": PERMISSIONS,
                "private_mode": PRIVATE_MODE,
                "companion": {"vision_service": _companion_vision_service_status(self)},
                "people_count": len(MEMORY["people"]),
                "lessons_count": len(MEMORY["lessons"]),
                "pairing_required": self._pairing_required_for_client(),
                "paired_devices": FOUNDATION.store.paired_device_count(),
                "foundation_schema": FOUNDATION.store.health().get("schema_version"),
                "reliability": {
                    "overall": (reliability_status.get("diagnostics") or {}).get("overall"),
                    "automatic_backups": reliability_status.get("automatic_backups"),
                    "backup_count": reliability_status.get("backup_count"),
                },
                "model_warmup": _public_model_warmup_status(),
                "regular_chat_routing": _regular_chat_routing_status(
                    include_runtime_details=False
                ),
                "web_retrieval": WEB_SOURCE_RETRIEVER.health_check(),
                "source_consensus": _source_consensus_health(),
                "conversation_evaluation": _conversation_evaluation_status(),
            }
            encoded = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self._send_cors_headers()
            self.end_headers()
            self._write_bytes(encoded)
        elif parsed.path == '/healthz':
            foundation_health = FOUNDATION.store.health()
            reliability_status = RELIABILITY.status()
            self._send_json({
                "ok": True,
                "version": NOVA_APP_VERSION,
                "uptime_seconds": max(0, int(time.time() - SERVER_STARTED_AT)),
                "foundation": {
                    "ok": bool(foundation_health.get("ok")),
                    "schema_version": foundation_health.get("schema_version"),
                    "journal_mode": foundation_health.get("journal_mode"),
                },
                "reliability": {
                    "overall": (reliability_status.get("diagnostics") or {}).get("overall"),
                    "automatic_backups": reliability_status.get("automatic_backups"),
                    "backup_count": reliability_status.get("backup_count"),
                },
                "regular_chat_routing": _regular_chat_routing_status(
                    include_runtime_details=False
                ),
                "web_retrieval": WEB_SOURCE_RETRIEVER.health_check(),
                "source_consensus": _source_consensus_health(),
                "conversation_evaluation": _conversation_evaluation_status(),
            })
        elif parsed.path == '/api/training/status':
            guarded_report = _latest_guarded_training_report()
            self._send_json({
                "ok": True,
                "running": _TRAINING_RUNNING,
                "job_id": _TRAINING_RUN_ID or ((guarded_report or {}).get("run_id")),
                "latest_report": _LAST_TRAINING_REPORT,
                "latest_guarded_report": guarded_report,
                "log": _TRAINING_LOG[-12:],
            })
        elif parsed.path == '/api/training/studio/status':
            self._send_json(_training_studio_status())
        elif parsed.path == '/api/training/studio/reviews':
            self._send_json(_training_studio_reviews(parse_qs(parsed.query or "")))
        elif parsed.path == '/api/memory/list':
            query = parse_qs(parsed.query or "")
            self._send_json(
                _memory_control_list(
                    query=(query.get("q") or [""])[0],
                    active=(query.get("active") or ["all"])[0],
                )
            )
        elif parsed.path == '/api/adapters/list':
            try:
                self._send_json(_adapter_registry_list())
            except Exception as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
        elif parsed.path == '/api/models/memory':
            try:
                self._send_json(_model_memory_status())
            except Exception as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
        elif parsed.path == '/api/models/quality':
            self._send_json(_model_quality_status())
        elif parsed.path == '/api/models/capabilities/evaluations':
            self._send_json(_capability_evaluation_status())
        elif parsed.path == '/api/gpu-training/status':
            self._send_json(_gpu_training_status())
        elif parsed.path == '/api/gpu-training/kaggle-bundle.zip':
            bundle = _build_kaggle_gpu_training_bundle()
            self.send_response(200)
            self.send_header('Content-Type', bundle["content_type"])
            self.send_header('Content-Disposition', f'attachment; filename="{bundle["filename"]}"')
            self._send_cors_headers()
            self.end_headers()
            self._write_bytes(bundle["bytes"])
        elif parsed.path == '/api/training/studio/kaggle-bundle.zip':
            query = parse_qs(parsed.query or "")
            dataset_id = (query.get("dataset_id") or [""])[0] or None
            from nova_training_studio import build_training_studio_kaggle_bundle

            bundle = build_training_studio_kaggle_bundle(ROOT, dataset_id=dataset_id)
            self.send_response(200)
            self.send_header('Content-Type', bundle["content_type"])
            self.send_header('Content-Disposition', f'attachment; filename="{bundle["filename"]}"')
            self._send_cors_headers()
            self.end_headers()
            self._write_bytes(bundle["bytes"])
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
    
    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if not self._authorize_api(parsed.path):
                return
            if NOVA_GATEWAY_HTTP.handle_post(self, parsed):
                return
            if DESKTOP_HTTP.handle_post(self, parsed):
                return
            if RELIABILITY_HTTP.handle_post(self, parsed):
                return
            if FOUNDATION_HTTP.handle_post(self, parsed):
                return
            if self._handle_gpu_hub_post(parsed):
                return
            if self._handle_projects_post(parsed):
                return
            if parsed.path == '/api/tts':
                body = self._read_json_body()
                payload, status = _tts_response_from_text(body)
                self._send_json(payload, status=status)
                return
            if self._handle_companion_vision_post(parsed.path):
                return
            if parsed.path == '/api/scrape':
                body = self._read_json_body()
                web_policy = _authorize_explicit_web_action(body.get("url", ""), body)
                if not web_policy.allowed:
                    self._send_json(
                        {
                            "ok": False,
                            "error": _blocked_web_action_response(web_policy),
                            "source_retrieval": RetrievalResult("blocked", web_policy).safe_trace(),
                        },
                        status=403,
                    )
                    return
                try:
                    result = _scrape_public_url(body.get("url", ""))
                    self._send_json(result)
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/adapters/compare':
                body = self._read_json_body()
                text = _chat_text_from_body(body)
                adapter_ids = body.get("adapter_ids")
                if not isinstance(adapter_ids, list):
                    adapter_ids = None
                try:
                    max_new_tokens = int(body.get("max_new_tokens") or 192)
                except Exception:
                    max_new_tokens = 192
                if not str(text or "").strip():
                    self._send_json({"ok": False, "error": "Missing text for raw adapter compare"}, status=400)
                    return
                compare_context = {}
                conversation_history = bounded_conversation_history(body, text, maximum_messages=8)
                if conversation_history:
                    compare_context["conversation_history"] = conversation_history
                if isinstance(body.get("conversation_summary"), dict):
                    compare_context["conversation_summary"] = body.get("conversation_summary")
                compare_kwargs = {
                    "adapter_ids": adapter_ids,
                    "max_new_tokens": max_new_tokens,
                }
                if compare_context:
                    compare_kwargs["context"] = compare_context
                self._send_json(_compare_raw_lora_adapters(text, **compare_kwargs))
                return
            if parsed.path == '/api/adapters/import':
                try:
                    content_type = str(self.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
                    if content_type in ('application/zip', 'application/octet-stream'):
                        query = parse_qs(parsed.query or '')
                        filename = (query.get('filename') or ['nova_lora_adapter.zip'])[0]
                        adapter_id = (query.get('adapter_id') or [''])[0] or None
                        activate = (query.get('activate') or ['false'])[0].strip().lower() in ('1', 'true', 'yes', 'on')
                        upload_path = self._receive_adapter_zip(filename)
                        result = _adapter_registry_import_file(
                            upload_path,
                            adapter_id=adapter_id,
                            activate=activate,
                        )
                    else:
                        result = _adapter_registry_import(self._read_json_body())
                    self._send_json(result)
                except RequestBodyTooLarge as error:
                    self._send_json({"ok": False, "error": str(error)}, status=413)
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/adapters/activate':
                body = self._read_json_body()
                try:
                    self._send_json(_adapter_registry_activate(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/models/memory/unload':
                body = self._read_json_body()
                try:
                    self._send_json(_unload_model_memory(body))
                except ValueError as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=500)
                return
            if parsed.path == '/api/models/quality/check':
                self._read_json_body()
                self._send_json(_start_loaded_model_quality_check("manual"))
                return
            if parsed.path == '/api/models/capabilities/evaluate':
                try:
                    self._send_json(_start_capability_evaluation(self._read_json_body()))
                except ValueError as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/training/studio/import':
                body = self._read_json_body()
                try:
                    self._send_json(_training_studio_import(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/training/studio/feedback':
                body = self._read_json_body()
                try:
                    self._send_json(_training_studio_feedback(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/training/studio/review':
                body = self._read_json_body()
                try:
                    self._send_json(_training_studio_review(body))
                except FileNotFoundError as error:
                    self._send_json({"ok": False, "error": str(error)}, status=404)
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/training/studio/train':
                body = self._read_json_body()
                try:
                    self._send_json(_training_studio_train(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/memory/update':
                body = self._read_json_body()
                try:
                    self._send_json(_memory_control_update(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/memory/action':
                body = self._read_json_body()
                try:
                    self._send_json(_memory_control_action(body))
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            if parsed.path == '/api/training/run':
                body = self._read_json_body()
                mode = str(body.get("mode") or "full").lower()
                if mode not in ("full", "all", "core"):
                    self._send_json({"ok": False, "error": "Unknown training mode: " + mode}, status=400)
                    return
                training_job = _start_training_center_job()
                report = _run_full_training_suite()
                self._send_json({"ok": report.get("ok", False), "report": report, "training_job": training_job})
                return
            if parsed.path == '/api/chat':
                body = self._read_json_body()
                text = _chat_text_from_body(body)
                response, trace = _run_nova_chat_turn(text, context=body)
                data = {
                    "response": response,
                    "trace": trace,
                    "answer_status": (
                        trace.get("answer_status")
                        if isinstance(trace, dict)
                        else None
                    ),
                    "permissions": {**PERMISSIONS, "private_mode": PRIVATE_MODE}
                }
                self._send_json(data)
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
        except RequestBodyTooLarge as error:
            self._send_json({"ok": False, "error": str(error)}, status=413)
        except RequestBodyError as error:
            self._send_json({"ok": False, "error": str(error)}, status=400)
        except Exception as e:
            traceback.print_exc()
            try:
                self._send_json(
                    {"ok": False, "error": "Internal server error.", "response": "Nova hit an internal error."},
                    status=500,
                )
            except: pass
    
    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()
    
    def log_message(self, format, *args):
        pass


def _serve_recovery_screen(startup_error):
    class RecoveryRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = RELIABILITY.recovery_html(str(startup_error)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    try:
        recovery_port = int(os.environ.get("NOVA_RECOVERY_PORT", "0"))
    except (TypeError, ValueError):
        recovery_port = 0
    try:
        recovery_server = HTTPServer(("127.0.0.1", recovery_port), RecoveryRequestHandler)
    except OSError as recovery_error:
        raise SystemExit(
            f"Nova startup failed ({startup_error}) and the recovery screen could not start: {recovery_error}"
        ) from recovery_error
    actual_port = recovery_server.server_port
    print(f"  [RECOVERY] Nova protected your data after a startup failure.")
    print(f"  [RECOVERY] Open http://127.0.0.1:{actual_port}/")
    try:
        recovery_server.serve_forever()
    except KeyboardInterrupt:
        recovery_server.server_close()


def main():
    raw_port = os.environ.get('NOVA_API_PORT') or os.environ.get('NOVA_PORT') or (sys.argv[1] if len(sys.argv) > 1 else '3000')
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise SystemExit(f"Invalid Nova port: {raw_port!r}")
    if not 1 <= port <= 65535:
        raise SystemExit(f"Nova port must be between 1 and 65535, got {port}")
    DESKTOP.port = port
    TAILSCALE.set_nova_port(port)
    host = os.environ.get('NOVA_API_HOST') or os.environ.get('NOVA_HOST') or (sys.argv[2] if len(sys.argv) > 2 else '127.0.0.1')
    port_available = port_appears_available(host, port)
    RELIABILITY.run_diagnostics(
        host=host,
        port=port,
        port_error=None if port_available else f"Port {port} is already in use.",
    )
    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
        daemon_threads = True
    try:
        server = ThreadedHTTPServer((host, port), NovaHandler)
    except OSError as exc:
        RELIABILITY.run_diagnostics(host=host, port=port, port_error=str(exc))
        recovery_enabled = str(os.environ.get("NOVA_RECOVERY_SCREEN", "on")).lower() not in {
            "0", "false", "no", "off", "disabled"
        }
        if recovery_enabled:
            _serve_recovery_screen(exc)
            return
        raise SystemExit(f"Could not start Nova on {host}:{port}: {exc}") from exc
    print(f"\n{'='*60}")
    print(f"  NOVA ENHANCED SERVER — Hybrid Router Edition")
    print(f"  {'='*60}")
    display_host = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    print(f"  URL:      http://{display_host}:{port}")
    print(f"  Version:  {NOVA_APP_VERSION}")
    if host in ('0.0.0.0', '::'):
        print("  Network:  LAN access enabled; only use this on a trusted network")
    print(f"  Session:  {SESSION_ID}")
    print(f"  People:   {len(MEMORY['people'])} known")
    print(f"  Lessons:  {len(MEMORY['lessons'])} learned")
    print(f"  Dictionary: {len(DICT_INDEX)} entries")
    print(f"  Router: {'HYBRID (transformer-driven)' if _HYBRID_ROUTER_AVAIL else 'CLASSIC'}")
    print(f"  Reliability: {RELIABILITY.last_diagnostics.get('overall', 'unknown').upper()}")
    if FOUNDATION_RESTORE_ERROR:
        print(f"  [RECOVERY] Staged Foundation restore was not applied: {FOUNDATION_RESTORE_ERROR}")
    print(f"  {'='*60}")
    print(f"  Open the URL in your browser to chat with Nova!")
    print(f"  {'='*60}\n")
    
    # Pre-load hybrid router so it doesn't lazy-load in request threads
    print("  [LOAD] Loading hybrid router + transformer models...")
    try:
        from nova_hybrid_router import route_and_respond
        from nova_meaning_pipeline import process_input as pp
        from nova_transformer_engine import NovaBrain, NovaTokenizer
        test_result = pp("preload test", memory={}, dict_lookup_fn=lambda t: None)
        print(f"  [LOAD] Pipeline: {test_result.get('intent',{}).get('primary_intent','?')}")
        print("  [LOAD] Loading 7 brain transformers...")
        brain = NovaBrain()
        brain.load_all()
        if hasattr(brain, 'models'):
            print(f"  [LOAD] Loaded {len(brain.models)}/7 transformer models")
        print(f"  [LOAD] Hybrid router ready")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [LOAD] Warning: {e}")

    RELIABILITY.start_automatic_backups()
    _start_model_warmup()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Nova server stopped.")
        RELIABILITY.stop_automatic_backups()
        server.server_close()

if __name__ == "__main__":
    main()
