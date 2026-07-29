# Final Fix Report — Nova Practical Support

- status: DONE_WITH_CONCERNS
- implementation commit: `f8c6065` — `fix: close practical support release gaps`
- integration state: required cognitive, server, and browser hunks are verified
  in the current shared tree but intentionally remain uncommitted because their
  files contain large pre-existing user-owned baselines that do not exist in
  `HEAD`.

## Root-cause findings

1. `src/nova_cognitive_os.py` ran `_fast_general_conversation_answer` for every
   general-conversation route before LLM synthesis. The short input
   `I need some money` therefore became the generic “I’m here with you” answer
   and never called the small Qwen synthesizer.
2. Finance precedence recognized only a narrow set of question/advice words.
   Natural `is/are/would/could`, `good idea`, `worth it`, and
   `invest/investing` constructions fell through to open-ended or practical
   support.
3. The server’s existing practical-support exclusion covered conversation
   engine, natural-chat, and memory-v2 writes, but the rolling-summary function
   did not consume that exclusion and did not export a browser-safe flag.
   The browser then marked every non-private turn durable, wrote it to local
   storage, and sent it back in history eligible for later summaries.
4. The action-precedence regex treated any occurrence of
   `send/buy/pay/transfer` as a command. It could not distinguish
   `I cannot pay rent tomorrow` from a Nova-directed transaction.
5. Existing reviewed repairs covered all three subtypes, but managed firewall
   coverage was missing for `essential_expense_stress` and `income_help`, and
   no two-turn managed test joined transient context with no durable
   persistence.

## RED evidence

Python command:

```text
py -3.11 -m pytest -q tests/test_nova_practical_support_final_fix.py
```

Result before production changes:

```text
26 failed, 9 passed in 4.28s
```

Expected failure evidence:

- practical-support cognitive tests observed zero synthesizer calls;
- all eight natural finance-advice matrix cases returned `open_ended`;
- `I cannot pay rent tomorrow` returned `permission_action`;
- the remaining new hardship/income examples returned `open_ended`;
- subtype repair tests reached model escalation because classification did not
  select a reviewed practical-support repair;
- server traces had no
  `automatic_conversation_persistence_allowed` flag and still rolled
  summaries.

JavaScript command:

```text
node --test tests/js/practical-support-persistence.test.mjs
```

Result before browser changes:

```text
2 failed, 1 passed
```

Expected failure evidence:

- the financial-stress pair was not marked ephemeral and was stored;
- `buildChatPayload` had no `conversation_summary_history`, so later summaries
  could receive sensitive transient turns;
- the ordinary-chat control passed.

## Implementation

### Small-Qwen first chance

- The general fast-chat shortcut now excludes only a shared
  `practical_support` decision.
- The existing planner’s synthesis route and all raw adapter paths remain
  unchanged.
- A real `nova_cognitive_os.route` test with a stub Qwen synthesizer proves the
  synthesizer is called and an accepted relevant draft is preserved.
- Managed route tests prove reviewed repair is absent for the accepted draft
  and runs before escalation for the rejected draft.

### Finance and action precedence

- High-stakes finance domain matching now covers common singular/plural and
  investing variants.
- Advisory matching now covers natural auxiliary, value-judgment, and
  investment phrasing before practical support.
- Transaction permission matching is limited to imperatives, `please`,
  `can/could/will/would you`, and explicit requests for Nova to act.
- Added hardship patterns for being behind, not having enough for essentials,
  essential-expense budgeting, help finding work, and job-loss income need.

### Automatic persistence exclusion

- The server propagates
  `automatic_conversation_persistence_allowed` from the practical-support
  decision into the safe trace.
- Rolling-summary attachment exits before an update when that flag is false.
- The browser marks that user/assistant pair ephemeral. It stays in the
  in-memory recent transcript for the immediate follow-up but is excluded from
  local-storage serialization.
- The browser sends a separate durable-only
  `conversation_summary_history`; the server validates and uses it only for
  rolling summaries. The full recent transcript remains the generation
  context.
- Missing flags default to the prior durable behavior, preserving older
  servers/clients and ordinary chat.

## Added regression tests

Python:

- `test_practical_support_cognitive_route_gives_small_qwen_first_chance`
- `test_managed_cognitive_route_repairs_only_rejected_small_qwen_drafts`
- `test_natural_finance_advice_outranks_practical_support`
- `test_hardship_and_budgeting_support_do_not_become_finance_advice`
- `test_nova_directed_transactions_remain_permission_actions`
- `test_hardship_descriptions_are_practical_support`
- `test_practical_support_subtype_repairs_pass_the_managed_firewall`
- `test_server_blocks_practical_support_rolling_summary_and_exports_safe_flag`
- `test_ordinary_chat_keeps_rolling_summary_and_safe_flag`
- `test_two_turn_managed_practical_support_stays_focused_without_persistence`

