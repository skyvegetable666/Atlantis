"use strict";

const $ = (id) => document.getElementById(id);

const STATUS_META = {
  // 实验状态
  ready: { label: "待启动", tone: "neutral" },
  running: { label: "运行中", tone: "info" },
  paused: { label: "已暂停", tone: "warning" },
  completed: { label: "已完成", tone: "success" },
  budget_exhausted: { label: "步数用尽", tone: "danger" },
  idle: { label: "已停止", tone: "neutral" },
  failed: { label: "未通过", tone: "danger" },
  // 居民状态
  active: { label: "可调度", tone: "success" },
  waiting: { label: "等待中", tone: "warning" },
  insufficient_credit: { label: "积分不足", tone: "danger" },
  error: { label: "调用出错", tone: "danger" },
  // 任务状态
  open: { label: "待接单", tone: "neutral" },
  claimed: { label: "进行中", tone: "info" },
  submitted: { label: "待验收", tone: "warning" },
  accepted: { label: "已完成", tone: "success" },
  cancelled: { label: "已取消", tone: "neutral" },
  // 调用状态
  reserved: { label: "已预留", tone: "neutral" },
  executing: { label: "执行中", tone: "info" },
  done: { label: "已完成", tone: "success" },
  unknown: { label: "待核查", tone: "warning" }
};

const EVENT_LABELS = {
  run_created: "创建实验并发布主任务",
  run_status: "变更实验运行状态",
  call_started: "开始执行调用",
  call_finished: "执行调用结束",
  publish_task: "发布子任务",
  claim_task: "接取任务",
  submit_task: "提交任务成果",
  accept_task: "验收任务并结算积分",
  cancel_task: "取消任务",
  send_message: "发送聊天消息",
  put_artifact: "保存工作成果",
  run_tool: "请求运行统计工具",
  wait: "进入等待状态",
  independent_score: "完成主任务独立评测",
  insufficient_credit: "积分不足，暂停调度",
  budget_exhausted: "达到步数上限，停止实验",
  run_idle: "无待办工作，实验停止",
  restart_recovery: "服务重启恢复，暂停待核查"
};

const CHAT_LABELS = {
  none: "禁止聊天",
  public: "仅允许群聊",
  private: "允许群聊与私聊"
};

const ERROR_LABELS = {
  invalid_params: "动作参数不符合接口要求",
  invalid_action: "动作类型无效",
  insufficient_credit: "可用积分不足",
  forbidden: "没有执行此动作的权限",
  state_conflict: "当前状态不允许此动作",
  invalid_recipient: "私聊接收者无效",
  chat_disabled: "当前实验未开放此聊天方式"
};

function eventOutcome(event) {
  const data = event.data || {};
  if (data.result) {
    const result = data.result;
    if (result.status === "rejected") {
      return { label: "被拒绝", tone: "danger", reason: ERROR_LABELS[result.code] || result.message || "请求被拒绝" };
    }
    if (result.status === "pending") return { label: "待执行", tone: "info", reason: "已授权，等待工具执行结果" };
    if (result.status === "completed") return { label: "成功", tone: "success", reason: "" };
  }
  if (event.kind === "call_finished") {
    if (data.status === "failed") return { label: "失败", tone: "danger", reason: data.error || "执行调用失败" };
    if (data.status === "unknown") return { label: "待核查", tone: "warning", reason: "调用结果尚未确认" };
    if (data.status === "done") return { label: "成功", tone: "success", reason: "" };
  }
  if (event.kind === "independent_score") {
    return { label: data.passed ? "通过" : "未通过", tone: data.passed ? "success" : "danger", reason: data.detail || "" };
  }
  if (event.kind === "call_started") return { label: "已开始", tone: "info", reason: "" };
  if (event.kind === "restart_recovery") return { label: "已暂停", tone: "warning", reason: "服务重启后暂停，未确认的调用需核查" };
  if (["insufficient_credit", "budget_exhausted"].includes(event.kind)) {
    return { label: "已停止", tone: "warning", reason: EVENT_LABELS[event.kind] };
  }
  if (event.kind === "run_status" && STATUS_META[data.status]) return { ...STATUS_META[data.status], reason: "" };
  return { label: "已记录", tone: "neutral", reason: "" };
}

