# Stage 0 Report: Foundation

## Status: COMPLETE

### Files Created
- `pyproject.toml` - Project metadata
- `requirements.txt` - Python dependencies
- `nova/__init__.py` - Package init
- `nova/config.py` - Configuration system (NovaConfig with JSON/env/dataclass support)
- `nova/schema.py` - Core data schemas (MeaningPacket, NovaResponse, etc.)
- `nova/utils.py` - Utility functions (JSONL, timestamps, IDs)
- `nova/model_provider.py` - Model provider abstraction (Mock, OpenAI, Ollama)
- `reports/STAGE_0_FOUNDATION.md` - This report

### What Works
- NovaConfig loads from defaults, dict, JSON file
- All core schemas (MeaningPacket, NovaResponse, TruthVerdict, etc.)
- Utility functions for JSONL reading/writing, IDs, timestamps
- Model provider factory with Mock, OpenAI, Ollama providers
- Schema enums for IntentType, UncertaintyLevel, EvidenceClass, LogicStatus

### What's Placeholder
- OpenAI and Ollama providers are stubs (need API keys / packages)
- Config file loading not yet wired to CLI

### Next Stage
- Language Cortex (stage 1) with intent classification and MeaningPacket creation
