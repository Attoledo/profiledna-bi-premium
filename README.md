# ProfileDNA

Infra: Ubuntu + Nginx + Docker Compose + Postgres + FastAPI (Jinja2).
Ambiente prod: https://profiledna.dnaagencia.com

## Estrutura
- app/            (código FastAPI)
- compose/        (docker-compose.yml)
- runtime/        (.env.example; .env fica fora do git)
- volumes/        (dados persistentes, fora do git)
- backups/        (backups, fora do git)

## Subir local no servidor
- DB: docker compose up -d db
- API: docker compose up -d --build api
