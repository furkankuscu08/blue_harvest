# API contract

The HTTP interface of the pricing exception service. It follows the rules in [state-model.md](state-model.md) and the assumptions in [assumptions-and-scope.md](assumptions-and-scope.md).

This is the design record. Once the service exists, the OpenAPI schema that FastAPI generates at `/docs` is the source of truth for field-level detail.

## Conventions

- Requests and responses are JSON.
- Timestamps are UTC in ISO 8601, set by the server.
- The caller is identified by the `X-User-Id` header. It is required on every endpoint except `GET /users` and `GET /health`. This is not authentication; see assumption A7.
- A user has one or more roles: `RELATIONSHIP_MANAGER`, `REVIEWER`, `MORTGAGE_PROCESS`.
- Discounts are whole basis points: `20` means 0.20 percentage points.

### Input rules

These apply to every request body.

- Whole-number fields accept JSON integers only. Strings, booleans and decimals are rejected, not converted.
- Unknown fields are rejected. A client that sends `decided_by`, for example, gets an error and is not silently ignored.
- Text fields are trimmed of leading and trailing whitespace before any other rule is applied. The trimmed value is what is stored and what idempotency compares.

### Errors

Every error defined in this contract has the same body. Requests to an unknown route or with an unsupported method get the framework's standard `404` or `405` response instead. The HTTP status gives the category and `code` names the exact case; clients branch on `code`. `details` is optional and carries data a client may need, so that nobody has to parse `message`.

```json
{
  "code": "REQUEST_ALREADY_EXISTS",
  "message": "An exception request already exists for this application.",
  "details": { "request_id": "0b6f3c1e-8f0a-4c57-9d0e-2f6a4c1d9a11" }
}
```

## Endpoints

| Method and path | Purpose | Allowed caller |
|---|---|---|
| `POST /requests` | Create a request | `RELATIONSHIP_MANAGER` |
| `GET /requests` | List requests | Any known user |
| `GET /requests/{id}` | Request detail with full history | Any known user |
| `POST /requests/{id}/revisions` | Revise a request | The `RELATIONSHIP_MANAGER` who created it |
| `POST /requests/{id}/decisions` | Approve or decline | A `REVIEWER` who did not create it |
| `GET /applications/{id}/approved-discount` | Approved discount for the mortgage process | `MORTGAGE_PROCESS` |
| `GET /applications` | Seed mortgage applications | Any known user |
| `GET /users` | Seed users, for choosing who to act as | No identity needed |
| `GET /health` | Health check | No identity needed |

## Order of checks

Two kinds of check, with different guarantees.

**Request-level checks** look only at the caller and the shape of the request. For a request that can be parsed, an unknown caller is rejected first. A body that is not valid JSON may be answered with `422 VALIDATION_ERROR` before the caller is checked. The remaining request-level checks (role, idempotency key, body) all run before any business rule, but their order among themselves is not guaranteed.

A request id in the path that is not a valid UUID is a `422 VALIDATION_ERROR`. A valid UUID that matches no request is a `404 REQUEST_NOT_FOUND`.

| Check | Error |
|---|---|
| Caller is known | `401 UNKNOWN_USER` |
| Caller has a role that allows the action | `403 ROLE_NOT_ALLOWED` |
| Idempotency key is valid (create only) | `400 INVALID_IDEMPOTENCY_KEY` |
| Body is well-formed and follows the input rules | `422 VALIDATION_ERROR` |

**Business checks** look at stored data. Their order is guaranteed and is listed under each endpoint.

## Request detail

Returned by `GET /requests/{id}` and by every successful create, revise and decide.

```json
{
  "id": "0b6f3c1e-8f0a-4c57-9d0e-2f6a4c1d9a11",
  "application_id": "APP-1004",
  "status": "APPROVED",
  "version": 4,
  "created_by": "alice",
  "created_at": "2026-10-05T09:00:00Z",
  "updated_at": "2026-10-05T11:30:00Z",
  "revisions": [
    {
      "number": 1,
      "discount_bps": 35,
      "reason": "Competing offer from another lender.",
      "created_at": "2026-10-05T09:00:00Z",
      "decision": {
        "outcome": "DECLINED",
        "decided_by": "carol",
        "decided_at": "2026-10-05T10:00:00Z",
        "comment": "Above what the competing offer justifies."
      }
    },
    {
      "number": 2,
      "discount_bps": 20,
      "reason": "Matches the competing offer.",
      "created_at": "2026-10-05T11:00:00Z",
      "decision": {
        "outcome": "APPROVED",
        "decided_by": "carol",
        "decided_at": "2026-10-05T11:30:00Z",
        "comment": null
      }
    }
  ]
}
```

