#!/usr/bin/env bash
# Smoke test of the main story against the service running in Docker.
#
#     scripts/smoke.sh                 # on port 8000
#     APP_PORT=8001 scripts/smoke.sh   # if port 8000 is taken
#
# Needs Docker, curl and jq. It starts from an empty volume, so the seed data
# is fresh, and stops the service at the end. Both steps run
# `docker compose down -v`: data in the local volume is deleted.
set -uo pipefail

cd "$(dirname "$0")/.."
export APP_PORT="${APP_PORT:-8000}"
BASE="http://localhost:$APP_PORT"
WORK=$(mktemp -d)
PASS=0
FAIL=0

trap 'docker compose down -v >/dev/null 2>&1; rm -rf "$WORK"' EXIT
docker compose down -v >/dev/null 2>&1
# Our service is down now. Whatever still answers here would get the calls below
# instead of it, for example a local uvicorn bound to 127.0.0.1.
if curl -s --connect-timeout 2 --max-time 5 -o /dev/null "$BASE/health"; then
    echo "Port $APP_PORT is already in use by something else. Stop it or set APP_PORT."; exit 1
fi
echo "Building and starting the service on port $APP_PORT..."
if ! docker compose up --build -d --wait --wait-timeout 90 >"$WORK/compose" 2>&1; then
    echo "The service did not start."; tail -n 5 "$WORK/compose"; docker compose logs; exit 1
fi

CURL=(-s --connect-timeout 5 --max-time 30 -o "$WORK/body" -w '%{http_code}')

# call METHOD PATH USER [IDEMPOTENCY_KEY] [JSON] -> prints the status; body goes to $WORK/body
call() {
    local args=("${CURL[@]}" -X "$1" "$BASE$2" -H "X-User-Id: $3")
    [[ -n "${4:-}" ]] && args+=(-H "Idempotency-Key: $4")
    [[ -n "${5:-}" ]] && args+=(-H 'Content-Type: application/json' -d "$5")
    curl "${args[@]}"
}

# check DESCRIPTION EXPECTED ACTUAL
check() {
    if [[ "$2" == "$3" ]]; then
        PASS=$((PASS + 1)); printf '  ok    %-58s %s\n' "$1" "$3"
    else
        FAIL=$((FAIL + 1)); printf '  FAIL  %-58s expected %s, got %s\n' "$1" "$2" "$3"
        printf '        body: %s\n' "$(cat "$WORK/body")"
    fi
}

outcome() { echo "$1 $(jq -r '.code // .status // empty' "$WORK/body")"; }

CREATE='{"application_id": "APP-1001", "discount_bps": 20, "reason": "Competing offer."}'
APPROVE='{"expected_version": 1, "outcome": "APPROVED", "comment": "Matches the competing offer."}'

echo
echo "1. alice creates a request for APP-1001"
status=$(call POST /requests alice smoke-1 "$CREATE")
check "create" "201 PENDING" "$(outcome "$status")"
cp "$WORK/body" "$WORK/first"
REQUEST_ID=$(jq -r .id "$WORK/first")

echo "2. alice sends the same create again with the same key"
status=$(call POST /requests alice smoke-1 "$CREATE")
check "replay returns 201" "201" "$status"
check "replay body is identical to the first response" "same" \
    "$(cmp -s "$WORK/first" "$WORK/body" && echo same || echo different)"
call GET /applications alice >/dev/null
check "APP-1001 still has that one request" "$REQUEST_ID" \
    "$(jq -r '.[] | select(.id == "APP-1001") | .request_id' "$WORK/body")"

echo "3. mortgage-process reads the discount while the request is pending"
status=$(call GET /applications/APP-1001/approved-discount mortgage-process)
check "no approved discount yet" "404 NO_APPROVED_DISCOUNT" "$(outcome "$status")"

echo "4. carol approves version 1"
status=$(call POST "/requests/$REQUEST_ID/decisions" carol "" "$APPROVE")
check "approve" "201 APPROVED" "$(outcome "$status")"

echo "5. carol retries the same approval"
status=$(call POST "/requests/$REQUEST_ID/decisions" carol "" "$APPROVE")
check "retry is stale" "409 STALE_VERSION" "$(outcome "$status")"

echo "6. mortgage-process reads the discount again"
status=$(call GET /applications/APP-1001/approved-discount mortgage-process)
check "approved discount" "200 20 carol" \
    "$status $(jq -r '"\(.approved_discount_bps) \(.decided_by)"' "$WORK/body")"

echo "7. alice replays the original create after the approval"
status=$(call POST /requests alice smoke-1 "$CREATE")
check "still the original response (PENDING, version 1)" "201 PENDING 1" \
    "$status $(jq -r '"\(.status) \(.version)"' "$WORK/body")"

