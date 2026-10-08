# UI demo script

The main story in the browser, with the checks that have no automated test. The steps were run by hand on 2026-10-05 in Google Chrome, against the service in Docker, and every step gave the expected result. After an approved request could be revised, steps 1 to 12 were run again in the same way on 2026-10-08, with the Requests list also checked in a narrow window, and every step gave the expected result. Steps 13 to 21 were not run again.

Start from the seed data:

```bash
docker compose up --build -d --wait
docker compose exec app python -m app.seed --reset
```

Open `http://localhost:8000/`. With `APP_PORT` set, use that port.

## The main story

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 1 | Alice | Applications, "New request" on APP-1001: 35 bps, a reason | The new request opens: `Pending`, revision 1, version 1 |
| 2 | Carol | Open APP-1001, comment, "Decline" | `Declined`, version 2; the comment is next to the current request |
| 3 | Alice | Open APP-1001, "Revise": 20 bps, a new reason | `Pending`, revision 2, version 3 |
| 4 | Carol, in two tabs | Open APP-1001 in both. In the first tab: comment, "Approve" | First tab: `Approved`, version 4 |
| 5 | Carol, second tab | Type a comment, "Decline" | "This request changed while you were looking at it", the comment is still there and both buttons are closed |
| 6 | Carol, second tab | "Reload" | `Approved`; the form is gone: "Nothing to decide until Alice revises it." |
| 7 | Mortgage process | Applications | APP-1001: 20 bps, revision 2, approved by Carol |

## After an approval

Continue right after step 7: APP-1001 is approved at 20 bps in revision 2.

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 8 | Alice | Open APP-1001, "Revise": 30 bps, a reason | `Pending`, revision 3; below the reason, under "Approved in force": "20 bps from revision 2" |
| 9 | Alice | Requests | APP-1001: `Pending`, asked for 30 bps, approved in force 20 bps |
| 10 | Carol | Open APP-1001, comment, "Decline" | Above the buttons: "In force now: 20 bps from revision 2. Approving replaces it; declining keeps it." After the decline: `Declined`, and 20 bps from revision 2 is still in force |
| 11 | Mortgage process | Applications | APP-1001: 20 bps, revision 2, approved by Carol |
| 12 | Alice, then Dave | Alice: "Revise", 25 bps, a reason. Dave: open APP-1001, comment, "Approve" | `Approved`; in force: 25 bps from revision 4, and the history marks revision 4. As the mortgage process: 25 bps, revision 4, approved by Dave |

## Rules the UI explains

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 13 | Dave | Open APP-1005, his own request | "Another reviewer must decide on your request."; no decision form |
| 14 | Bob | Open APP-1002, Alice's request | "Only Alice can revise this request."; no "Revise" button |
| 15 | Carol | Applications | No "New request" button |

## A lost connection

Stop and start the service from a terminal: `docker compose stop app` and `docker compose start app`. This works the same in every browser; the "Offline" switch of the developer tools did not cut the calls in one run.

| Step | Acting as | Do | Expect |
|---|---|---|---|
| 16 | Bob | Open APP-1003, "Revise", stop the service, "Submit revision" | "We couldn't confirm the result", the draft is still there, the submit button is closed |
| 17 | Bob | Start the service, "Reload" | The current request; the draft is back and can be submitted |
| 18 | Alice | Reset the seed first. "New request" on APP-1001, stop the service, "Submit request" | Only "Retry" is offered; Escape does not close the dialog |
| 19 | Alice | Start the service, "Retry" | The new request opens |

Steps 16 to 19 check the messages and the buttons. They do not prove that a create which was stored, and whose answer was lost, is replayed: the request never reaches the stopped service. The API tests and `scripts/smoke.sh` prove the replay.

## Keyboard and a narrow window

| Step | Do | Expect |
|---|---|---|
| 20 | Reset the seed, then repeat step 1 with a real keyboard only | Every control can be reached with Tab; the focus is visible. A browser draws the focus ring for the keyboard, not after a mouse click |
| 21 | Make the window narrow and open a request | One column; nothing is cut off |
