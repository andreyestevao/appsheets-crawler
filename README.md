# appsheets-crawler

Ferramentas locais para **inventariar apps Google AppSheet** (UI autenticada e, opcionalmente, planilhas/API) antes de migrar para outro stack. A estratégia é **agnóstica**: este repositório só coleta estrutura e dependências; a decisão de destino fica com você.

Dois fluxos complementares:

| Fluxo | Comando | Saída |
|-------|---------|-------|
| **Telas autenticadas** (Playwright, somente leitura) | `./inventariar-telas.sh` | `saida/telas/` — JSON, screenshots, resumo |
| **Planilhas / API** (OAuth Google, opcional) | `python scripts/inventariar.py` | `saida/inventario-*.json`, `ordem-migracao.md` |

Documentação:

- [TELAS.md](TELAS.md) — varredura de UI AppSheet (política read-only)
- [SETUP.md](SETUP.md) — OAuth Google, AppSheet API, inventário de planilhas

## Requisitos

- Python 3.10+
- Chromium (instalado via Playwright no primeiro `./inventariar-telas.sh`)

## Início rápido

```bash
git clone https://github.com/andreyestevao/appsheets-crawler.git
cd appsheets-crawler

cp links.exemplo.md links.md   # edite com seus links AppSheet/Sheets

./inventariar-telas.sh --login
./inventariar-telas.sh --documento links.md
```

Ou informe outro markdown: `--documento /caminho/seus-links.md`.

## O que não vai para o Git

Pastas e arquivos locais (ver `.gitignore`):

- `saida/` — resultados de varredura e inventário
- `links.md` — seu catálogo de apps (use `links.exemplo.md` como base)
- `credentials/` — OAuth, perfil do browser, chaves AppSheet
- `apps_mapeamento.json` — chaves de API por app
- `.venv/`

## Licença

MIT (ou conforme indicado no repositório).
