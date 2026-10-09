# UI demo script

The main story in the browser, with the checks that have no automated test. It follows the example in [state-model.md](state-model.md), which [story.html](story.html) shows step by step.

The steps were run by hand in Google Chrome, against the service in Docker, on 2026-10-05, and steps 1 to 12 again on 2026-10-08; every step gave the expected result. On 2026-10-09 the amounts of the story changed, steps 4 to 6 became a revise under an open review, and the two tabs of one reviewer moved to step 13. Steps 1 to 13 as written here have not been run yet.

Start from the seed data:

```bash
docker compose up --build -d --wait
docker compose exec app python -m app.seed --reset
```

Open `http://localhost:8000/`. With `APP_PORT` set, use that port. The acting user is kept per tab, so two tabs can act as two users.

## The main story

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 1 | Alice | Applications, "New request" on APP-1001: 40 bps, a reason | The new request opens: `Pending`, revision 1, version 1 |
| 2 | Carol | Open APP-1001, comment, "Decline" | `Declined`, version 2; the comment is next to the current request |
| 3 | Alice | Open APP-1001, "Revise": 20 bps, a new reason | `Pending`, revision 2, version 3 |
| 4 | Carol in one tab, Alice in a second | Carol: open APP-1001 and leave it open at 20 bps. Alice: "Revise": 25 bps, a reason | Alice's tab: `Pending`, revision 3, version 4 |
| 5 | Carol, her tab | Type a comment, "Approve" | "This request changed while you were looking at it", the comment is still there and both buttons are closed |
| 6 | Carol, her tab | "Reload", then "Approve" | After the reload: 25 bps, revision 3, and revision 2 in the history with "No decision yet." After the approval: `Approved`, version 5 |
| 7 | Mortgage process | Applications | APP-1001: 25 bps, revision 3, approved by Carol |

## After an approval

Continue right after step 7: APP-1001 is approved at 25 bps in revision 3.

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 8 | Alice | Open APP-1001, "Revise": 35 bps, a reason | `Pending`, revision 4; below the reason, under "Approved in force": "25 bps from revision 3" |
| 9 | Alice | Requests | APP-1001: `Pending`, asked for 35 bps, approved in force 25 bps |
| 10 | Carol | Open APP-1001, comment, "Decline" | Above the buttons: "In force now: 25 bps from revision 3. Approving replaces it; declining keeps it." After the decline: `Declined`, and 25 bps from revision 3 is still in force |
| 11 | Mortgage process | Applications | APP-1001: 25 bps, revision 3, approved by Carol |
| 12 | Alice, then Dave | Alice: "Revise", 30 bps, a reason. Dave: open APP-1001, comment, "Approve" | `Approved`; in force: 30 bps from revision 5, and the history marks revision 5. As the mortgage process: 30 bps, revision 5, approved by Dave |

## Rules the UI explains

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 13 | Carol, in two tabs | Open APP-1002 in both. First tab: comment, "Approve". Second tab: comment, "Decline", then "Reload" | Second tab: "This request changed while you were looking at it"; after the reload `Approved`, and the form is gone: "Nothing to decide until Alice revises it." |
| 14 | Dave | Open APP-1005, his own request | "Another reviewer must decide on your request."; no decision form |
| 15 | Bob | Open APP-1002, Alice's request | "Only Alice can revise this request."; no "Revise" button |
| 16 | Carol | Applications | No "New request" button |

## A lost connection

Stop and start the service from a terminal: `docker compose stop app` and `docker compose start app`. This works the same in every browser; the "Offline" switch of the developer tools did not cut the calls in one run.

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 17 | Bob | Open APP-1003, "Revise", stop the service, "Submit revision" | "We couldn't confirm the result", the draft is still there, the submit button is closed |
| 18 | Bob | Start the service, "Reload" | The current request; the draft is back and can be submitted |
| 19 | Alice | Reset the seed first. "New request" on APP-1001, stop the service, "Submit request" | Only "Retry" is offered; Escape does not close the dialog |
| 20 | Alice | Start the service, "Retry" | The new request opens |

Steps 17 to 20 check the messages and the buttons. They do not prove that a create which was stored, and whose answer was lost, is replayed: the request never reaches the stopped service. The API tests and `scripts/smoke.sh` prove the replay.

## Keyboard and a narrow window

| Step | Do | Expect |
|---|---|---|
| 21 | Reset the seed, then repeat step 1 with a real keyboard only | Every control can be reached with Tab; the focus is visible. A browser draws the focus ring for the keyboard, not after a mouse click |
| 22 | Make the window narrow and open a request | One column; nothing is cut off |