History is part of the detail, not a separate endpoint. Each decision sits inside the revision it applies to; `decision` is `null` for a revision that has not been decided. The last entry in `revisions` is the current one.

Consistency guarantees:

- A detail response is produced from a single database snapshot, so status, version and history always belong together.
- The response to a successful create, revise or decide shows the state that this operation produced. It is built inside the operation's transaction, not from a later read that could already include someone else's change.

## Create a request

`POST /requests`

| Input | Rule |
|---|---|
| `Idempotency-Key` header | Required. 1 to 255 characters. Scoped to the caller. |
| `application_id` | Required. |
| `discount_bps` | Required. Whole number from 1 to the configured limit. The limit defaults to 200. |
| `reason` | Required. Not blank, at most 1000 characters. |

Returns `201` with the request detail: status `PENDING`, one revision, version 1.

Business checks, in order:

1. The key was used before by this caller:
   - with the same validated fields: return the stored original response, status and body, and stop;
   - with different fields: `422 IDEMPOTENCY_KEY_REUSED`.
2. Application exists: `404 APPLICATION_NOT_FOUND`.
3. Application has no request: `409 REQUEST_ALREADY_EXISTS`, with the existing request's id in `details.request_id`.

The idempotency lookup, the application and request checks, the creation of the request and its first revision, and the storage of the successful response all happen in one write transaction. Success is returned only after commit. A request can never be stored without its idempotency record.

Because check 1 comes before check 3, a retry of a successful create is never answered with `REQUEST_ALREADY_EXISTS`. The stored response is replayed as it was first sent, even if the request has changed since. Failed calls are not stored; a retry of a failed call is evaluated again.

## List requests

`GET /requests`

Returns `200` with an array ordered by `updated_at` descending, then `id` ascending, so the order is the same on every call. No filtering or pagination.

```json
[
  {
    "id": "0b6f3c1e-8f0a-4c57-9d0e-2f6a4c1d9a11",
    "application_id": "APP-1004",
    "status": "APPROVED",
    "version": 4,
    "created_by": "alice",
    "current_discount_bps": 20,
    "updated_at": "2026-10-05T11:30:00Z"
  }
]
```

## Get a request

`GET /requests/{id}`

Returns `200` with the request detail, or `404 REQUEST_NOT_FOUND`.

## Revise a request

`POST /requests/{id}/revisions`

| Input | Rule |
|---|---|
| `expected_version` | Required. Positive whole number: the version the caller saw. |
| `discount_bps` | Required. Whole number from 1 to the configured limit. |
| `reason` | Required. Not blank, at most 1000 characters. |

Returns `201` with the request detail: a new revision, status `PENDING`, version increased by one.

## Decide on a request

`POST /requests/{id}/decisions`

| Input | Rule |
|---|---|
| `expected_version` | Required. Positive whole number: the version the caller saw. |
| `outcome` | Required. `APPROVED` or `DECLINED`. |
| `comment` | Required and not blank for `DECLINED`; optional for `APPROVED`. At most 1000 characters. |

Returns `201` with the request detail: a decision on the latest revision, status `APPROVED` or `DECLINED`, version increased by one.

`outcome` uses the same two values in the request and in the stored decision. `PENDING` is a request status only, never an outcome.

A decline needs a comment so that the relationship manager knows what to change before resubmitting. This is our assumption A9.

## Business checks for revise and decide

In order, all inside one write transaction together with the change itself:

1. Request exists: `404 REQUEST_NOT_FOUND`.
2. Caller's relation to the request:
   - revise: caller created it, otherwise `403 NOT_REQUEST_OWNER`;
   - decide: caller did not create it, otherwise `403 FOUR_EYES_VIOLATION`.
3. `expected_version` is the current version: `409 STALE_VERSION`.
4. The current status allows the action: `409 INVALID_STATE`.

For a client this means: `STALE_VERSION` says "reload, you were looking at an old state"; `INVALID_STATE` says "you saw the current state and this action is not possible in it". A stale version is always reported as `STALE_VERSION`, even when the current status would also forbid the action.

## Approved discount

`GET /applications/{id}/approved-discount`

Only callers with the `MORTGAGE_PROCESS` role can use this endpoint. Internal users see the same information in the request detail.

Returns `200` when the application's request is `APPROVED`:

