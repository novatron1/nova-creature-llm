# v056 Conversation Memory Loop

v056 adds conversation continuity.

## Files

- `src/conversation_memory.py`
- `src/v056_conversation_router.py`
- `scripts/v056_chat_once.py`
- `scripts/v056_gold_conversation_test.py`
- `scripts/check_v056_conversation_memory.py`

## Memory data

Stored in:

```text
data/conversation_memory/
```

## Conversation flow

```text
user message
-> conversation memory context
-> role-brain router
-> answer
-> update conversation state
```

## Test

```bash
python scripts/check_v056_conversation_memory.py
python scripts/v056_gold_conversation_test.py
```

## Manual use

```bash
python scripts/v056_chat_once.py --message "We need conversation memory."
python scripts/v056_chat_once.py --message "Do that."
python scripts/v056_chat_once.py --message "What next?"
```
