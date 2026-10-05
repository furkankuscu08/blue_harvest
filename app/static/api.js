// Calls to the public API (docs/api-contract.md). Every call ends in one of:
//   { kind: "ok", data }                               a valid success
//   { kind: "error", status, code, message, details }  an error from the contract
//   { kind: "uncertain" }                              network error, timeout, 5xx
//                                                      or a response that cannot be read
// "Uncertain" means the caller does not know what the server did.

const TIMEOUT_MS = 10000;
const UNCERTAIN = { kind: "uncertain" };

async function call(method, path, { user, body, headers = {} } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      method,
      signal: controller.signal,
      headers: {
        ...headers,
        ...(user ? { "X-User-Id": user.id } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status >= 500) return UNCERTAIN;
    const data = await response.json();
    if (response.ok) return { kind: "ok", data };
    if (typeof data.code !== "string" || typeof data.message !== "string") return UNCERTAIN;
    return {
      kind: "error",
      status: response.status,
      code: data.code,
      message: data.message,
      details: data.details ?? {},
    };
  } catch {
    return UNCERTAIN;
  } finally {
    clearTimeout(timer);
  }
}

const id = encodeURIComponent;

export const getUsers = () => call("GET", "/users");
export const getRequests = (user) => call("GET", "/requests", { user });
export const getRequest = (user, requestId) => call("GET", `/requests/${id(requestId)}`, { user });
export const getApplications = (user) => call("GET", "/applications", { user });
export const getApprovedDiscount = (user, applicationId) =>
  call("GET", `/applications/${id(applicationId)}/approved-discount`, { user });

// A successful create, revise or decide answers with the request. A success
// without one does not say what was stored, so it is not a definite answer.
const isRequest = (data) =>
  typeof data?.id === "string" &&
  Number.isInteger(data.version) &&
  Array.isArray(data.revisions) &&
  data.revisions.length > 0;

async function submit(path, options) {
  const result = await call("POST", path, options);
  return result.kind === "ok" && !isRequest(result.data) ? UNCERTAIN : result;
}

export const createRequest = (user, key, body) =>
  submit("/requests", { user, body, headers: { "Idempotency-Key": key } });
export const reviseRequest = (user, requestId, body) =>
  submit(`/requests/${id(requestId)}/revisions`, { user, body });
export const decideRequest = (user, requestId, body) =>
  submit(`/requests/${id(requestId)}/decisions`, { user, body });
