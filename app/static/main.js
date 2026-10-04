// Who the user acts as, which screen is shown, and reading its data.
// The behaviour is described in docs/ui-design.md.

import * as api from "./api.js";
import * as views from "./views.js";

const USER_KEY = "acting-user";
const content = document.getElementById("content");
const select = document.getElementById("acting-user");
const roles = document.getElementById("acting-roles");

let users = [];
let user = null;
// Increases with every change of user or screen and every refresh. A response
// is shown only if no newer read has started since.
let reads = 0;

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
    views.el("button", { type: "button", onclick: () => show() }, "Try again"),
  );
}

async function show({ focus } = {}) {
  const read = ++reads;
  const target = route();
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
  const [results, approved] = await load(target, user);
  if (read !== reads) return;

  const failed = results.find((result) => result.kind !== "ok");
  if (failed) {
    content.replaceChildren(failure(failed, target.screen));
    return;
  }
  const onRefresh = () => show({ focus: "refresh" });
  if (target.screen === "request") {
    const [request, applications] = results.map((r) => r.data);
    content.replaceChildren(views.requestScreen({ request, applications, users, user, onRefresh }));
  } else {
    const [requests, applications] = results.map((r) => r.data);
    const screen = target.screen === "applications" ? views.applicationsScreen : views.requestsScreen;
    content.replaceChildren(screen({ requests, applications, users, user, approved, onRefresh }));
  }
  // The screen was rebuilt, so keyboard focus has to be put back.
  if (focus === "refresh") content.querySelector("[data-refresh]").focus();
  if (focus === "content") {
    // Without this, focusing the content scrolls the top bar out of view.
    window.scrollTo(0, 0);
    content.focus({ preventScroll: true });
  }
}

select.addEventListener("change", () => {
  setUser(select.value);
  // The mortgage process has nothing to do on the requests screen.
  const onRequests = route().screen === "requests";
  if (user?.roles.includes("MORTGAGE_PROCESS") && onRequests) location.hash = "#/applications";
  else show();
});

window.addEventListener("hashchange", () => show({ focus: "content" }));

async function start() {
  content.replaceChildren(views.loading());
  const result = await api.getUsers();
  if (result.kind !== "ok") {
    content.replaceChildren(
      views.message(
        "The service could not be reached",
        "The list of users could not be read.",
        views.el("button", { type: "button", onclick: start }, "Try again"),
      ),
    );
    return;
  }
  users = result.data;
  select.replaceChildren(
    views.el("option", { value: "" }, "Choose a user…"),
    ...users.map((u) => views.el("option", { value: u.id }, u.name)),
  );
  setUser(sessionStorage.getItem(USER_KEY));
  show();
}

start();
