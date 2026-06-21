#!/usr/bin/env bash

: "${RESOLVE_OPT:=}"
set -euo pipefail


ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DOMAIN="${DOMAIN:-https://profiledna.dnaagencia.com}"
RESOLVE_OPT="${RESOLVE_OPT:-$RESOLVE_OPT}"
EMAIL="e2e_full_$(date +%s)@example.com"


wait_health() {
  local name="$1"
  local url="$2"
  local max="${3:-60}"
  echo "== wait_health ${name} (${max}s) =="
  for i in $(seq 1 "$max"); do
    if curl -fsS -m 2 "$url" >/dev/null 2>&1; then
      echo "OK: ${name}"
      return 0
    fi
    echo "try=${i} ${name}=not_ready"
    sleep 1
  done
  echo "ERRO: ${name} não ficou pronto em ${max}s: ${url}"
  return 1
}

echo "== [0] HEAD sanity =="
git --no-pager log -1 --oneline

echo
echo "== [1] Health (interno + nginx SNI local) =="
wait_health "upstream" "http://127.0.0.1:18081/health" 60
wait_health "nginx" "https://profiledna.dnaagencia.com/health" 60
curl -fsS http://127.0.0.1:18081/health && echo
curl -fsS $RESOLVE_OPT "$DOMAIN/health" && echo

echo
echo "== [2] Start -> token =="
LOC="$(
  curl -sS -D- -o /dev/null -X POST "$DOMAIN/start" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data "nome=E2E&sobrenome=Full&email=${EMAIL//+/%2B}&tipo_aplicacao=pessoal" \
  | awk -F': ' 'tolower($1)=="location"{gsub("\r","",$2); print $2}'
)"
TOKEN="$(echo "$LOC" | sed -n 's|^/p/\([^/]*\)/q/1$|\1|p')"
echo "EMAIL=$EMAIL"
echo "LOCATION=$LOC"
echo "TOKEN=$TOKEN"
test -n "$TOKEN"

echo
echo "== [3] Autosave 100 (A/B alternado) =="
for i in $(seq 1 100); do
  c="A"; [ $((i%2)) -eq 0 ] && c="B"
  curl -fsS -o /dev/null -X POST "$DOMAIN/p/$TOKEN/autosave" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data "question_number=$i&choice=$c"
done
echo "OK: autosave 100"

echo
echo "== [4] Review + Confirm (GET) =="
curl -fsS -o /dev/null "$DOMAIN/p/$TOKEN/review" && echo "OK: review 200"
curl -fsS -o /dev/null "$DOMAIN/p/$TOKEN/confirm" && echo "OK: confirm 200"

echo
echo "== [5] Submit (303 esperado) =="
SUBH="$(curl -sS -D- -o /dev/null -X POST "$DOMAIN/p/$TOKEN/submit")"
echo "$SUBH" | sed -n '1,15p'
echo "$SUBH" | grep -q "303" && echo "OK: submit 303" || { echo "ERRO: submit não retornou 303"; exit 1; }

echo
echo "== [6] Report HTML (sem legado + PT-BR band) =="
HTML="$(curl -sS "$DOMAIN/p/$TOKEN/report")"
echo "$HTML" | grep -q "interpretations_per_score" && { echo "ERRO: HTML contém legado"; exit 1; } || true
echo "$HTML" | grep -Eiq "(Baixo|Médio|Alto)" || { echo "ERRO: não encontrei faixa PT-BR no HTML"; exit 1; }
echo "OK: report HTML OK (no-legacy + PT-BR)"

echo
echo "== [7] Aliases SSOT (/t/*) =="
H1="$(curl -sS -D- -o /dev/null -L "$DOMAIN/t/$TOKEN/resultado" | tr -d '\r' | sed -n '1,15p')"
echo "$H1"
echo "$H1" | grep -q "307" && echo "OK: /t/.../resultado -> 307" || { echo "ERRO: alias /resultado"; exit 1; }

