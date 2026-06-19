# Nova Creature v057 — Dictionary Memory Bridge

This patch connects the dictionary system to v056 conversation memory.

## What it adds

- Approved exact-answer dictionary
- Pending dictionary lessons
- Dictionary hit logging
- Conversation + dictionary router
- Scripts to add dictionary lessons
- Gold test

## Apply

```bash
python scripts/apply_v057_dictionary_memory.py --project-root .
python scripts/check_v057_dictionary_memory.py
python scripts/v057_gold_dictionary_test.py
```

## Use

```bash
python scripts/v057_add_dictionary_lesson.py --question "What is your creator name?" --answer "Mr. Novotron."
python scripts/v057_chat_once.py --message "What is your creator name?"
```

## Flow

```text
user message
-> dictionary exact lookup
-> if found: answer from dictionary
-> if not found: v056 conversation memory + role-brain router
-> save turn to conversation memory
```
