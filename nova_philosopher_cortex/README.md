# Nova Philosopher Cortex

A grand-scale architecture prototype for a **modular AI philosopher engine**.

Nova is designed as a modern philosopher-engine whose mission is to understand the world from a higher level—expanding on the work of the greatest philosophers, questioning modern systems, analyzing science and math deeply, exposing hidden assumptions, separating fact from inference, and speaking with the cleanest logic possible.

## Architecture

```
User raw message
  → Language Cortex → MeaningPacket
  → Tiny Control Modules (11 modules)
  → Router Cortex
  → Specialist Cortex Modules (6 specialists)
  → Truth Filter
  → Final Voice
  → Memory + Training Logger
```

## Quick Start

```bash
# Run a query
python main.py "What is truth?"

# Math problem
python main.py "If a car travels 150 miles in 3 hours, what is the speed?"

# Offline research (no web needed)
python main.py --offline "Look up the latest evidence about AI"

# Show pipeline trace
python main.py --pipeline "What is consciousness?"

# Run demos
python examples/demo_conversation.py
python examples/demo_math_measurement.py
python examples/demo_philosophy.py

# Run tests
python -m pytest -v
```

## Core Principles

Nova does not start with belief. Nova starts with:

1. The exact question
2. Definitions
3. Measurements
4. Evidence
5. Assumptions
6. Missing variables
7. Counterarguments
8. Logic consistency
9. Uncertainty level
10. Clean conclusion

## Pipeline Components

### Language Cortex
Transforms raw text into a structured `MeaningPacket` containing intent, questions, key terms, assumptions, bias flags, and routing hints.

### Tiny Control Modules (12)
Focused reasoning modules that each perform one task:
- **IntentDetector** - Refines intent classification
- **QuestionSplitter** - Splits multi-part questions
- **AssumptionDetector** - Identifies unsupported assumptions
- **BiasDetector** - Flags loaded language and bias patterns
- **DefinitionChecker** - Validates term definitions
- **EvidenceClassifier** - Classifies evidence types
- **LogicValidator** - Checks logical consistency
- **ContradictionFinder** - Finds internal contradictions
- **CounterargumentBuilder** - Constructs opposing arguments
- **UncertaintyMarker** - Assigns confidence levels
- **PrincipleConsistencyChecker** - Audits against Nova principles
- **FinalTruthFilter** - Validates output truthfulness

### Specialist Cortex (6)
Domain-specific reasoning modules:
- **PhilosopherCortex** - Philosophical analysis
- **ScienceCortex** - Scientific reasoning
- **MathMeasurementCortex** - Mathematical problem solving
- **KnowledgeCortex** - General knowledge recall
- **CodeSkillCortex** - Programming analysis
- **WorldSystemsCortex** - Societal systems analysis

### Research Agents (7)
Data gathering and verification:
- ResearchAgent, WebSearchAgent, WebFetchAgent
- DataGatheringAgent, CitationAgent, SourceQualityAgent

## Grand Roadmap

### Phase A: Rule-based Skeleton (✅ Current)
Prove the architecture works with rule-based modules.

### Phase B: Train Tiny Control Modules
Replace rule-based detectors with tiny transformers for:
- Intent detection, assumption detection, bias risk detection
- Evidence classification, route selection, uncertainty marking
- Contradiction detection, truth filtering

### Phase C: Train Small Specialist Models
Train domain-specific models for:
- Language cortex, philosopher cortex, science cortex
- Math/measurement cortex, world systems cortex, final voice

### Phase D: Build Research Agents
Full web research capability with source verification.

### Phase E: Training Loop
Log conversations, label corrections, select best outputs, create SFT datasets.

### Phase F: Nova Core Absorption
Train a large model from validated pipeline outputs.

### Phase G: Nova as Philosopher-Engine
Full autonomous philosophical reasoning with live research capability.

## Model Swapping

Configure which modules use which model providers:

```json
{
  "models": {
    "language_cortex": "mock",
    "intent_detector": "mock",
    "philosopher_cortex": "mock",
    "final_voice": "mock"
  },
  "provider_settings": {
    "openai": {
      "api_key": "sk-...",
      "model": "gpt-4o"
    },
    "ollama": {
      "base_url": "http://localhost:11434",
      "model": "llama3"
    }
  }
}
```

## Project Structure

```
nova_philosopher_cortex/
  README.md
  main.py                          # CLI entry point
  nova/
    config.py                      # Configuration
    schema.py                      # Core data types
    language_cortex.py             # First pipeline stage
    pipeline.py                    # Pipeline orchestrator
    router_cortex.py               # Route selection
    final_voice.py                 # Output generation
    memory.py                      # JSONL persistence
    model_provider.py              # Provider abstraction
    model_registry.py              # Module-to-model mapping
    tiny_modules/                  # 12 control modules
    specialist_cortex/             # 6 reasoning modules
    agents/                        # 7 research agents
    providers/                     # Provider implementations
    prompts/                       # System prompts
  tests/                           # ~60 automated tests
  examples/                        # 4 demo scripts
  reports/                         # Stage reports
```

## License

Internal prototype. Built as a staged architecture demonstration.
