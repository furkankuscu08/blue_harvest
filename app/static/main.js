// Who the user acts as, which screen is shown, reading its data, and wiring
// the forms to the rules in actions.js. The behaviour is described in
// docs/ui-design.md.

import * as actions from "./actions.js";
import * as api from "./api.js";
import * as views from "./views.js";

const USER_KEY = "acting-user";
const content = document.getElementById("content");
const select = document.getElementById("acting-user");
const roles = document.getElementById("acting-roles");
const dialog = document.getElementById("create");

let users = null; // null until the list of users has been read
let user = null;
// Increases with every read. A response is shown only if no newer read has
// started since and the acting user and the address are still the same.
let reads = 0;
// The request on screen, kept so that an action can draw it again without
// reading it: { request, applications, actor, blocked }. `blocked` is set
// when nothing may be sent until the request has been read again; only a
// read replaces this object, and with it the block.
let shown = null;
// The revise or decide the user is working on, and the create in the dialog.
// The create is not tied to a screen, so the back button cannot discard it.
let draft = null;
let creating = null;

function route() {
  const [screen, requestId] = location.hash.replace(/^#\/?/, "").split("/");
  if (screen === "requests" && requestId) return { screen: "request", requestId };
  if (screen === "applications") return { screen: "applications" };
  return { screen: "requests" };
}

function setUser(userId) {
  user = users.find((u) => u.id === userId) ?? null;
  if (user) sessionStorage.setItem(USER_KEY, user.id);
  else sessionStorage.removeItem(USER_KEY);
  select.value = user?.id ?? "";
  roles.replaceChildren(
    ...(user?.roles ?? []).map((role) => views.el("span", { class: "role" }, views.ROLES[role])),
  );
}

// Reading -----------------------------------------------------------------

// `user` is passed in: the acting user may change while the calls are running.
async function load({ screen, requestId }, user) {
  if (screen === "request") {
    return [await Promise.all([api.getRequest(user, requestId), api.getApplications(user)]), null];
  }
  const lists = await Promise.all([api.getRequests(user), api.getApplications(user)]);
  if (screen !== "applications" || !user.roles.includes("MORTGAGE_PROCESS")) return [lists, null];
  if (lists[1].kind !== "ok") return [lists, null];
  // The approved discount comes from its own endpoint, one call per application.
  const applications = lists[1].data;
  const results = await Promise.all(applications.map((a) => api.getApprovedDiscount(user, a.id)));
  return [lists, new Map(applications.map((a, i) => [a.id, results[i]]))];
}

const again = () => show({ focus: "content" });

function failure(result, screen) {
  if (result.kind === "error" && result.code === "UNKNOWN_USER") {
    setUser(null);
    return views.message("Choose who to act as", "The selected user is no longer known.");
  }
  if (result.kind === "error") {
    const back = views.el("a", { href: "#/requests" }, "Back to requests");
    return views.message("This cannot be shown", result.message, screen === "request" ? back : null);
  }
  return views.message(
    "The service could not be reached",
    "Nothing was changed. Check that the service is running, then try again.",
    tryAgain(again),
  );
}

const tryAgain = (retry) => views.el("button", { type: "button", onclick: () => retry() }, "Try again");

// The shape of an answer is not checked field by field. Whatever goes wrong
// while an answer is turned into a screen ends here, not on "Loading".
const unexpected = (retry) =>
  views.message("This cannot be shown", "The service sent an unexpected answer.", tryAgain(retry));

// A message replaced the screen: keyboard focus goes to what the user can do next.
function showMessage(message) {
  content.replaceChildren(message);
  (content.querySelector("button, a") ?? content).focus({ preventScroll: true });
}

async function show({ focus } = {}) {
  if (!users) return start();
  const read = ++reads;
  const actor = user;
  const address = location.hash;
  // The user or the address can change before the event that starts the next
  // read has arrived, so the counter alone is not enough.
  const stale = () => read !== reads || actor !== user || address !== location.hash;
  const target = route();
  // A draft belongs to one request and one user.
  if (draft && (draft.requestId !== target.requestId || draft.actor !== actor)) draft = null;
  for (const link of document.querySelectorAll("[data-screen]")) {
    const here = link.dataset.screen === (target.screen === "request" ? "requests" : target.screen);
    if (here) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (!user) {
    content.replaceChildren(
      views.message("Choose who to act as", "Select a user in the top bar to see the requests."),
    );
    return;
  }

  content.replaceChildren(views.loading());
  try {
    const [results, approved] = await load(target, actor);
    if (stale()) return;
    const failed = results.find((result) => result.kind !== "ok");
    if (failed) {
      showMessage(failure(failed, target.screen));
      return;
    }
    if (target.screen === "request") {
      const [request, applications] = results.map((r) => r.data);
      shown = { request, applications, actor, blocked: null };
      if (draft && !draft.sending) {
        // The draft is kept for the user to look at again. If its action is
        // no longer possible, it has nowhere to go.
        if (views.actionFor(request, actor) === draft.kind) draft.error = null;
        else draft = null;
      }
      drawRequest();
    } else {
      const [requests, applications] = results.map((r) => r.data);
      const screen =
        target.screen === "applications" ? views.applicationsScreen : views.requestsScreen;
      const onCreate = actor.roles.includes("RELATIONSHIP_MANAGER") ? openCreate : null;
      const onRefresh = () => show({ focus: "refresh" });
      shown = null;
      content.replaceChildren(
        screen({ requests, applications, users, user: actor, approved, onRefresh, onCreate }),
      );
    }
  } catch {
    if (!stale()) showMessage(unexpected(again));
    return;
  }
  // The screen was rebuilt, so keyboard focus has to be put back.
  if (focus === "refresh") content.querySelector("[data-refresh]").focus();
  if (focus === "content") focusContent();
}

function focusContent() {
  // Without this, focusing the content scrolls the top bar out of view.
  window.scrollTo(0, 0);
  content.focus({ preventScroll: true });
}

// Revise and decide --------------------------------------------------------

const draftActions = {
  onOpen() {
    draft = actions.newDraft("revise", shown.request, shown.actor);
    drawRequest("form input");
  },
  onCancel() {
    draft = null;
    drawRequest("[data-open]");
  },
  // Every keystroke goes into the draft, so drawing the screen again keeps it.
  onInput(values) {
    draft ??= actions.newDraft("decide", shown.request, shown.actor);
    Object.assign(draft.values, values);
  },
  onSubmit: submitDraft,
  onReload: again,
};

function drawRequest(focus) {
  const { request, applications, actor } = shown;
  const onRefresh = () => show({ focus: "refresh" });
  content.replaceChildren(
    views.requestScreen({
      request,
      applications,
      users,
      user: actor,
      onRefresh,
      draft,
      blocked: shown.blocked,
      act: draftActions,
    }),
  );
  if (focus) content.querySelector(focus)?.focus();
}

async function submitDraft(outcome) {
  draft ??= actions.newDraft("decide", shown.request, shown.actor);
  const mine = draft;
  const screen = shown;
  if (!actions.canSend(mine, screen)) return;
  // The address can already name another screen while this one is still
  // drawn; an answer would then be checked against the wrong address.
  if (route().requestId !== screen.request.id) return;
  const actor = user;
  const address = location.hash;

  // While the submission runs the page takes no input: no second submission,
  // no refresh, no change of user. The back button still works.
  document.body.inert = true;
  let request;
  try {
    request = await actions.sendDraft(mine, screen, outcome, () => drawRequest());
  } finally {
    document.body.inert = false; // whatever happens, the page must open again
  }

  // The user left this request while the answer was on its way. It is not
  // shown; the next read of the request shows what happened.
  if (user !== actor || location.hash !== address) return;
  if (mine.error?.code === "UNKNOWN_USER") return forgetUser();
  // A read that started before this answer must not draw over it, and must
  // not lift a block: only a read that starts from here on counts.
  reads++;
  shown = request ? { ...screen, request } : screen;
  draft = request ? null : mine;
  drawRequest(request ? null : "[role=alert]");
  if (request) focusContent();
}

function forgetUser() {
  draft = null;
  setUser(null);
  show();
}

// Create ------------------------------------------------------------------

const createActions = {
  onInput(values) {
    Object.assign(creating.values, values);
  },
  onSubmit: submitCreate,
  onCancel: () => dialog.close(),
};

function drawCreate() {
  dialog.replaceChildren(views.createForm(creating, createActions));
  const first = "input:not([disabled]), button:not([disabled])";
  (dialog.querySelector("[role=alert]") ?? dialog.querySelector(first))?.focus();
}

function openCreate(application) {
  creating = actions.newCreate(application, user);
  drawCreate();
  dialog.showModal();
}

async function submitCreate() {
  const mine = creating;
  const request = await actions.sendCreate(mine, drawCreate);
  if (mine.error?.code === "UNKNOWN_USER") {
    dialog.close();
    return forgetUser();
  }
  if (!request) return;
  creating = null;
  dialog.close();
  location.hash = `#/requests/${request.id}`;
}

// Escape must not close the dialog while a create is unresolved.
dialog.addEventListener("cancel", (event) => {
  if (creating && actions.createIsLocked(creating)) event.preventDefault();
});

dialog.addEventListener("close", () => {
  if (!creating) return;
  // A browser may close the dialog on a second Escape although "cancel" was
  // prevented. The create is still unresolved, so the dialog opens again.
  if (actions.createIsLocked(creating)) {
    dialog.showModal();
    return;
  }
  const failed = creating.error;
  creating = null; // a draft that was not sent is discarded
  if (failed) again(); // the list behind the dialog may be out of date
});

// Start -------------------------------------------------------------------

select.addEventListener("change", () => {
  setUser(select.value);
  // The mortgage process has nothing to do on the requests screen.
  const onRequests = route().screen === "requests";
  if (user?.roles.includes("MORTGAGE_PROCESS") && onRequests) location.hash = "#/applications";
  else show();
});

window.addEventListener("hashchange", again);

// Reads the users. It can run more than once, because every screen starts it
// again until the users are known; only the latest run may change the page.
async function start() {
  const read = ++reads;
  content.replaceChildren(views.loading());
  try {
    const result = await api.getUsers();
    if (read !== reads) return;
    if (result.kind !== "ok") {
      showMessage(
        views.message(
          "The service could not be reached",
          "The list of users could not be read.",
          tryAgain(start),
        ),
      );
      return;
    }
    select.replaceChildren(
      views.el("option", { value: "" }, "Choose a user…"),
      ...result.data.map((u) => views.el("option", { value: u.id }, u.name)),
    );
    users = result.data;
  } catch {
    if (read === reads) showMessage(unexpected(start));
    return;
  }
  setUser(sessionStorage.getItem(USER_KEY));
  show();
}

start();