H2="$(curl -sS -D- -o /dev/null -L "$DOMAIN/t/$TOKEN/resultado/pdf" | tr -d '\r' | sed -n '1,15p')"
echo "$H2"
echo "$H2" | grep -q "307" && echo "OK: /t/.../resultado/pdf -> 307" || { echo "ERRO: alias /resultado/pdf"; exit 1; }

echo
echo "== [8] PDF: HEAD + GET + estabilidade (ETag/len) =="
PH="$(curl -sSIL "$DOMAIN/p/$TOKEN/report/pdf" | tr -d '\r')"
echo "$PH" | sed -n '1,20p'
echo "$PH" | grep -q "200" || { echo "ERRO: HEAD pdf não deu 200"; exit 1; }
echo "$PH" | awk -F': ' 'tolower($1)=="content-type"{print $2}' | grep -q "application/pdf" || { echo "ERRO: HEAD content-type != pdf"; exit 1; }

ET1="$(echo "$PH" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tail -n 1)"
LEN_H1="$(echo "$PH" | awk -F': ' 'tolower($1)=="content-length"{print $2}' | tail -n 1)"
echo "ETAG1=\"$ET1\""
echo "LEN_H1=$LEN_H1"

GET1="$(curl -sS -D- -o /dev/null "$DOMAIN/p/$TOKEN/report/pdf")"
ETG1="$(echo "$GET1" | awk -F': ' 'tolower($1)=="etag"{gsub("\r","",$2); print $2}' | tail -n 1)"
LENG1="$(echo "$GET1" | awk -F': ' 'tolower($1)=="content-length"{gsub("\r","",$2); print $2}' | tail -n 1)"
echo "GET_LEN1=$LENG1 ET1=\"$ETG1\""

GET2="$(curl -sS -D- -o /dev/null "$DOMAIN/p/$TOKEN/report/pdf")"
ETG2="$(echo "$GET2" | awk -F': ' 'tolower($1)=="etag"{gsub("\r","",$2); print $2}' | tail -n 1)"
LENG2="$(echo "$GET2" | awk -F': ' 'tolower($1)=="content-length"{gsub("\r","",$2); print $2}' | tail -n 1)"
echo "GET_LEN2=$LENG2 ET2=\"$ETG2\""

[ "$ETG1" = "$ETG2" ] && [ "$LENG1" = "$LENG2" ] && echo "OK: PDF cache estável" || echo "ATENÇÃO: PDF variou (investigar)"

echo
echo "== [9] DB checks: status/progress + empty_text_count + snapshot/pdf_path =="
set -a
. runtime/.env
set +a

TOKEN_HASH="$(python3 -c 'from backend.services.token import token_hash; import sys; print(token_hash(sys.argv[1]))' "$TOKEN")"
echo "TOKEN_HASH=$TOKEN_HASH"

ATTEMPT_ID="$(
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" compose-db-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "
select a.id
from attempts a
where a.token_hash = '$TOKEN_HASH'
order by a.data_inicio desc
limit 1;
"
)"
echo "ATTEMPT_ID=$ATTEMPT_ID"
test -n "$ATTEMPT_ID"

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" compose-db-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select status, progress, data_inicio, data_conclusao
from attempts
where id = '$ATTEMPT_ID';
"

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" compose-db-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select
  cr.attempt_id,
  sum(case when coalesce(cr.interpretations->k->>'text','') = '' then 1 else 0 end) as empty_text_count
from computed_results cr,
     jsonb_object_keys(cr.interpretations) as k
where cr.attempt_id = '$ATTEMPT_ID'
group by cr.attempt_id;
"

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" compose-db-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select attempt_id, length(html_content) as html_len, pdf_path
from report_snapshots
where attempt_id = '$ATTEMPT_ID';
"

echo
echo "== [10] Idempotência: submit 2x (não deve quebrar) =="
SUBH2="$(curl -sS -D- -o /dev/null -X POST "$DOMAIN/p/$TOKEN/submit")"
echo "$SUBH2" | sed -n '1,15p'
echo "$SUBH2" | grep -q "303" && echo "OK: submit 2x ainda 303" || { echo "ERRO: submit 2x"; exit 1; }

echo
echo "✅ E2E FULL SMOKE OK"
