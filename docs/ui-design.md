# UI design

How the browser UI behaves and why. The UI is a client of the public API in [api-contract.md](api-contract.md); it has no access of its own. The API enforces every rule. The UI only guides the user, so a check in the UI is never the only defence.

## Technology

| Area | Choice | Why |
|---|---|---|
| Language | HTML, CSS and plain JavaScript (ES modules) | Fits the existing JSON API directly. No build step, no new dependency. |
| Screens | One HTML file with hash routes: `#/requests`, `#/requests/{id}`, `#/applications` | Every screen has an address, so the back button and a second tab work. |
| Style | One hand-written stylesheet | No framework and no external source; the UI works offline. |
| Forms | The browser's own form checks and the `<dialog>` element | Required fields, ranges, lengths and modal behaviour come for free. |
| Serving | `GET /` returns the page; its files are under `/static/` | One address for the README. Unknown routes keep the framework's answer. |
| Acting user | Kept per tab in `sessionStorage` | Two tabs can act as two different users. |

Not chosen: server-rendered pages with HTMX (a new dependency and a second path next to the JSON API) and a framework with a build step (too much for three screens).

## Screens

**Top bar**, on every screen: the two screens and the "Acting as" selection with the user's roles. Until a user is selected, the UI calls nothing but `GET /users`.

**Requests**, the home screen: one table in the order the API returns, latest change first. No filters. The "Next step" column tells the acting user what a request needs from them:

| Label | When |
|---|---|
| Awaiting your review | `PENDING`, created by someone else, and the user is a reviewer |
| Needs your revision | `DECLINED` and created by the user |
| Awaiting review | `PENDING` and created by the user |

**Request detail**: the current discount and reason and the action panel are at the top, so a reviewer decides with the reason in view. The history follows: every revision with its decision directly below it.

**Applications**: every application with its request, or "New request" for a relationship manager when there is none. For the mortgage process each row shows the approved discount, read from the approved-discount endpoint and not derived from the list. Only `NO_APPROVED_DISCOUNT` is shown as "No approved discount"; any other failure is shown as "Could not be read".

A discount is shown in basis points, for example `25 bps`.

## Actions

An action that does not belong to the user's roles is hidden. An action that belongs to their role but is not possible now is replaced by a visible sentence that says why.

| Action | Shown to | Possible when | Otherwise |
|---|---|---|---|
| New request | Relationship manager | The application has no request | A link to the request |
| Revise | Relationship manager | The user created the request and it is `PENDING` or `DECLINED` | "Only Alice can revise this request." |
| Approve, decline | Reviewer | The user did not create the request and it is `PENDING` | "Another reviewer must decide on your request." or "Waiting for a revision." |

On an `APPROVED` request the panel shows "Approved requests cannot be changed."

## Reading

A read remembers the acting user and the address it started with, and its number from a counter that increases with every read. Its response is shown only if no newer read has started and the user and the address are still the same. This drops a late response for an earlier user, an earlier screen or an earlier refresh. The counter alone is not enough: after a change of user or address, the event that starts the next read can arrive later than an old response. The read of the users at the start takes its number from the same counter. This rule is for reads. What happens to the answer of a submission is described below.

The UI does not check the shape of every answer field by field; the API's schemas define it. An answer that cannot be turned into a screen, at any step between the response and the page, is shown as "This cannot be shown" with "Try again", never as an endless "Loading". Until the list of users has been read, every screen offers to read it again.

## Submitting

A response is **definite** when it is a valid success or an error from the contract. A success is valid only if it contains the request. It is **uncertain** after a network error, a timeout, a `5xx` or a response that cannot be read. While a revise or decide is running, the whole page takes no input: no second submission, no refresh, no change of user. A create runs in a modal dialog, which has the same effect. The browser's back button cannot be locked, so the rules below do not depend on it.

**Revise and decide** send the version the user sees and do not read the request again first.

- `STALE_VERSION` and an uncertain result are handled the same way: a message, the draft kept, and a "Reload" button. Nothing is read or resubmitted automatically.
- Until the current request has been loaded, every action on it stays closed. This block belongs to the request on screen, not to the draft: discarding the draft does not lift it. If the reload fails, the draft and the block stay.
- Only a read that starts after the answer lifts the block. When the answer of a submission is shown, every read that started earlier is dropped, so an earlier read can neither draw over a success nor open a blocked screen.
- After a reload the draft is kept but not merged with the current values. The user compares it with the current request above and submits it themselves.
- If the action is no longer possible after the reload, for example because the request was approved meanwhile, the draft is discarded: there is nothing left to submit it to.
- The answer is shown only if the acting user and the address are the same as when it was sent. Nothing is sent from a screen that the address no longer names. If they left before it arrived, it is not shown; the next read of the request shows what happened, which is what the contract asks a client to do after a timeout.

**Create** follows the contract's retry rule: one submission is one idempotency key and one payload.

- The key is made when the form is first submitted. The caller, key, payload and result are kept apart from the screen, so the back button cannot discard them.
- Until a definite response arrives, the form, the user selection and closing the dialog are locked.
- After an uncertain result only "Retry" is offered, and it sends the same caller, key and payload.
- After a definite error the form opens again; a corrected submission gets a new key.
- A draft that was never sent is discarded when the dialog closes. The dialog is modal, so the acting user cannot change while it is open.
- The key lives in the page only. After a page reload a new submission gets `REQUEST_ALREADY_EXISTS` if the earlier create was stored, and the UI links to the existing request.

## Errors

By default the UI shows the API's `message` next to the action and keeps what the user typed. Five cases get their own handling:

| Case | Handling |
|---|---|
| `VALIDATION_ERROR` | The fields and messages in `details.errors` are listed |
| `STALE_VERSION` | "Reload", as described above |
| `REQUEST_ALREADY_EXISTS` | A link to the request in `details.request_id` |
| `UNKNOWN_USER` | The selection is cleared and the user chooses again |
| Uncertain result | For a read: "try again". For a submission: as described above |

Text from the API is written to the page as text, never as HTML: reasons and comments are user input.

When a message replaces a screen, keyboard focus moves to its button or link. A message next to a form is marked as an alert, so a screen reader announces it.

## Out of scope

Filters, search and pagination, automatic refresh, a dark theme, translations, automated browser tests, a seed reset from the UI, and keeping the idempotency key across a page reload.
