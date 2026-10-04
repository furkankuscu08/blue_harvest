// The rules for submitting: docs/ui-design.md, "Submitting". There is no DOM
// here. main.js owns the state objects and draws them; these functions change
// them and call `changed` when the page has to be drawn again.

import * as api from "./api.js";

function newKey() {
  // Not crypto.randomUUID: it only exists on https and localhost.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// Create ------------------------------------------------------------------

export const newCreate = (application, actor) => ({
  application,
  actor,
  phase: "draft", // draft, sending, uncertain or done
  values: { discount_bps: "", reason: "" },
  key: null,
  payload: null,
  error: null,
});

// Until a definite answer arrives, nothing about the submission may change.
export const createIsLocked = (creating) =>
  creating.phase === "sending" || creating.phase === "uncertain";

// One submission is one key and one payload. From a draft this makes a new
// pair; after an uncertain result it sends the pair it already has, as the
// same user. Returns the created request, or null.
export async function sendCreate(creating, changed) {
  if (creating.phase === "sending" || creating.phase === "done") return null;
  if (creating.phase === "draft") {
    creating.key = newKey();
    creating.payload = {
      application_id: creating.application.id,
      discount_bps: Number(creating.values.discount_bps),
      reason: creating.values.reason,
    };
  }
  creating.phase = "sending";
  creating.error = null;
  changed();

  const result = await api.createRequest(creating.actor, creating.key, creating.payload);
  if (result.kind === "ok") {
    creating.phase = "done";
    return result.data;
  }
  if (result.kind === "uncertain") {
    creating.phase = "uncertain";
  } else {
    // A definite error: nothing was stored, so the next submission is a new one.
    creating.phase = "draft";
    creating.error = result;
  }
  changed();
  return null;
}

// Revise and decide --------------------------------------------------------

export function newDraft(kind, request, actor) {
  const current = request.revisions.at(-1);
  return {
    kind, // revise or decide
    requestId: request.id,
    actor,
    values:
      kind === "revise"
        ? { discount_bps: String(current.discount_bps), reason: current.reason }
        : { comment: "" },
    sending: false,
    error: null,
  };
}

// `screen` is the request as the user sees it: { request, blocked }. After a
// stale version or an uncertain result the screen is blocked ("stale" or
// "uncertain"): nothing can be sent from it until the request has been read
// again. The block is on the screen, not on the draft, so that discarding the
// draft does not lift it.
export const canSend = (draft, screen) => !draft.sending && !screen.blocked;

// Sends the version on the screen; the request is not read again first.
// Returns the changed request, or null with the block or the error set.
export async function sendDraft(draft, screen, outcome, changed) {
  const version = screen.request.version;
  draft.sending = true;
  draft.error = null;
  changed();

  const { values } = draft;
  const result =
    draft.kind === "revise"
      ? await api.reviseRequest(draft.actor, draft.requestId, {
          expected_version: version,
          discount_bps: Number(values.discount_bps),
          reason: values.reason,
        })
      : await api.decideRequest(draft.actor, draft.requestId, {
          expected_version: version,
          outcome,
          comment: values.comment,
        });
  draft.sending = false;
  if (result.kind === "ok") return result.data;
  if (result.kind === "uncertain") screen.blocked = "uncertain";
  else if (result.code === "STALE_VERSION") screen.blocked = "stale";
  else draft.error = result;
  return null;
}