```json
{
  "application_id": "APP-1004",
  "request_id": "0b6f3c1e-8f0a-4c57-9d0e-2f6a4c1d9a11",
  "revision_number": 2,
  "approved_discount_bps": 20,
  "decided_by": "carol",
  "decided_at": "2026-10-05T11:30:00Z"
}
```

The values come from the approved revision and its decision.

| Case | Response |
|---|---|
| Application does not exist | `404 APPLICATION_NOT_FOUND` |
| No request, or request is `PENDING` or `DECLINED` | `404 NO_APPROVED_DISCOUNT` |

## Applications and users

`GET /applications` returns the seed applications. `request_id` is `null` when the application has no request yet.

```json
[ { "id": "APP-1001", "customer_name": "J. de Vries", "request_id": null } ]
```

`GET /users` returns the seed users.

```json
[ { "id": "dave", "name": "Dave", "roles": ["RELATIONSHIP_MANAGER", "REVIEWER"] } ]
```

Both are plain lists with no filtering or pagination. They exist so that the UI and a reviewer of this exercise read seed data from one place.

## Health

`GET /health` runs a trivial database query.

| Case | Response |
|---|---|
| Service and database are usable | `200` with `{"status": "ok"}` |
| Database cannot be reached | `503 DATABASE_UNAVAILABLE` |

## Error catalogue

| Status | Code | Meaning |
|---|---|---|
| `400` | `INVALID_IDEMPOTENCY_KEY` | The key header is missing, empty or longer than 255 characters. |
| `401` | `UNKNOWN_USER` | `X-User-Id` is missing or is not a seed user. |
| `403` | `ROLE_NOT_ALLOWED` | The caller's roles do not allow this action. |
| `403` | `NOT_REQUEST_OWNER` | Only the creator can revise a request. |
| `403` | `FOUR_EYES_VIOLATION` | The creator cannot decide on their own request. |
| `404` | `REQUEST_NOT_FOUND` | No request with this id. |
| `404` | `APPLICATION_NOT_FOUND` | No application with this id. |
| `404` | `NO_APPROVED_DISCOUNT` | The application has no approved request. |
| `409` | `REQUEST_ALREADY_EXISTS` | The application already has a request. `details.request_id` identifies it. |
| `409` | `STALE_VERSION` | The request changed since the caller loaded it. |
| `409` | `INVALID_STATE` | The current status does not allow this action. |
| `422` | `VALIDATION_ERROR` | The body is malformed, a field is missing or of the wrong type, an unknown field was sent, or a rule is broken. |
| `422` | `IDEMPOTENCY_KEY_REUSED` | The key was already used with different fields. |
| `503` | `DATABASE_UNAVAILABLE` | The health check could not reach the database. |

## Retry behaviour

**Create** is protected by the idempotency key, as described above. One logical submission is one key and one fixed payload; a retry sends exactly that pair again.

**Revise and decide** have no idempotency key. The version check gives the protection needed:

- If the first call was committed, a retry with the same `expected_version` changes nothing and returns `409 STALE_VERSION`.
- If the first call was not committed, the retry succeeds only if `expected_version` is still current and the status still allows the action.
- A conflict does not prove that the caller's earlier call succeeded; another user may have changed the request. After a timeout, the client reads the request and its history to find out what happened.
- A client must not fetch the new version and resend the same action automatically. The user has to see the current state first.

## Seed data

Users:

| Id | Roles | Purpose |
|---|---|---|
| `alice` | `RELATIONSHIP_MANAGER` | Creates and revises requests. |
| `bob` | `RELATIONSHIP_MANAGER` | A second manager, to show that only the creator can revise. |
| `carol` | `REVIEWER` | Decides on requests. |
| `dave` | `RELATIONSHIP_MANAGER`, `REVIEWER` | Holds both roles, so the four-eyes rule can be exercised. |
| `mortgage-process` | `MORTGAGE_PROCESS` | The downstream system that reads approved discounts. |

Applications:

| Id | Starting point |
|---|---|
| `APP-1001` | No request. |
| `APP-1002` | `PENDING` request created by `alice`. |
| `APP-1003` | `DECLINED` request created by `bob`. |
| `APP-1004` | `APPROVED` request created by `alice`: declined once, revised, then approved. |
| `APP-1005` | `PENDING` request created by `dave`. |

Seeding goes through the same create, revise and decide logic as the API (not over HTTP), so seed data cannot break a domain rule and every seeded history is a state that real operations can reach.

Seeding runs only when the database is empty. A documented reset command empties the database and seeds it again, in one transaction, so it can run while the service is up.

A seed test checks two things: each application ends in the expected status, revision and version; and running the seed a second time adds no rows.
