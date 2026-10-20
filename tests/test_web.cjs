"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  eventOutcome, formatMoney, summarizeCosts, summarizeBehavior, residentActivity, residentState
} = require("../atlantis/web/app.js");

test("known real fees are added, including fees below one cent", () => {
  const result = summarizeCosts([{ cost_micros: 120000 }, { cost_micros: 3456 }]);
  assert.equal(result.value, "$0.123456");
  assert.equal(result.knownMicros, 123456);
  assert.equal(result.unknownCount, 0);
  assert.equal(formatMoney(1), "$0.000001");
});

test("partially known costs remain an explicitly incomplete total", () => {
  const result = summarizeCosts([{ cost_micros: 50000 }, { cost_micros: null }]);
  assert.equal(result.value, "已确认 $0.05");
  assert.equal(result.unknownCount, 1);
  assert.match(result.detail, /1 次费用待核实/);
});

test("unknown, absent and simulated fees never become a confirmed real zero", () => {
  assert.equal(summarizeCosts([]).value, "暂无调用");
  assert.equal(summarizeCosts([{ cost_micros: null }]).value, "待核实");
  assert.equal(summarizeCosts([{ cost_micros: 0, simulated: true }]).value, "演示调用");
  assert.equal(summarizeCosts([{ cost_micros: 0 }]).value, "$0.00");
  assert.equal(summarizeCosts([{ cost_micros: -1 }]).unknownCount, 1);
});

test("simulated estimates do not inflate real fees and token totals include cache", () => {
  const result = summarizeCosts([
    { cost_micros: 20000, input_tokens: 12, output_tokens: 3, cache_read_tokens: 8, cache_creation_tokens: 2 },
    { cost_micros: 1000000, simulated: true }
  ]);
  assert.equal(result.value, "$0.02");
  assert.match(result.detail, /25 tokens/);
  assert.match(result.detail, /1 次演示不计真实费用/);
});

test("a rejected send is distinguished from successful delivery without opening JSON", () => {
  const outcome = eventOutcome({ kind: "send_message", data: {
    result: { status: "rejected", code: "invalid_params", message: "Unexpected action parameters." }
  } });
  assert.equal(outcome.label, "被拒绝");
  assert.equal(outcome.tone, "danger");
  assert.equal(outcome.reason, "动作参数不符合接口要求");
  assert.equal(eventOutcome({ kind: "send_message", data: { result: { status: "completed" } } }).label, "成功");
});

test("pending tools, failed calls and negative evaluations do not look successful", () => {
  assert.equal(eventOutcome({ kind: "run_tool", data: { result: { status: "pending" } } }).label, "待执行");
  const failed = eventOutcome({ kind: "call_finished", data: { status: "failed", error: "Connection failed." } });
  assert.equal(failed.label, "失败");
  assert.equal(failed.reason, "Connection failed.");
  assert.equal(eventOutcome({ kind: "independent_score", data: { passed: false } }).label, "未通过");
  assert.equal(eventOutcome({ kind: "unrecognized", data: {} }).label, "已记录");
});

test("behavior counts actual deliveries, created tasks and resident payments separately", () => {
  const state = {
    agents: { ada: {}, lin: {} },
    messages: [{ sender: "lin", recipient: "ada", body: "hello" }],
    tasks: { main: { parent_id: null }, child: { parent_id: "main" } },
    events: [
      { kind: "send_message", data: { result: { status: "rejected" } } },
      { kind: "send_message", data: { result: { status: "completed" } } },
      { kind: "publish_task", data: { result: { status: "rejected" } } }
    ],
    accounts: { ledger: [
      { purpose: "task_payment", from: "treasury", to: "ada", amount: 60 },
      { purpose: "task_payment", from: "ada", to: "lin", amount: 8 },
      { purpose: "prototype_call_fee", from: "lin", to: "resource_sink", amount: 1 }
    ] }
  };
  assert.deepEqual(summarizeBehavior(state), { messages: 1, rejectedMessages: 1, childTasks: 1, payments: 1, paidCredits: 8 });
  state.messages = [];
  assert.equal(summarizeBehavior(state).messages, 0);
  assert.equal(summarizeBehavior(state).rejectedMessages, 1);
});

test("resident activity respects ownership, task state and event order", () => {
  const rejected = { actor: "lin", kind: "send_message", data: { request: {}, result: { status: "rejected" } } };
  const state = {
    tasks: {
      finished: { assignee: "lin", status: "accepted" },
      active: { assignee: "ada", status: "claimed" },
      pending: { assignee: "lin", status: "submitted" }
    },
    events: [rejected, { actor: "ada", kind: "submit_task", data: { request: {} } }],
    calls: { previous: { actor: "lin", status: "done" }, current: { actor: "ada", status: "executing" } }
  };
  const eventsBefore = [...state.events];
  const activity = residentActivity(state, "lin");
  assert.deepEqual(activity.tasks, [state.tasks.pending]);
  assert.equal(activity.latest, rejected);
  assert.equal(activity.inFlight, undefined);
  assert.deepEqual(state.events, eventsBefore);
  assert.equal(residentActivity(state, "ada").inFlight, state.calls.current);
});

test("ended and paused runs do not label active residents as currently working", () => {
  assert.equal(residentState({ status: "active" }, "completed").label, "本场已结束");
  assert.equal(residentState({ status: "active" }, "paused").label, "随实验暂停");
  assert.equal(residentState({ status: "active" }, "running").label, "可调度");
  assert.equal(residentState({ status: "error" }, "paused").label, "调用出错");
});
