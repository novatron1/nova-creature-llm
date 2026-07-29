import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";


const html = await readFile(
  new URL("../../nova_chat_web.html", import.meta.url),
  "utf8",
);

function extractFunction(name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  assert.notEqual(start, -1, `${name} must exist`);
  const parameters = html.indexOf("(", start);
  let parameterDepth = 0;
  let brace = -1;
  for (let index = parameters; index < html.length; index += 1) {
    if (html[index] === "(") parameterDepth += 1;
    if (html[index] === ")") {
      parameterDepth -= 1;
      if (parameterDepth === 0) {
        brace = html.indexOf("{", index);
        break;
      }
    }
  }
  assert.notEqual(brace, -1, `${name} must have a function body`);
  let depth = 0;
  let quote = "";
  let escaped = false;
  for (let index = brace; index < html.length; index += 1) {
    const char = html[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "'" || char === '"' || char === "`") {
      quote = char;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return html.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

function createHarness() {
  const storage = new Map();
  const sandbox = {
    console,
    Date,
    JSON,
    localStorage: {
      getItem(key) {
        return storage.has(key) ? storage.get(key) : null;
      },
      removeItem(key) {
        storage.delete(key);
      },
      setItem(key, value) {
        storage.set(key, String(value));
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    `
      const CONVERSATION_MAX_MESSAGES = 16;
      const CONVERSATION_PREFS_STORAGE_KEY = "nova_prefs";
      const CONVERSATION_STORAGE_KEY = "nova_context";
      const DOLPHIN_LORA_ADAPTER_ID = "dolphin";
      const QWEN_LORA_ADAPTER_ID = "qwen";
      let conversationId = "test-conversation";
      let conversationPersistenceEnabled = true;
      let conversationSummary = {
        schema_version: "1.0",
        revision: 2,
        topics: ["ordinary earlier topic"]
      };
      let dolphinAdapterOnlyMode = false;
      let privateModeEnabled = false;
      let recentConversationHistory = [
        {role:"user", content:"ordinary hello", private:false, ephemeral:false},
        {role:"assistant", content:"ordinary reply", private:false, ephemeral:false}
      ];
      let trainedAdapterOnlyMode = false;
      function sensorSnapshotForNova(){ return null; }
      function updateConversationContextUi(){}
      ${extractFunction("storedConversationMessages")}
      ${extractFunction("validConversationSummary")}
      ${extractFunction("persistConversationContext")}
      ${extractFunction("buildChatPayload")}
      ${extractFunction("rememberConversationTurn")}
      globalThis.harness = {
        buildChatPayload,
        rememberConversationTurn,
        state(){
          return {
            messages: recentConversationHistory.map(item => ({...item})),
            summary: conversationSummary && {...conversationSummary}
          };
        }
      };
    `,
    sandbox,
  );
  return { harness: sandbox.harness, storage };
}

test("financial-stress turn remains transient and is excluded from stored context", () => {
  const { harness, storage } = createHarness();

  harness.rememberConversationTurn(
    "I need some money",
    "Tell me the amount and deadline and we can make a realistic plan.",
    {
      automatic_conversation_persistence_allowed: false,
      conversation_summary: {
        schema_version: "1.0",
        revision: 99,
        topics: ["I need some money"],
      },
    },
  );

  const state = harness.state();
  assert.equal(state.messages.length, 4);
  assert.equal(state.messages.at(-2).ephemeral, true);
  assert.equal(state.messages.at(-1).ephemeral, true);
  assert.deepEqual(Array.from(state.summary.topics), ["ordinary earlier topic"]);

  const saved = JSON.parse(storage.get("nova_context"));
  assert.deepEqual(
    saved.messages.map((item) => item.content),
    ["ordinary hello", "ordinary reply"],
  );
  assert.equal(JSON.stringify(saved).includes("I need some money"), false);
  assert.equal(JSON.stringify(saved).includes("amount and deadline"), false);
});

test("transient support context reaches immediate follow-up but not summary history", () => {
  const { harness } = createHarness();
  harness.rememberConversationTurn(
    "I need some money",
    "Is this urgent for rent, food, or bills?",
    { automatic_conversation_persistence_allowed: false },
  );

  const payload = harness.buildChatPayload("For rent tomorrow");

  assert.deepEqual(
    Array.from(payload.conversation_history, (item) => item.content),
    [
      "ordinary hello",
      "ordinary reply",
      "I need some money",
      "Is this urgent for rent, food, or bills?",
    ],
  );
  assert.deepEqual(
    Array.from(payload.conversation_summary_history, (item) => item.content),
    ["ordinary hello", "ordinary reply"],
  );
});

test("ordinary chat remains durable", () => {
  const { harness, storage } = createHarness();

  harness.rememberConversationTurn(
    "Tell me a joke",
    "Why did the robot cross the road?",
    { automatic_conversation_persistence_allowed: true },
  );

  const state = harness.state();
  assert.equal(state.messages.at(-2).ephemeral, false);
  assert.equal(state.messages.at(-1).ephemeral, false);
  const saved = JSON.parse(storage.get("nova_context"));
  assert.equal(saved.messages.at(-2).content, "Tell me a joke");
  assert.equal(saved.messages.at(-1).content, "Why did the robot cross the road?");
});
