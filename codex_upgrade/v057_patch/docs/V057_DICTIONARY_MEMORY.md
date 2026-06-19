# v057 Dictionary Memory Bridge

v057 connects exact approved dictionary answers to v056 conversation memory.

## Flow

```text
user message
-> dictionary exact lookup
-> if found: answer immediately
-> if not found: v056 conversation memory / v052 role router
-> update conversation memory
```

## Files

- `src/dictionary_memory.py`
- `src/v057_dictionary_conversation_router.py`
- `data/dictionary_memory/approved_answer_dictionary.json`
- `data/dictionary_memory/pending_dictionary_lessons.jsonl`
- `data/dictionary_memory/dictionary_hits.jsonl`

## Commands

```bash
python scripts/check_v057_dictionary_memory.py
python scripts/v057_gold_dictionary_test.py
python scripts/v057_add_dictionary_lesson.py --question "..." --answer "..." --approve
python scripts/v057_chat_once.py --message "..."
```