function formatMoney(micros) {
  return `$${(micros / 1000000).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`;
}

function summarizeCosts(usage) {
  const real = usage.filter((u) => !u.simulated);
  const known = real.filter((u) => Number.isFinite(u.cost_micros) && u.cost_micros >= 0);
  const knownMicros = known.reduce((sum, u) => sum + u.cost_micros, 0);
  const unknownCount = real.length - known.length;
  const tokens = usage.reduce((sum, u) => sum + (u.input_tokens || 0) + (u.output_tokens || 0)
    + (u.cache_read_tokens || 0) + (u.cache_creation_tokens || 0), 0);
  let value = "暂无调用";
  let detail = `累计 ${tokens.toLocaleString()} tokens`;
  if (real.length) {
    value = unknownCount ? (known.length ? `已确认 ${formatMoney(knownMicros)}` : "待核实") : formatMoney(knownMicros);
    detail += unknownCount ? ` · ${unknownCount} 次费用待核实` : " · 费用已核实";
  }
  if (usage.length > real.length) {
    if (!real.length) value = "演示调用";
    detail += ` · ${usage.length - real.length} 次演示不计真实费用`;
  }
  return { value, detail, knownMicros, unknownCount };
}

function summarizeBehavior(state) {
  const payments = state.accounts.ledger.filter((entry) => entry.purpose === "task_payment"
    && state.agents[entry.from] && state.agents[entry.to]);
  return {
    messages: state.messages.length,
    rejectedMessages: state.events.filter((event) => event.kind === "send_message"
      && event.data?.result?.status === "rejected").length,
    childTasks: Object.values(state.tasks).filter((task) => task.parent_id).length,
    payments: payments.length,
    paidCredits: payments.reduce((sum, entry) => sum + entry.amount, 0)
  };
}

function residentActivity(state, id) {
  return {
    tasks: Object.values(state.tasks).filter((task) => task.assignee === id && ["claimed", "submitted"].includes(task.status)),
    latest: [...state.events].reverse().find((event) => event.actor === id && (event.data?.request || event.kind === "call_finished")),
    inFlight: Object.values(state.calls).find((call) => call.actor === id && ["reserved", "executing"].includes(call.status))
  };
}

function residentState(agent, runStatus) {
  if (agent.status !== "active") return STATUS_META[agent.status] || { label: agent.status, tone: "neutral" };
  if (["completed", "failed", "budget_exhausted"].includes(runStatus)) return { label: "本场已结束", tone: "neutral" };
  if (runStatus === "paused") return { label: "随实验暂停", tone: "warning" };
  if (runStatus === "ready") return STATUS_META.ready;
  if (runStatus === "idle") return { label: "未调度", tone: "neutral" };
  return STATUS_META.active;
}

let selected = null;
let snapshot = null;
let busy = false;

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = String(text);
  return node;
}

function badge(status) {
  const info = STATUS_META[status] || { label: status, tone: "neutral" };
  return outcomeBadge(info);
}

function outcomeBadge(info) {
  return element("span", `badge ${info.tone}`, info.label);
}

function empty(text) {
  return element("div", "empty", text);
}

function heading(title, detail = "") {
  const node = element("div", "section-head");
  node.append(element("h2", "", title), element("span", "", detail));
  return node;
}

function json(value) {
  return element("pre", "", JSON.stringify(value, null, 2));
}

function actorName(id) {
  if (!id) return "—";
  if (snapshot?.agents[id]) return snapshot.agents[id].name;
  if (id === "treasury") return "系统资金池";
  if (id === "resource_sink") return "系统调用扣费";
  return id;
}