JavaScript:

- `financial-stress turn remains transient and is excluded from stored context`
- `transient support context reaches immediate follow-up but not summary history`
- `ordinary chat remains durable`

## GREEN evidence

```text
py -3.11 -m pytest -q tests/test_nova_practical_support_final_fix.py
35 passed in 2.19s

node --test tests/js/practical-support-persistence.test.mjs
3 passed, 0 failed

py -3.11 -m pytest -q tests/test_nova_practical_support_final_fix.py tests/test_nova_conversation_intelligence.py tests/test_nova_response_repair.py tests/test_nova_turn_analyzer.py tests/test_nova_action_policy.py tests/test_nova_memory_control.py
120 passed in 5.32s

py -3.11 -m pytest -q tests/test_nova_cognitive_os.py
61 passed in 6.16s

py -3.11 -m pytest -q tests/test_nova_enhanced_server.py -k "practical_support or non_practical_turns_keep or conversation_summary or raw_adapter"
17 passed, 340 deselected in 4.08s

py -3.11 -m pytest -q tests/test_nova_enhanced_server.py::test_web_ui_sends_context_for_all_modes_and_shows_firewall_state tests/test_nova_enhanced_server.py::test_private_turn_cannot_update_supplied_conversation_summary tests/test_nova_enhanced_server.py::test_practical_support_blocks_automatic_memory_and_training_writes tests/test_nova_enhanced_server.py::test_non_practical_turns_keep_automatic_persistence_enabled
5 passed in 5.75s

py -3.11 -m py_compile src\nova_conversation_intelligence.py src\nova_cognitive_os.py nova_enhanced_server.py
exit 0
```

The existing selected server tests cover raw adapter bypass, private summary
suppression, ordinary persistence, and explicit-memory persistence. The
broader focused Python run covers action policy, memory control, shared
conversation intelligence, turn analysis, and reviewed repair.

## Uncommitted shared-tree integration hunks

These required lines remain unstaged:

- `src/nova_cognitive_os.py:1222-1227` — bypass the generic fast-chat
  shortcut for `practical_support`, allowing synthesis at line 1239 onward.
- `nova_enhanced_server.py:11540-11549` — export the automatic-persistence
  flag and suppress rolling-summary updates.
- `nova_enhanced_server.py:11561-11575` — validate and use the browser’s
  durable-only summary history.
- `nova_enhanced_server.py:11730-11732` — propagate the practical-support
  decision gate into the summary/browser flag.
- `nova_chat_web.html:5702-5705` — send durable-only summary history while
  retaining the complete transient generation history.
- `nova_chat_web.html:5727-5728` — mark excluded financial-stress turns
  temporary/ephemeral.

`HEAD` has none of the surrounding cognitive-route, rolling-summary, or
browser conversation-persistence baselines, so staging these files would
necessarily include thousands of unrelated pre-existing lines.

## Self-review

- Mutation check: removing the practical-support fast-chat guard makes the
  synthesizer-call tests fail; removing any finance/action/hardship branch
  fails its literal matrix; removing the server flag or summary early return
  fails the server persistence test; removing browser ephemerality or durable
  summary history fails the executable Node tests.
- Accepted Qwen text is not rewritten. Reviewed fallback is used only after
  the real managed answer firewall rejects the draft.
- The reviewed responses do not promise money, execute a transaction,
  fabricate a resource, or initiate web search.
- Raw Qwen/Dolphin modes skip shared classification and retain their prior
  behavior.
- Private mode and paused browser persistence still force ephemerality.
- Ordinary chat and explicit memory commands default to automatic persistence
  allowed.
- No Companion default, gateway permission rule, training route, model
  escalation policy, or `/api/chat` response shape was changed.
- The isolated staged diff passed `git diff --cached --check`. A whole-tree
  `git diff --check` still reports pre-existing trailing whitespace in the
  large user-owned server baseline around lines 1841-1882; none is in these
  task hunks.

## Concerns

- The release depends on the six exact current-tree integration hunks above.
  They cannot be represented by a clean commit until the user-owned cognitive,
  server, and browser baselines are committed or otherwise made available as a
  common parent.
- The isolated regression-test commit exercises the current shared tree. A
  checkout containing only `f8c6065` without those integration hunks will
  intentionally fail the cognitive and persistence regressions.
