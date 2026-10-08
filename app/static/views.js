// The three screens. They only build DOM from data they are given; reading
// and routing are in main.js. Text from the API is always added as text,
// never as HTML: reasons and comments are user input.

const STATUS = { PENDING: "Pending", DECLINED: "Declined", APPROVED: "Approved" };
export const ROLES = {
  RELATIONSHIP_MANAGER: "Relationship manager",
  REVIEWER: "Reviewer",
  MORTGAGE_PROCESS: "Mortgage process",
};

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value);
  }
  node.append(...children.filter((child) => child != null));
  return node;
}

const bps = (value) => `${value} bps`;
const points = (value) => `${(Number(value) / 100).toFixed(2)} percentage points`;
const off = (condition) => (condition ? { disabled: "" } : {});
const badge = (status) => el("span", { class: `badge ${status.toLowerCase()}` }, STATUS[status]);
const nameOf = (users, userId) => users.find((user) => user.id === userId)?.name ?? userId;

function when(timestamp) {
  const local = new Date(timestamp).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
  return el("time", { datetime: timestamp, title: timestamp }, local);
}

function application(applications, applicationId) {
  const customer = applications.find((a) => a.id === applicationId)?.customer_name;
  return { id: applicationId, customer: customer ?? "" };
}

function pageHead(title, subtitle, ...actions) {
  return el(
    "div",
    { class: "page-head" },
    el("div", {}, el("h1", {}, title), el("p", { class: "muted" }, subtitle)),
    el("div", { class: "head-actions" }, ...actions),
  );
}

const refreshButton = (onRefresh) =>
  el("button", { type: "button", "data-refresh": "", onclick: onRefresh }, "Refresh");

