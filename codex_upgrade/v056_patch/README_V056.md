# Nova Creature v056 — Conversation Memory Loop

This patch adds the conversation layer.

It lets Nova track:

- recent turns
- current topic
- active goal
- last answer
- unresolved questions
- facts learned during conversation
- follow-up phrases like “that,” “it,” “do that,” and “what next”

## Apply

From the cloud project root:

```bash
python scripts/apply_v056_conversation_memory.py --project-root .
python scripts/check_v056_conversation_memory.py
python scripts/v056_gold_conversation_test.py
```

## Use

```bash
python scripts/v056_chat_once.py --message "We need conversation memory."
python scripts/v056_chat_once.py --message "Do that."
python scripts/v056_chat_once.py --message "What next?"
```

## What it does

Input -> conversation memory -> v052 role-brain router -> answer -> memory update

If `src/v052_role_brain_router.py` exists, v056 calls it.
If not, v056 uses a safe fallback answer.
