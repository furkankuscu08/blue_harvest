# Assumptions and scope

What the assignment asks for, what we decided ourselves, and what we left out on purpose.

## A. Stated requirements

Taken from the assignment. The identifiers are used in the traceability table.

| Id | Requirement |
|---|---|
| R1 | A relationship manager can create a request for an existing mortgage application: application identifier, requested discount in basis points, reason. |
| R2 | A reviewer can approve or decline a request. The outcome identifies who decided and when. |
| R3 | An approved request is available to the mortgage application process, which needs the approved discount. |
| R4 | Internal users can see the history of a request, including its current status and previous decisions. |
| R5 | A retried call from an upstream system after a timeout does not create a duplicate request. |
| R6 | The service is straightforward to run locally. |

## B. Stakeholder decision

One stakeholder wants the relationship manager to be able to change the requested discount after submitting. Another wants an approval to always apply to the exact request that was reviewed.

**Decision:** a request is changed only by adding a new revision, and every decision is bound to the revision that was reviewed. An approved request can be revised too: its approval stays in force until a later revision is approved.

Both needs are met. Revisions are immutable, so the content a reviewer saw can never change underneath a decision. A reviewer acting on an outdated view is rejected and has to look at the current revision first. The relationship manager can keep negotiating after an approval, and the mortgage process never reads a discount that no reviewer approved.

Details are in `state-model.md`.

## C. Our assumptions

None of these is stated in the assignment. Each is a choice we made and would confirm with the client.

| # | Assumption | Why | If it is wrong |
|---|---|---|---|
| A1 | An application has at most one pricing exception request. | The mortgage process gets one unambiguous answer per application. | Allow several requests and define which approval is in force. |
| A2 | Four-eyes: the person who created a request cannot decide on it. | Standard separation of duties in financial services. | Revise the separation-of-duties policy and its tests. |
| A3 | Only the manager who created a request can revise it. | Keeps A2 meaningful: nobody can change a request and then approve their own change. | Track who authored each revision and apply four-eyes per revision. |
| A4 | A declined request can be revised and resubmitted. An approved request can be revised too; the new revision needs its own approval. | Explains "previous decisions" in R4, gives a declined request a way forward under A1, and lets a negotiation continue after an approval. | Make an approval final, or make decline final and allow a new request instead. The second also means changing A1. |
| A5 | The discount is a positive whole number of basis points, at most 200 (2.00 percentage points). The limit is one constant in the code. | Rejects obviously wrong input. The number itself is a placeholder. | A different limit is a one-line change. Fractional basis points or a zero discount would change validation and the data model. |
| A6 | Mortgage applications and users are seed data. This service reads them and does not manage them. | The assignment lets us represent them as we find useful. | Integrate with the systems that own them. |
| A7 | The caller is identified by an `X-User-Id` header. This is not authentication. | Lets reviewers exercise roles locally without an identity provider. | See section D. |
| A8 | Who decided and when are set by the server, in UTC. They are never taken from the request body. | An audit record must not be writable by the caller. | No alternative considered. |
| A9 | Every decision carries a comment. | A decline tells the relationship manager what to change before resubmitting (A4); an approval records why the exception is justified. | Make the comment optional on approval. |
| A10 | A new revision does not withdraw the approval in force. While the new revision is pending, or after it was declined, the last approval stays in force. When a later revision is approved, that approval replaces it. | Asking for more must not cost the customer the discount the bank already granted. A reviewer who declines a new proposal says no to that proposal only. | Withdraw the approval as soon as a new revision is submitted, or let a reviewer cancel it; see "Cancelling an approved discount" in section D. |

## D. Deliberately out of scope

### Lighter trade-offs to change before production

These are places where the exercise is deliberately lighter than a production service.

| In this exercise | Before production |
|---|---|
| Seeded identities selected by a header. Role, ownership and four-eyes checks are enforced server-side, but the identity itself is not verified. | Authentication through the client's identity provider and trusted role assignment. The existing checks stay. |
| SQLite in a local file, single writer. | PostgreSQL with managed migrations, and the concurrency tests validated again on it. |
| The UI is checked with a written manual script. | Automated browser tests for the main flows. |

### Features not built

Each would need to be confirmed as a requirement first. None is assumed to be necessary.

| Feature | If the client needs it |
|---|---|
| Cancelling an approved discount (revoke) | A separate, audited action. Declining a new revision does not cancel the approval in force (A10). |
| Changing a discount the mortgage process has already used | The approved-discount endpoint gives the discount that can be used at the moment it is read. What happens to an offer that was already made belongs to the mortgage process. |
| Withdrawing a request | A `WITHDRAWN` status available to the creator. |
| Reviewer authority limits | Tiered approval based on the size of the discount. |
| Notifying the mortgage process | An event on approval using an outbox. Not needed while querying the endpoint is enough. |
| Expiry of an approval | A validity period, checked when the approved discount is read. |
| Pagination, filtering, search | Useful once there are more requests than fit on a page. |