function table(headings, rows) {
  return el(
    "div",
    { class: "card table-wrap" },
    el(
      "table",
      {},
      el("thead", {}, el("tr", {}, ...headings.map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", {}, ...rows.map((cells) => el("tr", {}, ...cells.map((c) => el("td", {}, c))))),
    ),
  );
}

// What a request needs from the acting user: docs/ui-design.md, "Screens".
export function nextStep(request, user) {
  const mine = request.created_by === user.id;
  if (request.status === "PENDING" && !mine && user.roles.includes("REVIEWER")) {
    return "Awaiting your review";
  }
  // With an approval in force a declined proposal needs nothing: that approval stays.
  if (request.status === "DECLINED" && mine && request.approved_discount_bps == null) {
    return "Needs your revision";
  }
  if (request.status === "PENDING" && mine) return "Awaiting review";
  return "";
}

// The action the acting user can take on a request: docs/ui-design.md,
// "Actions". The API enforces these rules; this only decides what is offered.
export function actionFor(request, user) {
  const mine = request.created_by === user.id;
  if (mine && user.roles.includes("RELATIONSHIP_MANAGER")) return "revise";
  if (!mine && user.roles.includes("REVIEWER") && request.status === "PENDING") return "decide";
  return null;
}

// The approval in force, in words: docs/state-model.md. Null when nothing was approved.
function inForce(request) {
  if (request.approved_revision_number == null) return null;
  return `${bps(request.approved_discount_bps)} from revision ${request.approved_revision_number}`;
}

function actionNotes(request, user, users) {
  const mine = request.created_by === user.id;
  const creator = nameOf(users, request.created_by);
  const approved = inForce(request);
  const notes = [];
  if (user.roles.includes("RELATIONSHIP_MANAGER")) {
    if (!mine) notes.push(`Only ${creator} can revise this request.`);
    else if (request.status === "APPROVED") {
      notes.push(
        "Approved. You can revise it to ask for another discount; this approval stays in force until a new revision is approved.",
      );
    } else if (request.status === "DECLINED") {
      notes.push(
        approved
          ? `Declined. The approval of ${approved} stays in force. You can revise and resubmit.`
          : "Declined. You can revise and resubmit it.",
      );
    } else notes.push("Awaiting review. You can still revise it.");
  }
  if (user.roles.includes("REVIEWER")) {
    if (request.status === "PENDING") {
      notes.push(mine ? "Another reviewer must decide on your request." : "Awaiting your review.");
    } else if (!mine) notes.push(`Nothing to decide until ${creator} revises it.`);
  }
  if (notes.length === 0) notes.push("Your role has no actions on this request.");
  return notes;
}

export function message(title, text, action) {
  return el("div", { class: "card message" }, el("h1", {}, title), el("p", {}, text), action);
}

export const loading = () => el("p", { class: "muted loading" }, "Loading…");

// Forms -------------------------------------------------------------------

const field = (label, control, hint) =>
  el("label", { class: "field" }, el("span", {}, label), control, hint);

const values = (event) => Object.fromEntries(new FormData(event.currentTarget));

function discountField(value, disabled) {
  const describe = (v) => (v ? points(v) : "Whole basis points, from 1 to 200.");
  const hint = el("span", { class: "muted" }, describe(value));
  const input = el("input", {
    type: "number",
    name: "discount_bps",
    min: "1",
    max: "200",
    step: "1",
    required: "",
    value: String(value),
    ...off(disabled),
    oninput: () => (hint.textContent = describe(input.value)),
  });
  return field("Discount (bps)", input, hint);
}

const textField = (label, name, value, disabled) =>
  field(
    label,
    el("textarea", { name, rows: "4", maxlength: "1000", required: "", ...off(disabled) }, value),
  );

// An error from the contract, next to the form it belongs to.
function problem(error, extra) {
  const errors = error.code === "VALIDATION_ERROR" ? error.details.errors : null;
  return el(
    "div",
    { class: "alert", role: "alert", tabindex: "-1" },
    el("p", {}, error.message),
    Array.isArray(errors)
      ? el("ul", {}, ...errors.map((e) => el("li", {}, `${e.field}: ${e.message}`)))
      : null,
    extra,
  );
}

const BLOCKED = {
  stale: "This request changed while you were looking at it. Reload and review it again.",
  uncertain:
    "We couldn't confirm the result. Reload and review the latest state before taking another action.",
};

const blockNotice = (blocked, act) =>
  el(
    "div",
    { class: "alert warn", role: "alert", tabindex: "-1" },
    el("p", {}, BLOCKED[blocked]),
    el("button", { type: "button", onclick: act.onReload }, "Reload"),
  );

function reviseForm(draft, blocked, act) {
  const closed = draft.sending || blocked;
  return el(
    "form",
    {
      class: "form",
      oninput: (event) => act.onInput(values(event)),
      onsubmit: (event) => {
        event.preventDefault();
        act.onSubmit();
      },
    },
    discountField(draft.values.discount_bps, draft.sending),
    textField("Reason", "reason", draft.values.reason, draft.sending),
    draft.error ? problem(draft.error) : null,
    el(
      "div",
      { class: "buttons" },
      el("button", { type: "button", onclick: act.onCancel, ...off(draft.sending) }, "Cancel"),
      el(
        "button",
        { type: "submit", class: "primary", ...off(closed) },
        draft.sending ? "Sending…" : "Submit revision",
      ),
    ),
  );
}

function decideForm(request, draft, blocked, act) {
  const current = request.revisions.at(-1);
  const closed = draft?.sending || blocked;
  return el(
    "form",
    {
      class: "form",
      oninput: (event) => act.onInput(values(event)),
      onsubmit: (event) => {
        event.preventDefault();
        act.onSubmit(event.submitter.value);
      },
    },
    el("p", { class: "strong" }, `Deciding on revision ${current.number} · ${bps(current.discount_bps)}`),
    inForce(request)
      ? el(
          "p",
          { class: "muted" },
          `In force now: ${inForce(request)}. Approving replaces it; declining keeps it.`,
        )
      : null,
    textField("Comment", "comment", draft?.values.comment ?? "", draft?.sending),
    draft?.error ? problem(draft.error) : null,
    el(
      "div",
      { class: "buttons" },
      el("button", { type: "submit", value: "DECLINED", ...off(closed) }, "Decline"),
      el("button", { type: "submit", value: "APPROVED", class: "primary", ...off(closed) }, "Approve"),
    ),
  );
}

export function createForm(creating, act) {
  const app = creating.application;
  const head = [
    el("h2", {}, "New request"),
    el("p", { class: "strong" }, `${app.id} · ${app.customer_name}`),
  ];
  if (creating.phase === "uncertain") {
    return el(
      "div",
      { class: "form" },
      ...head,
      el(
        "div",
        { class: "alert warn", role: "alert", tabindex: "-1" },
        el("p", {}, "We couldn't confirm the result."),
        el("p", {}, "Retry sends the same request again. It cannot create a second one."),
      ),
      el("p", { class: "text" }, `${bps(creating.payload.discount_bps)} · ${creating.payload.reason}`),
      el(
        "div",
        { class: "buttons" },
        el("button", { type: "button", class: "primary", onclick: act.onSubmit }, "Retry"),
      ),
    );
  }
  const busy = creating.phase === "sending";
  const error = creating.error;
  const existing = error?.code === "REQUEST_ALREADY_EXISTS" ? error.details.request_id : null;
  return el(
    "form",
    {
      class: "form",
      oninput: (event) => act.onInput(values(event)),
      onsubmit: (event) => {
        event.preventDefault();
        act.onSubmit();
      },
    },
    ...head,
    discountField(creating.values.discount_bps, busy),
    textField("Reason", "reason", creating.values.reason, busy),
    error
      ? problem(
          error,
          existing
            ? el("a", { href: `#/requests/${existing}`, onclick: act.onCancel }, "Open the existing request")
            : null,
        )
      : null,
    el(
      "div",
      { class: "buttons" },
      el("button", { type: "button", onclick: act.onCancel, ...off(busy) }, "Cancel"),
      el("button", { type: "submit", class: "primary", ...off(busy) }, busy ? "Sending…" : "Submit request"),
    ),
  );
}

// Screens -----------------------------------------------------------------

export function requestsScreen({ requests, applications, users, user, onRefresh }) {
  const rows = requests.map((request) => {
    const app = application(applications, request.application_id);
    return [
      el(
        "div",
        {},
        el("a", { href: `#/requests/${request.id}`, class: "strong" }, app.id),
        el("div", { class: "muted" }, app.customer),
      ),
      badge(request.status),
      bps(request.current_discount_bps),
      request.approved_discount_bps == null
        ? el("span", { class: "muted" }, "None")
        : bps(request.approved_discount_bps),
      nameOf(users, request.created_by),
      when(request.updated_at),
      nextStep(request, user),
    ];
  });
  return el(
    "div",
    {},
    pageHead(
      "Requests",
      "Pricing exceptions, latest change first.",
      user.roles.includes("RELATIONSHIP_MANAGER")
        ? el("a", { href: "#/applications", class: "button" }, "New request")
        : null,
      refreshButton(onRefresh),
    ),
    rows.length === 0
      ? el("p", { class: "card empty" }, "No requests yet.")
      : table(
          [
            "Application",
            "Status",
            "Asked for",
            "Approved in force",
            "Requested by",
            "Updated",
            "Next step",
          ],
          rows,
        ),
  );
}

function decisionBlock(decision, users) {
  return el(
    "div",
    { class: `decision ${decision.outcome.toLowerCase()}` },
    el(
      "p",
      {},
      badge(decision.outcome),
      el("span", { class: "muted" }, ` by ${nameOf(users, decision.decided_by)} · `),
      el("span", { class: "muted" }, when(decision.decided_at)),
    ),
    el("p", { class: "text" }, decision.comment),
  );
}

function historyItem(revision, users, inForceNumber) {
  const decision = revision.decision;
  return el(
    "li",
    { class: "card" },
    el(
      "p",
      {},
      el("span", { class: "strong" }, `Revision ${revision.number} · ${bps(revision.discount_bps)}`),
      el("span", { class: "muted" }, " · ", when(revision.created_at)),
      revision.number === inForceNumber ? el("span", { class: "strong" }, " · In force") : null,
    ),
    el("p", { class: "text" }, revision.reason),
    decision ? decisionBlock(decision, users) : el("p", { class: "muted" }, "No decision yet."),
  );
}

// `draft` is the revise or decide the user is working on, or null. `blocked`
// says why nothing can be sent until the request has been read again, or is null.
export function requestScreen(screen) {
  const { request, applications, users, user, onRefresh, draft, blocked, act } = screen;
  const app = application(applications, request.application_id);
  const current = request.revisions.at(-1);
  const action = actionFor(request, user);
  let form = null;
  if (action === "decide") form = decideForm(request, draft, blocked, act);
  else if (action === "revise" && draft) form = reviseForm(draft, blocked, act);
  else if (action === "revise") {
    form = el(
      "div",
      { class: "buttons" },
      el(
        "button",
        { type: "button", class: "primary", "data-open": "", onclick: act.onOpen, ...off(blocked) },
        "Revise",
      ),
    );
  }
  return el(
    "div",
    {},
    el("a", { href: "#/requests", class: "back" }, "← Requests"),
    pageHead(
      `${app.id} · ${app.customer}`,
      `Requested by ${nameOf(users, request.created_by)}`,
      badge(request.status),
      refreshButton(onRefresh),
    ),
    el(
      "div",
      { class: "detail" },
      el(
        "section",
        { class: "card" },
        el("h2", {}, "Latest revision"),
        el("p", { class: "discount" }, bps(current.discount_bps)),
        el("p", { class: "muted" }, `Revision ${current.number} · Version ${request.version}`),
        el("h3", {}, "Reason"),
        el("p", { class: "text" }, current.reason),
        el("h3", {}, "Approved in force"),
        el("p", { class: "text" }, inForce(request) ?? "Nothing approved yet."),
      ),
      el(
        "section",
        { class: "card" },
        el("h2", {}, "Next step"),
        ...actionNotes(request, user, users).map((note) => el("p", {}, note)),
        // The decision on the current revision: why it was declined or approved.
        current.decision ? decisionBlock(current.decision, users) : null,
        blocked ? blockNotice(blocked, act) : null,
        form,
      ),
    ),
    el("h2", {}, "History"),
    el(
      "ol",
      { class: "history" },
      ...request.revisions.map((r) => historyItem(r, users, request.approved_revision_number)),
    ),
  );
}

function approvedCell(result, users) {
  if (result.kind === "ok") {
    const d = result.data;
    return el(
      "div",
      {},
      el("div", { class: "strong" }, bps(d.approved_discount_bps)),
      el(
        "div",
        { class: "muted" },
        `Revision ${d.revision_number}, approved by ${nameOf(users, d.decided_by)}`,
      ),
    );
  }
  if (result.kind === "error" && result.code === "NO_APPROVED_DISCOUNT") {
    return el("span", { class: "muted" }, "No approved discount");
  }
  return el("span", { class: "problem" }, "Could not be read");
}

// `approved` maps an application id to the result of its approved-discount
// call, or is null when the acting user is not the mortgage process.
// `onCreate` is null when the acting user cannot create requests.
export function applicationsScreen({ applications, requests, users, approved, onRefresh, onCreate }) {
  const rows = applications.map((app) => {
    const request = requests.find((r) => r.id === app.request_id);
    const cells = [
      el("div", {}, el("div", { class: "strong" }, app.id), el("div", { class: "muted" }, app.customer_name)),
      request
        ? el(
            "div",
            { class: "with-link" },
            badge(request.status),
            el("a", { href: `#/requests/${request.id}` }, "View request"),
          )
        : el(
            "div",
            { class: "with-link" },
            el("span", { class: "muted" }, "No request"),
            onCreate
              ? el("button", { type: "button", onclick: () => onCreate(app) }, "New request")
              : null,
          ),
    ];
    if (approved) cells.push(approvedCell(approved.get(app.id), users));
    return cells;
  });
  return el(
    "div",
    {},
    pageHead("Applications", "Mortgage applications and their requests.", refreshButton(onRefresh)),
    table(["Application", "Request", ...(approved ? ["Approved discount"] : [])], rows),
  );
}