async function api(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function setError(message) {
  const box = $("error");
  box.textContent = message ? `操作失败：${message}` : "";
  box.hidden = !message;
}

function switchView(view) {
  document.querySelectorAll(".view").forEach((node) => {
    node.hidden = node.id !== view;
  });
  document.querySelectorAll(".tabs .tab-btn").forEach((node) => {
    const chosen = node.dataset.view === view;
    node.classList.toggle("selected", chosen);
    if (chosen) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });
}

function metricCard(label, value, detail, valueClass = "") {
  const card = element("div", "metric");
  card.append(
    element("div", "metric-label", label),
    element("div", `metric-value ${valueClass}`.trim(), value),
    element("div", "metric-detail", detail)
  );
  return card;
}

function residentReason(agent) {
  if (agent.status === "insufficient_credit") {
    return { text: "可用积分不足以支付单次调用费，已暂停新动作。", danger: true };
  }
  if (agent.status === "error") {
    return { text: "最近一次模型或工具调用出错，实验已自动暂停。", danger: true };
  }
  if (agent.status === "waiting") {
    return { text: "当前无事可做，收到新消息或新任务后会自动唤醒。", danger: false };
  }
  return null;
}

function render() {
  const s = snapshot;
  if (!s) return;

  const statusInfo = STATUS_META[s.status] || { label: s.status, tone: "neutral" };
  $("status").className = `badge ${statusInfo.tone}`;
  $("status").textContent = statusInfo.label;

  const live = s.config.execution_mode === "live";
  $("run-name").textContent = `实验 #${s.id.slice(0, 8)}`;
  $("run-meta").textContent = `${live ? "真实模型" : "演示脚本"} · ${Object.keys(s.agents).length} 名居民 · ${CHAT_LABELS[s.config.chat_mode] || s.config.chat_mode}`;

  const canStart = ["ready", "paused", "idle"].includes(s.status);
  $("start").disabled = !canStart;
  $("start").textContent = s.status === "ready" ? "启动实验"
    : ["completed", "failed", "budget_exhausted"].includes(s.status) ? "本场已结束" : "继续实验";
  $("pause").disabled = s.status !== "running";

  const residents = Object.values(s.agents);
  const tasks = Object.values(s.tasks);
  const cost = summarizeCosts(s.usage);
  const behavior = summarizeBehavior(s);

  // 更新标签页计数
  $("count-tasks").textContent = String(tasks.length);
  $("count-messages").textContent = String(s.messages.length);
  $("count-ledger").textContent = String(s.accounts.ledger.length + s.usage.length);
  $("count-events").textContent = String(s.events.length);

  // 顶部 4 项核心指标
  const mainScore = s.scores["task-1"];
  const scoreValue = mainScore ? `${Math.round(mainScore.score * 100)} 分` : "待评测";
  const scoreClass = mainScore ? (mainScore.passed ? "is-success" : "is-danger") : "";

  $("metrics").replaceChildren(
    metricCard(
      "主任务评分",
      scoreValue,
      `已完成 ${tasks.filter((t) => t.status === "accepted").length} / ${tasks.length} 个任务`,
      scoreClass
    ),
    metricCard(
      "已用步数",
      `${s.budget.started} / ${s.budget.limit}`,
      s.budget.reserved > 0 ? `${s.budget.reserved} 步正在执行` : "每次模型或工具调用计 1 步"
    ),
    metricCard(
      "居民人数",
      `${residents.length} 名`,
      `初始总积分 ${s.config.resident_credits}，各自独立结算`
    ),
    metricCard(
      "真实调用费用",
      cost.value,
      cost.detail
    )
  );

  // 1. 概览视图
  const overview = $("overview");
  const behaviorCards = element("div", "behavior-metrics");
  behaviorCards.append(
    metricCard("成功投递消息", `${behavior.messages} 条`, `另有 ${behavior.rejectedMessages} 次发送被拒绝`),
    metricCard("已发布子任务", `${behavior.childTasks} 个`, "只统计已成功创建的子任务"),
    metricCard("居民间任务付款", `${behavior.payments} 次`, `已结算 ${behavior.paidCredits} 积分，不含系统赏金`)
  );
  const residentCards = element("div", "residents");
  for (const agent of residents) {
    const card = element("article", "card");
    const head = element("div", "card-head");
    head.append(element("h3", "card-title", agent.name), outcomeBadge(residentState(agent, s.status)));

    const stats = element("div", "resident-stats");
    stats.append(
      element("span", "resident-balance", agent.available),
      element("span", "resident-unit", "可用积分")
    );

    const frozen = agent.balance - agent.available;
    const meta = element(
      "p",
      "resident-meta",
      `总积分 ${agent.balance} · 冻结中 ${frozen} · 编号 ${agent.id}`
    );

    card.append(head, stats, meta);
    const activity = residentActivity(s, agent.id);
    const activityBox = element("div", "resident-activity");
    activityBox.append(element("p", "", `当前任务：${activity.tasks.length ? activity.tasks.map((task) => task.title).join("、") : "暂无进行中的任务"}`));
    if (activity.inFlight) {
      const call = activity.inFlight;
      activityBox.append(element("p", "", `${call.status === "executing" ? "正在执行" : "已预留"}：${call.kind === "model" ? "模型调用" : "工具调用"}`));
    }
    if (activity.latest) {
      const latest = activity.latest;
      const outcome = eventOutcome(latest);
      const row = element("div", "activity-row");
      row.append(element("span", "", `最近动作：${EVENT_LABELS[latest.kind] || latest.kind}`), outcomeBadge(outcome));
      activityBox.append(row);
      if (outcome.reason) activityBox.append(element("p", `activity-reason ${outcome.tone}`, outcome.reason));
    } else {
      activityBox.append(element("p", "", "最近动作：尚无记录"));
    }
    card.append(activityBox);
    const reason = residentReason(agent);
    if (reason) {
      card.append(element("div", `status-reason ${reason.danger ? "danger" : ""}`.trim(), reason.text));
    }
    residentCards.append(card);
  }

  const mainTask = s.tasks["task-1"];
  const overviewGrid = element("div", "overview-grid");

  const workCard = element("article", "card");
  const workHead = element("div", "card-head");
  workHead.append(element("h3", "card-title", `主任务：${mainTask.title}`), badge(mainTask.status));
  workCard.append(
    workHead,
    element("p", "task-desc", mainTask.spec),
    element("p", "card-sub", `验收标准：${mainTask.acceptance}`),
    json(mainTask.input)
  );

  const rulesCard = element("article", "card");
  rulesCard.append(
    element("div", "card-head", ""),
    element("p", "task-desc", `聊天权限：${CHAT_LABELS[s.config.chat_mode]}。`),
    element("p", "task-desc", `积分规则：主任务赏金 ${s.config.main_reward} 积分；居民每调用一次模型或工具扣除 ${s.config.demo_call_fee} 积分。`),
    element("p", "card-sub", live ? "当前为真实模型自主决策模式。" : "当前为演示脚本模式，按预设步骤验证委托与验收流程。")
  );
  rulesCard.querySelector(".card-head").append(element("h3", "card-title", "本场规则说明"));

  overviewGrid.append(workCard, rulesCard);
  overview.replaceChildren(
    heading("行为摘要", "统计已发生的行为，不自动判定合作是否有效"),
    behaviorCards,
    heading("居民状态", "点击顶部「积分与调用」可查看账单明细"),
    residentCards,
    heading("当前任务与规则"),
    overviewGrid
  );

  // 2. 任务与成果视图
  const taskList = element("div", "task-list");
  for (const task of tasks) {
    const card = element("article", "task-card");
    card.id = `task-card-${task.id}`;

    const head = element("div", "card-head");
    head.append(element("h3", "card-title", task.title), badge(task.status));
    card.append(
      head,
      element("p", "task-desc", task.spec),
      element("p", "card-sub", `验收标准：${task.acceptance}`)
    );

    const meta = element("div", "task-meta");
    meta.append(
      element("span", "reward-tag", `赏金 ${task.reward} 积分`),
      element("span", "", `发布方：${actorName(task.publisher)}`),
      element("span", "", `接单方：${task.assignee ? actorName(task.assignee) : "暂无人接单"}`),
      element("span", "", task.parent_id ? `关联主任务：${task.parent_id}` : "类型：主任务"),
      element("span", "mono", `编号 ${task.id}`)
    );
    card.append(meta);

    const artifact = s.artifacts[task.artifact_id];
    if (artifact) {
      const box = element("div", "artifact-box");
      box.append(
        element("p", "artifact-label", `提交成果（作者：${actorName(artifact.owner)} · 编号 ${artifact.id}）`),
        json(artifact.content)
      );
      card.append(box);
    }

    const score = s.scores[task.id];
    if (score) {
      const banner = element("div", `score-banner ${score.passed ? "pass" : "fail"}`);
      banner.append(
        element("span", "", `系统评测：${score.passed ? "通过" : "未通过"}（${Math.round(score.score * 100)} / 100 分）`),
        element("span", "mono", score.detail)
      );
      card.append(banner);
    }

    taskList.append(card);
  }
  $("tasks").replaceChildren(heading("任务列表", `共 ${tasks.length} 个任务`), taskList);

  // 3. 聊天记录视图
  const messageWrap = element("div", "message-list");
  for (const message of s.messages) {
    const card = element("article", "message");
    const head = element("div", "message-header");
    const route = element(
      "span",
      "message-sender",
      `${actorName(message.sender)} → ${message.recipient ? actorName(message.recipient) : "所有人"}`
    );
    const channelTag = element(
      "span",
      `badge ${message.recipient ? "purple" : "neutral"}`,
      message.recipient ? "私聊" : "群聊"
    );
    head.append(route, channelTag);
    card.append(head, element("p", "message-body", message.body));
    messageWrap.append(card);
  }
  $("messages").replaceChildren(
    heading("聊天记录", `共 ${s.messages.length} 条消息`),
    s.messages.length ? messageWrap : empty(behavior.rejectedMessages
      ? `尚无成功投递的消息；另有 ${behavior.rejectedMessages} 次发送被拒绝。原因见「操作日志」。`
      : "暂无成功投递的消息。居民发送成功的群聊或私聊会显示在这里。")
  );

  // 4. 积分与调用视图
  const ledger = $("ledger");
  ledger.replaceChildren(
    heading("积分转账明细", "点击关联编号可跳转到对应任务或日志"),
    table(
      ["关联对象", "付款方", "收款方", "变动积分", "用途说明"],
      s.accounts.ledger.map((entry) => {
        const isTask = Boolean(s.tasks[entry.id]);
        const refBtn = element("button", "link-button mono", `${entry.id} →`);
        refBtn.type = "button";
        refBtn.title = isTask ? "点击查看对应任务" : "点击查看操作日志";
        refBtn.addEventListener("click", () => {
          if (isTask) {
            switchView("tasks");
            $(`task-card-${entry.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
          } else {
            switchView("events");
          }
        });
        const amountCell = element("span", "td-amount", `${entry.amount} 积分`);
        return [
          refBtn,
          actorName(entry.from),
          actorName(entry.to),
          amountCell,
          entry.purpose === "task_payment" ? "任务验收结算" : "模型/工具调用费"
        ];
      }),
      "暂无已结算的积分变动记录。"
    ),
    heading("模型与工具调用明细", "未返回真实价格的调用会标记为待核实"),
    table(
      ["调用编号", "执行居民", "服务提供方", "输入 / 输出 Tokens", "真实费用"],
      s.usage.map((u) => [
        element("span", "mono td-muted", u.call_id),
        actorName(u.actor),
        u.provider,
        element("span", "mono", `${u.input_tokens} / ${u.output_tokens}`),
        u.cost_micros === null
          ? badge("unknown")
          : `${formatMoney(u.cost_micros)}${u.simulated ? "（演示）" : ""}`
      ]),
      "暂无模型或工具调用记录。"
    )
  );

  // 5. 操作日志视图
  const openEvents = new Set(
    [...$("events").querySelectorAll("details[open]")].map((node) => node.dataset.sequence)
  );
  const eventList = element("div", "event-list");
  for (const event of [...s.events].reverse()) {
    const detail = element("details", "event");
    detail.dataset.sequence = String(event.sequence);
    detail.open = openEvents.has(String(event.sequence));

    const summary = element("summary");
    const left = element("div", "event-left");
    left.append(
      element("span", "event-arrow", "▸"),
      element("span", "mono td-muted", `#${String(event.sequence).padStart(2, "0")}`),
      element("span", "event-title", EVENT_LABELS[event.kind] || event.kind)
    );

    const right = element("div", "event-right");
    const outcome = eventOutcome(event);
    right.append(
      outcomeBadge(outcome),
      element("span", "", actorName(event.actor)),
      element("span", "mono", new Date(event.time).toLocaleTimeString("zh-CN", { hour12: false })),
      element("span", "event-action-hint", "详情")
    );

    summary.append(left, right);
    const body = element("div", "event-body");
    if (outcome.reason) {
      summary.append(element("span", `event-reason ${outcome.tone}`, outcome.reason));
      body.append(element("p", "", outcome.reason));
    }
    body.append(json(event.data));
    detail.append(summary, body);
    eventList.append(detail);
  }
  $("events").replaceChildren(
    heading("操作日志", "点击任意行可展开查看原始参数"),
    s.events.length ? eventList : empty("暂无操作日志。")
  );
}

function table(headers, rows, emptyText) {
  if (!rows.length) return empty(emptyText);
  const wrap = element("div", "table-wrap");
  const tab = element("table");
  const head = element("thead");
  const tr = element("tr");
  headers.forEach((text) => tr.append(element("th", "", text)));
  head.append(tr);
  tab.append(head);

  const body = element("tbody");
  rows.forEach((row) => {
    const tr = element("tr");
    row.forEach((value) => {
      const td = element("td");
      if (value instanceof Node) td.append(value);
      else td.textContent = String(value);
      tr.append(td);
    });
    body.append(tr);
  });
  tab.append(body);
  wrap.append(tab);
  return wrap;
}

async function refresh() {
  if (busy) return;
  busy = true;
  try {
    const runs = await api("/api/runs");
    if (!selected || !runs.some((r) => r.id === selected)) {
      selected = runs[0]?.id;
    }
    const options = runs.map((run) => {
      const statusLabel = STATUS_META[run.status]?.label || run.status;
      const modeLabel = run.config.execution_mode === "live" ? "真实模型" : "演示脚本";
      const option = element(
        "option",
        "",
        `#${run.id.slice(0, 6)} · ${modeLabel} (${run.config.agent_count}人) · ${statusLabel}`
      );
      option.value = run.id;
      return option;
    });
    $("run-select").replaceChildren(...options);
    $("run-select").value = selected || "";

    if (selected) {
      const id = selected;
      const data = await api(`/api/runs/${id}`);
      if (id === selected) {
        snapshot = data;
        render();
      }
    }
  } catch (e) {
    setError(e.message);
  } finally {
    busy = false;
  }
}

function bindControls() {
  $("run-select").addEventListener("change", async (event) => {
    selected = event.target.value;
    setError("");
    await refresh();
  });

  document.querySelectorAll(".tabs .tab-btn").forEach((button) =>
    button.addEventListener("click", () => switchView(button.dataset.view))
  );

  $("create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("create-submit");
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "创建中…";
    setError("");
    try {
      const result = await api("/api/runs", {
        execution_mode: $("mode").value,
        agent_count: Number($("agents").value),
        max_calls: Number($("calls").value),
        chat_mode: $("chat").value
      });
      selected = result.id;
      await refresh();
      switchView("overview");
      $("create-panel").open = false;
      $("create-panel").querySelector("summary").focus();
    } catch (e) {
      setError(e.message);
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });

  for (const action of ["start", "pause"]) {
    $(action).addEventListener("click", async () => {
      setError("");
      const button = $(action);
      button.disabled = true;
      button.textContent = action === "start" ? "启动中…" : "暂停中…";
      try {
        await api(`/api/runs/${selected}/${action}`, {});
        await refresh();
      } catch (e) {
        setError(e.message);
        await refresh();
      }
    });
  }
}

async function init() {
  try {
    const config = await api("/api/capabilities");
    $("mode").querySelector('[value="live"]').disabled = !config.live_available;
    $("model-description").textContent = config.live_available
      ? `已连接模型：${config.model}`
      : "未配置真实模型 API，当前仅支持演示脚本。";
  } catch (e) {
    setError(e.message);
  }
  await refresh();
  setInterval(refresh, 1500);
}

if (typeof document !== "undefined") {
  bindControls();
  init();
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { eventOutcome, formatMoney, summarizeCosts, summarizeBehavior, residentActivity, residentState };
}
