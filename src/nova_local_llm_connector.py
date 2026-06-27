"""
Nova Local LLM Cortex Connector
=================================
Connects Nova to a downloaded local LLM (Ollama, LM Studio) while keeping Nova's
own brain system (memory, dictionary, routing, role transformers, critic) in control.

Architecture:
  User message
  → Nova normalizer
  → Nova dictionary / meaning expansion
  → Nova memory lookup
  → Nova 7-role transformer route voting
  → Nova route selector → decides if local LLM should be called
  → Nova builds task-specific prompt
  → local LLM generates fluent answer
  → Nova critic checks answer
  → Nova final speech output
  → Nova saves training log
"""

import json, os, time, sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

# Try httpx first, then urllib (httpx is more modern)
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ─── Config ──────────────────────────────────────────────────
class LocalLLMConfig:
    """Configuration for local LLM connection."""
    
    DEFAULT_CONFIG = {
        "NOVA_USE_LOCAL_LLM": False,
        "NOVA_LOCAL_LLM_PROVIDER": "ollama",
        "NOVA_LOCAL_LLM_MODEL": "qwen2.5:1.5b",
        "NOVA_LOCAL_LLM_URL": "http://127.0.0.1:11434/api/generate",
        "NOVA_LOCAL_LLM_TIMEOUT": 30,
        "NOVA_LOCAL_LLM_FALLBACK": True,
        "NOVA_LOG_LOCAL_LLM_PROMPTS": True,
    }
    
    def __init__(self):
        self.config = dict(self.DEFAULT_CONFIG)
        self._load_from_env()
        self._load_from_file()
    
    def _load_from_env(self):
        """Load config from environment variables."""
        for key in self.DEFAULT_CONFIG:
            env_val = os.environ.get(key)
            if env_val is not None:
                if env_val.lower() in ("true", "1", "yes"):
                    self.config[key] = True
                elif env_val.lower() in ("false", "0", "no"):
                    self.config[key] = False
                else:
                    try:
                        self.config[key] = int(env_val)
                    except ValueError:
                        self.config[key] = env_val
    
    def _load_from_file(self):
        """Load config from .nova_llm_config file if present."""
        config_paths = [
            ROOT / ".nova_llm_config",
            ROOT / ".env",
        ]
        for path in config_paths:
            if path.exists():
                try:
                    with open(path) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, val = line.split("=", 1)
                                key = key.strip()
                                val = val.strip().strip("\"'")
                                if key in self.DEFAULT_CONFIG:
                                    if val.lower() in ("true", "1", "yes"):
                                        self.config[key] = True
                                    elif val.lower() in ("false", "0", "no"):
                                        self.config[key] = False
                                    else:
                                        try:
                                            self.config[key] = int(val)
                                        except ValueError:
                                            self.config[key] = val
                except Exception:
                    pass  # Silent fail on config load
    
    @property
    def use_local_llm(self) -> bool:
        return self.config.get("NOVA_USE_LOCAL_LLM", False)
    
    @property
    def provider(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_PROVIDER", "ollama")
    
    @property
    def model(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_MODEL", "qwen2.5:1.5b")
    
    @property
    def url(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/generate")
    
    @property
    def timeout(self) -> int:
        return int(self.config.get("NOVA_LOCAL_LLM_TIMEOUT", 30))
    
    @property
    def fallback(self) -> bool:
        return self.config.get("NOVA_LOCAL_LLM_FALLBACK", True)
    
    @property
    def log_prompts(self) -> bool:
        return self.config.get("NOVA_LOG_LOCAL_LLM_PROMPTS", True)


# ─── LLM Response Object ────────────────────────────────────
class LocalLLMResponse:
    """Structured response from a local LLM call."""
    
    def __init__(self, 
                 local_llm_used: bool = False,
                 provider: str = "",
                 model: str = "",
                 url: str = "",
                 prompt: str = "",
                 raw_output: str = "",
                 error: Optional[str] = None,
                 fallback_used: bool = False,
                 fallback_reason: str = "",
                 response_time_ms: float = 0.0):
        self.local_llm_used = local_llm_used
        self.provider = provider
        self.model = model
        self.url = url
        self.prompt = prompt
        self.raw_output = raw_output
        self.error = error
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason
        self.response_time_ms = response_time_ms
    
    def to_dict(self) -> dict:
        return {
            "local_llm_used": self.local_llm_used,
            "provider": self.provider,
            "model": self.model,
            "url": self.url,
            "prompt": self.prompt[:500] if self.prompt else "",  # Truncate for logs
            "raw_output": self.raw_output[:500] if self.raw_output else "",
            "error": self.error,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "response_time_ms": self.response_time_ms,
        }
    
    def __repr__(self) -> str:
        status = "✓ LLM" if self.local_llm_used else "✗ Fallback"
        return f"<LocalLLMResponse {status} {self.provider}/{self.model} ({self.response_time_ms:.0f}ms)>"


# ─── Local LLM Connector ────────────────────────────────────
class LocalLLMConnector:
    """Connects to local LLM runtimes (Ollama, LM Studio)."""
    
    def __init__(self, config: Optional[LocalLLMConfig] = None):
        self.config = config or LocalLLMConfig()
        self._log_file = ROOT / "nova_training_logs" / "local_llm_calls.jsonl"
        os.makedirs(self._log_file.parent, exist_ok=True)
    
    def is_available(self) -> bool:
        """Check if local LLM is configured and reachable."""
        if not self.config.use_local_llm:
            return False
        try:
            if HAS_HTTPX:
                resp = httpx.get(
                    self.config.url.rsplit("/api", 1)[0] if "/api" in self.config.url else self.config.url,
                    timeout=2.0
                )
                return resp.status_code < 500
            else:
                import urllib.request
                base_url = self.config.url.rsplit("/api", 1)[0] if "/api" in self.config.url else self.config.url
                req = urllib.request.Request(base_url, method="HEAD")
                urllib.request.urlopen(req, timeout=2)
                return True
        except Exception:
            return False
    
    def _build_prompt(self, context: dict) -> str:
        """Build the full prompt for the local LLM with Nova context."""
        system = f"""You are Nova Creature's language cortex. Nova's router has already selected the task route. Use the supplied memory, dictionary meanings, route context, and brain votes. Do not invent saved personal facts. Do not claim to remember anything unless Nova memory provides it. Answer clearly and directly.

NOVA IDENTITY:
You are Nova Creature, a multi-brain AI system.

SELECTED ROUTE:
{context.get('selected_route', 'general')}

USER MESSAGE:
{context.get('user_message', '')}

NORMALIZED MESSAGE:
{context.get('normalized_message', context.get('user_message', ''))}

DICTIONARY MEANINGS:
{context.get('dictionary_meanings', 'None')}

MEMORY MATCHES:
{context.get('memory_matches', 'None')}

BRAIN ROLE VOTES:
{context.get('brain_votes', 'None')}

ROUTE TRACE:
{context.get('route_trace', 'None')}

CURRENT TASK:
{context.get('task_instruction', 'Respond to the user.')}

OUTPUT RULES:
- Answer cleanly and directly.
- Do not expose hidden code internals unless asked.
- Do not invent personal facts.
- If memory is missing, say it is not saved yet.
- MEMORY RULE: When the user mentions a personal fact like "my favorite food is pizza", 
  Nova saves this in memory. When asked about it later, use the saved memory.
- IDENTITY RULE: The user's statements about themselves (like "I was born in 1980", 
  "my name is X") are facts ABOUT THE USER. Do not repeat them as if Nova is saying them.
  Answer in second person ("You were born in 1980") not first person.
- Keep the final answer useful and readable."""

        return system
    
    def _call_ollama(self, prompt: str) -> LocalLLMResponse:
        """Call Ollama API."""
        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_k": 40,
                "num_predict": 256,
            }
        }
        
        start = time.time()
        try:
            if HAS_HTTPX:
                resp = httpx.post(url, json=payload, timeout=self.config.timeout)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "")
            else:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.config.timeout) as r:
                    data = json.loads(r.read())
                raw = data.get("response", "")
            
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=True,
                provider="ollama",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error=None,
                fallback_used=False,
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="ollama",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output="",
                error=str(e),
                fallback_used=self.config.fallback,
                fallback_reason=f"Ollama error: {e}",
                response_time_ms=elapsed,
            )
    
    def _call_lm_studio(self, prompt: str) -> LocalLLMResponse:
        """Call LM Studio (OpenAI-compatible API)."""
        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Respond based on the system context."}
            ],
            "temperature": 0.7,
            "max_tokens": 256,
            "stream": False,
        }
        
        start = time.time()
        try:
            if HAS_HTTPX:
                resp = httpx.post(url, json=payload, timeout=self.config.timeout)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.config.timeout) as r:
                    data = json.loads(r.read())
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=True,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error=None,
                fallback_used=False,
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output="",
                error=str(e),
                fallback_used=self.config.fallback,
                fallback_reason=f"LM Studio error: {e}",
                response_time_ms=elapsed,
            )
    
    def generate(self, context: dict) -> LocalLLMResponse:
        """Main generation method. Routes to correct provider."""
        if not self.config.use_local_llm:
            return LocalLLMResponse(
                local_llm_used=False,
                fallback_used=self.config.fallback,
                fallback_reason="NOVA_USE_LOCAL_LLM is not enabled",
            )
        
        prompt = self._build_prompt(context)
        
        if self.config.provider == "lm_studio":
            response = self._call_lm_studio(prompt)
        else:  # Default to ollama
            response = self._call_ollama(prompt)
        
        if self.config.log_prompts:
            self._save_log(context, response)
        
        return response
    
    def _save_log(self, context: dict, response: LocalLLMResponse):
        """Save local LLM call to training log."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "user_input": context.get("user_message", ""),
            "normalized_input": context.get("normalized_message", ""),
            "dictionary_meanings": context.get("dictionary_meanings", ""),
            "memory_matches": context.get("memory_matches", ""),
            "selected_route": context.get("selected_route", ""),
            "brain_votes": context.get("brain_votes", ""),
            "prompt_sent": response.prompt[:500] if response.prompt else "",
            "raw_output": response.raw_output[:500] if response.raw_output else "",
            "error": response.error,
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
            "response_time_ms": response.response_time_ms,
            "provider": response.provider,
            "model": response.model,
            "local_llm_used": response.local_llm_used,
        }
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # Silent fail on log write


# ─── Singleton ────────────────────────────────────────────────
_LLM_CONNECTOR = None

def get_llm_connector():
    """Get or create the singleton LLM connector."""
    global _LLM_CONNECTOR
    if _LLM_CONNECTOR is None:
        _LLM_CONNECTOR = LocalLLMConnector()
    return _LLM_CONNECTOR


# ─── Quick self-test ─────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("NOVA LOCAL LLM CORTEX CONNECTOR — Self Test")
    print("=" * 60)
    
    connector = get_llm_connector()
    config = connector.config
    
    print(f"\nConfig:")
    print(f"  USE_LOCAL_LLM: {config.use_local_llm}")
    print(f"  PROVIDER: {config.provider}")
    print(f"  MODEL: {config.model}")
    print(f"  URL: {config.url}")
    print(f"  TIMEOUT: {config.timeout}s")
    print(f"  FALLBACK: {config.fallback}")
    
    available = connector.is_available()
    print(f"\nLocal LLM available: {available}")
    
    if available:
        print("\nTesting LLM generation...")
        context = {
            "user_message": "Hello, what can you do?",
            "selected_route": "general_conversation",
            "dictionary_meanings": "None",
            "memory_matches": "None",
            "brain_votes": "memory=0.3, critic=0.3, speech=0.4",
            "route_trace": "memory_transformer -> critic_conscience_transformer -> speech_output_transformer",
            "task_instruction": "Respond to the user's greeting.",
        }
        result = connector.generate(context)
        print(f"\nResult: {result}")
        print(f"  local_llm_used: {result.local_llm_used}")
        print(f"  provider: {result.provider}")
        print(f"  model: {result.model}")
        print(f"  fallback_used: {result.fallback_used}")
        print(f"  response_time_ms: {result.response_time_ms:.0f}")
        if result.error:
            print(f"  error: {result.error}")
        if result.raw_output:
            print(f"\n  raw_output: {result.raw_output[:300]}")
    else:
        print("\nLocal LLM not available. This is expected if Ollama/LM Studio is not running.")
        print("Fallback behavior will be used.")
    
    print("\nDone.")
