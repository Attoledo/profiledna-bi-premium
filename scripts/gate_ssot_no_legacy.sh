#!/usr/bin/env bash
set -euo pipefail

# defaults para rodar com set -u (SSOT CI/local)
DOMAIN="${DOMAIN:-http://127.0.0.1:18081}"
RESOLVE_OPT="${RESOLVE_OPT:-}"

# CI: em qualquer erro, dump de logs/diagnóstico
trap 'dump_ci_debug' ERR

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"


echo "== Gate SSOT: no legacy interpretations_per_score =="

echo
echo "== (1) Repo scan: proibir legacy + fallback =="
BAD1="$(grep -RIn --line-number --exclude-dir=.git --exclude-dir=volumes --exclude-dir=backups \
  "interpretations_per_score\.json" backend | grep -vE "docs/SSOT_PROFILEDNA_v2_0\.md" || true)"
BAD2="$(grep -RIn --line-number --exclude-dir=.git --exclude-dir=volumes --exclude-dir=backups \
  "Sem texto encontrado" backend || true)"
if [ -n "$BAD1" ]; then echo "ERRO legacy:"; echo "$BAD1"; exit 1; fi
if [ -n "$BAD2" ]; then echo "ERRO fallback:"; echo "$BAD2"; exit 1; fi
echo "OK: sem legacy/fallback no backend"

echo
echo "== (2) /health via Nginx (SNI local) =="
curl -fsS $RESOLVE_OPT "$DOMAIN/health" >/dev/null
echo "OK: /health"

echo
echo "== (3) E2E: start -> autosave 100 -> submit -> validar DB =="

dump_ci_debug() {
  echo "== DEBUG: docker ps ==" || true
  docker ps -a || true
  echo "== DEBUG: api logs (tail 200) ==" || true
  docker logs --tail 200 compose-api_v2-1 || true
  echo "== DEBUG: db logs (tail 120) ==" || true
  docker logs --tail 120 compose-db-1 || true
}

curl_json() {
  # usage: curl_json <METHOD> <URL> <JSON_PAYLOAD>
  m="$1"; url="$2"; payload="$3"
  tmp_body="$(mktemp)"
  code="$(curl -sS -o "$tmp_body" -w "%{http_code}" -H "Content-Type: application/json" -X "$m" $RESOLVE_OPT "$url" -d "$payload" || echo "000")"
  echo "== HTTP $m $url -> $code =="
  echo "== BODY =="; cat "$tmp_body" || true; echo
  rm -f "$tmp_body" || true
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ]
}

EMAIL="gate_legacy_$(date +%s)@example.com"
LOC="$(
  curl -sS -D- -o /dev/null \
    $RESOLVE_OPT \
    -X POST "$DOMAIN/start" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data "nome=Gate&sobrenome=NoLegacy&email=${EMAIL}&tipo_aplicacao=pessoal" \
  | awk -F': ' 'tolower($1)=="location"{gsub("\r","",$2); print $2}'
)"
TOKEN="$(echo "$LOC" | sed -n 's|^/p/\([^/]*\)/q/1$|\1|p')"
test -n "$TOKEN"
echo "TOKEN=$TOKEN"

for i in $(seq 1 100); do
  if [ $((i % 2)) -eq 0 ]; then c="B"; else c="A"; fi
  curl -sS -o /dev/null \
    $RESOLVE_OPT \
    -X POST "$DOMAIN/p/$TOKEN/autosave" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data "question_number=$i&choice=$c"
done
echo "OK: autosave 100"

HDR="$(curl -sS -D- -o /dev/null \
  $RESOLVE_OPT \
  -X POST "$DOMAIN/p/$TOKEN/submit" | sed -n '1,20p')"
echo "$HDR" | head -n 5
echo "$HDR" | grep -q "303" || (echo "ERRO: submit != 303" && exit 1)
echo "OK: submit 303"

TOKEN_HASH="$(
python3 -c 'from backend.services.token import token_hash; import sys; print(token_hash(sys.argv[1]))' "$TOKEN"
)"
test -n "$TOKEN_HASH"
echo "TOKEN_HASH=$TOKEN_HASH"

set -a
. runtime/.env
set +a

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
test -n "$ATTEMPT_ID"
echo "ATTEMPT_ID=$ATTEMPT_ID"

EMPTY_COUNT="$(
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" compose-db-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "
select coalesce(sum(case when coalesce(cr.interpretations->k->>'text','') = '' then 1 else 0 end),0)
from computed_results cr, jsonb_object_keys(cr.interpretations) as k
where cr.attempt_id = '$ATTEMPT_ID';
"
)"
echo "empty_text_count=$EMPTY_COUNT"
[ "$EMPTY_COUNT" = "0" ] || (echo "ERRO: texts vazios em $EMPTY_COUNT dimensões" && exit 1)
echo "OK: DB interpretations.text preenchido (0 vazios)"

echo
echo "== (4) HTML: sem legacy e com faixa PT-BR =="
HTML="$(curl -sS $RESOLVE_OPT "$DOMAIN/p/$TOKEN/report")"
echo "$HTML" | grep -q "interpretations_per_score" && (echo "ERRO: HTML contém legado" && exit 1) || true
echo "$HTML" | grep -Eiq "(Baixo|Médio|Alto)" || (echo "ERRO: não encontrei faixa PT-BR no HTML" && exit 1)
echo "OK: HTML sem legado e com faixa PT-BR"

echo

echo
echo "== (5) Architecture: routers/services sem SQL =="
R_BAD="$(grep -RIn --line-number --exclude-dir=.git --exclude-dir=volumes --exclude-dir=backups -E 'session\.execute|select\(' backend/routers || true)"
S_BAD="$(grep -RIn --line-number --exclude-dir=.git --exclude-dir=volumes --exclude-dir=backups -E 'session\.execute|select\(' backend/services || true)"

if [ -n "$R_BAD" ]; then
  echo "ERRO: routers possuem SQL (não permitido):"
  echo "$R_BAD"
  exit 1
fi
if [ -n "$S_BAD" ]; then
  echo "ERRO: services possuem SQL (não permitido):"
  echo "$S_BAD"
  exit 1
fi
echo "OK: routers/services sem SQL"


echo
echo "== (6) HTTP: HEAD no PDF report endpoint =="
H_HDR="$(curl -sSIL $RESOLVE_OPT "$DOMAIN/p/$TOKEN/report/pdf" | tr -d "\r")"
echo "$H_HDR" | head -n 5
echo "$H_HDR" | grep -q "HTTP/" || (echo "ERRO: sem headers no HEAD" && exit 1)
echo "$H_HDR" | grep -q " 200 " || (echo "ERRO: HEAD não retornou 200" && exit 1)
echo "$H_HDR" | grep -qi "Content-Type: application/pdf" || (echo "ERRO: HEAD sem Content-Type application/pdf" && exit 1)
echo "OK: HEAD PDF = 200 + content-type pdf"

echo "✅ PASS: Gate SSOT no-legacy OK"