echo "8. dave tries to decide on his own request (APP-1005)"
call GET /applications alice >/dev/null
DAVES_ID=$(jq -r '.[] | select(.id == "APP-1005") | .request_id' "$WORK/body")
call GET "/requests/$DAVES_ID" dave >/dev/null
VERSION=$(jq -r .version "$WORK/body")
status=$(call POST "/requests/$DAVES_ID/decisions" dave "" \
    "{\"expected_version\": $VERSION, \"outcome\": \"APPROVED\", \"comment\": \"Looks fine.\"}")
check "four-eyes" "403 FOUR_EYES_VIOLATION" "$(outcome "$status")"

echo "9. reset the database to the seed data"
docker compose exec -T app python -m app.seed --reset >/dev/null 2>&1
call GET /applications alice >/dev/null
check "APP-1001 has no request again" "null" \
    "$(jq -r '.[] | select(.id == "APP-1001") | .request_id' "$WORK/body")"

echo "10. alice asks 40 bps for APP-1001"
status=$(call POST /requests alice smoke-2 \
    '{"application_id": "APP-1001", "discount_bps": 40, "reason": "Competing offer."}')
check "create" "201 PENDING" "$(outcome "$status")"
REQUEST_ID=$(jq -r .id "$WORK/body")

echo "11. dave declines version 1"
status=$(call POST "/requests/$REQUEST_ID/decisions" dave "" \
    '{"expected_version": 1, "outcome": "DECLINED", "comment": "Above what the offer justifies."}')
check "decline" "201 DECLINED" "$(outcome "$status")"
status=$(call GET /applications/APP-1001/approved-discount mortgage-process)
check "no approved discount after the decline" "404 NO_APPROVED_DISCOUNT" "$(outcome "$status")"

REVISE='{"expected_version": 2, "discount_bps": 20, "reason": "Matches the competing offer."}'
echo "12. alice revises version 2 to 20 bps"
status=$(call POST "/requests/$REQUEST_ID/revisions" alice "" "$REVISE")
check "revise" "201 PENDING 3" "$status $(jq -r '"\(.status) \(.version)"' "$WORK/body")"

echo "13. alice retries the same revision"
status=$(call POST "/requests/$REQUEST_ID/revisions" alice "" "$REVISE")
check "retry is stale" "409 STALE_VERSION" "$(outcome "$status")"

echo "14. bob tries to revise alice's request"
status=$(call POST "/requests/$REQUEST_ID/revisions" bob "" \
    '{"expected_version": 3, "discount_bps": 10, "reason": "Lower."}')
check "only the creator revises" "403 NOT_REQUEST_OWNER" "$(outcome "$status")"

echo "15. alice revises version 3 to 25 bps before anyone decided"
status=$(call POST "/requests/$REQUEST_ID/revisions" alice "" \
    '{"expected_version": 3, "discount_bps": 25, "reason": "The customer asks for more."}')
check "revise while pending" "201 PENDING 4" "$status $(jq -r '"\(.status) \(.version)"' "$WORK/body")"

echo "16. carol approves version 4"
status=$(call POST "/requests/$REQUEST_ID/decisions" carol "" \
    '{"expected_version": 4, "outcome": "APPROVED", "comment": "Matches a documented offer."}')
check "approve" "201 APPROVED" "$(outcome "$status")"

echo "17. mortgage-process reads the approved discount"
status=$(call GET /applications/APP-1001/approved-discount mortgage-process)
check "revision 3, 25 bps, approved by carol" "200 3 25 carol" \
    "$status $(jq -r '"\(.revision_number) \(.approved_discount_bps) \(.decided_by)"' "$WORK/body")"

echo "18. the history keeps every revision; revision 2 has no decision"
call GET "/requests/$REQUEST_ID" alice >/dev/null
check "history" "1:40:DECLINED:dave 2:20:null:null 3:25:APPROVED:carol" \
    "$(jq -r '[.revisions[] | "\(.number):\(.discount_bps):\(.decision.outcome):\(.decision.decided_by)"] | join(" ")' "$WORK/body")"

echo "19. the list of requests shows the approved request first"
status=$(call GET /requests carol)
check "latest change first" "200 APP-1001 APPROVED 5 25" \
    "$status $(jq -r '.[0] | "\(.application_id) \(.status) \(.version) \(.current_discount_bps)"' "$WORK/body")"
status=$(curl "${CURL[@]}" "$BASE/requests")
check "the list needs a known user" "401 UNKNOWN_USER" "$(outcome "$status")"

echo "20. the list of users needs no identity"
status=$(curl "${CURL[@]}" "$BASE/users")
check "five seed users" "200 alice bob carol dave mortgage-process" \
    "$status $(jq -r '[.[].id] | join(" ")' "$WORK/body")"

echo
echo "$PASS passed, $FAIL failed. Stopping the service."
[[ $FAIL -eq 0 ]]
