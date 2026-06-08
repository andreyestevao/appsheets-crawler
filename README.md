# migracao-appsheet

Ferramentas locais para inventariar apps **Google AppSheet** antes da migração para a arquitetura CEI (PostgreSQL + `cei_apps_service` + frontends Angular).

Dois fluxos complementares:

| Fluxo | Comando | Saída |
|-------|---------|-------|
| **Telas autenticadas** (Playwright, somente leitura) | `./inventariar-telas.sh` | `saida/telas/` — JSON, screenshots, resumo |
| **Planilhas / API** (OAuth Google, opcional) | `python scripts/inventariar.py` | `saida/inventario-*.json`, `ordem-migracao.md` |

Documentação detalhada:

- [TELAS.md](TELAS.md) — varredura de UI AppSheet (política read-only)
- [SETUP.md](SETUP.md) — OAuth Google, AppSheet API, inventário de planilhas

## Requisitos

- Python 3.10+
- Chromium (instalado via Playwright no primeiro `./inventariar-telas.sh`)

## Início rápido — inventário de telas

```bash
git clone https://github.com/andreyestevao/migracao-appsheet.git
cd migracao-appsheet

./inventariar-telas.sh --login    # login manual no browser (perfil em credentials/)
./inventariar-telas.sh            # varredura completa; artefatos em saida/telas/
```

Informe o markdown de links com `--links /caminho/Link\ das\ aplicações.md` (padrão: documento CEI local).

## O que não vai para o Git

Pastas e arquivos locais (ver `.gitignore`):

- `saida/` — resultados de varredura e inventário
- `credentials/` — OAuth, perfil do browser, chaves AppSheet
- `apps_mapeamento.json` — chaves de API por app
- `.venv/`

## Planos de migração CEI

Cronograma e ordem de módulos ficam em documentação separada (pasta **Plano Migração CEI**), fora deste repositório de ferramentas.

## Licença

Uso interno / projeto CEI.
