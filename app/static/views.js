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
  if (request.status === "DECLINED" && mine) return "Needs your revision";
  if (request.status === "PENDING" && mine) return "Awaiting review";
  return "";
}

// What the acting user can and cannot do: docs/ui-design.md, "Actions".
// The API enforces these rules; this only explains them.
function actionNotes(request, user, users) {
  if (request.status === "APPROVED") return ["Approved requests cannot be changed."];
  const mine = request.created_by === user.id;
  const creator = nameOf(users, request.created_by);
  const notes = [];
  if (user.roles.includes("RELATIONSHIP_MANAGER")) {
    if (!mine) notes.push(`Only ${creator} can revise this request.`);
    else if (request.status === "DECLINED") notes.push("Declined. You can revise and resubmit it.");
    else notes.push("You can revise it until a reviewer decides.");
  }
  if (user.roles.includes("REVIEWER")) {
    if (mine) notes.push("Another reviewer must decide on your request.");
    else if (request.status === "PENDING") notes.push("Awaiting your review.");
    else notes.push(`Waiting for a revision from ${creator}.`);
  }
  if (notes.length === 0) notes.push("Your role has no actions on this request.");
  return notes;
}

export function message(title, text, action) {
  return el("div", { class: "card message" }, el("h1", {}, title), el("p", {}, text), action);
}

export const loading = () => el("p", { class: "muted loading" }, "Loading…");

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
      nameOf(users, request.created_by),
      when(request.updated_at),
      nextStep(request, user),
    ];
  });
  return el(
    "div",
    {},
    pageHead("Requests", "Pricing exceptions, latest change first.", refreshButton(onRefresh)),
    rows.length === 0
      ? el("p", { class: "card empty" }, "No requests yet.")
      : table(
          ["Application", "Status", "Discount", "Requested by", "Updated", "Next step"],
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

function historyItem(revision, users) {
  const decision = revision.decision;
  return el(
    "li",
    { class: "card" },
    el(
      "p",
      {},
      el("span", { class: "strong" }, `Revision ${revision.number} · ${bps(revision.discount_bps)}`),
      el("span", { class: "muted" }, " · ", when(revision.created_at)),
    ),
    el("p", { class: "text" }, revision.reason),
    decision ? decisionBlock(decision, users) : el("p", { class: "muted" }, "No decision yet."),
  );
}

export function requestScreen({ request, applications, users, user, onRefresh }) {
  const app = application(applications, request.application_id);
  const current = request.revisions.at(-1);
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
        el("h2", {}, "Current request"),
        el("p", { class: "discount" }, bps(current.discount_bps)),
        el("p", { class: "muted" }, `Revision ${current.number} · Version ${request.version}`),
        el("h3", {}, "Reason"),
        el("p", { class: "text" }, current.reason),
      ),
      el(
        "section",
        { class: "card" },
        el("h2", {}, "Next step"),
        ...actionNotes(request, user, users).map((note) => el("p", {}, note)),
        // The decision on the current revision: why it was declined or approved.
        current.decision ? decisionBlock(current.decision, users) : null,
      ),
    ),
    el("h2", {}, "History"),
    el("ol", { class: "history" }, ...request.revisions.map((r) => historyItem(r, users))),
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
export function applicationsScreen({ applications, requests, users, approved, onRefresh }) {
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
        : el("span", { class: "muted" }, "No request"),
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
