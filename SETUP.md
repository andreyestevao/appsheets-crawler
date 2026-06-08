# Migração AppSheet → CEI — inventário automatizado

Ferramenta local que usa **suas credenciais Google** (OAuth no navegador) para ler planilhas, inferir dependências entre abas/tabelas e gerar ordem de migração.

## O que NÃO fazer (segurança)

- **Nunca** envie senha Google no chat ou em commit.
- **Nunca** commite `credentials/client_secret.json`, `credentials/token.json` ou `apps_mapeamento.json` com chaves AppSheet.
- Preferir OAuth (este kit) em vez de compartilhar senha com ferramentas de IA.

## Passo 1 — Google Cloud OAuth (Sheets + Drive)

1. Acesse [Google Cloud Console](https://console.cloud.google.com/).
2. Crie ou selecione um projeto (ex.: `cei-migracao-inventario`).
3. Ative as APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. **OAuth consent screen** → External ou Internal (conta `@ufg.br` / Workspace CEI se aplicável).
5. **Credentials** → **Create credentials** → **OAuth client ID** → **Desktop app**.
6. Baixe o JSON e salve como:

   `/home/andrey/Documentos/CEI/migracao-appsheet/credentials/client_secret.json`

## Passo 2 — AppSheet API (opcional, enriquece inventário)

Para cada app que você edita no AppSheet:

1. **Manage** → **Settings** → **Integrations** → marque **Enable API**.
2. Anote o **App ID** e gere **Application Access Key**.
3. Em cada tabela usada via API: **Data** → tabela → **Are updates allowed?** → **Read-Only** (mínimo para inventário).
4. Copie o exemplo e preencha:

   ```bash
   cp apps_mapeamento.exemplo.json apps_mapeamento.json
   ```

   Preencha `app_id` por `appName` (o sufixo `-745673639` aparece nas URLs do documento).

## Passo 3 — Executar inventário

```bash
cd /home/andrey/Documentos/CEI/migracao-appsheet
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/inventariar.py
```

Na **primeira execução** abre o navegador → faça login com a conta Google que acessa as planilhas/AppSheet CEI → autorize escopos **somente leitura**.

Token renovável salvo em `credentials/token.json` (gitignored).

## Saídas

| Arquivo | Conteúdo |
|---------|----------|
| `saida/inventario-*.json` | Entradas do markdown, abas, colunas, refs detectadas, grafo |
| `saida/inventario-latest.json` | Última execução |
| `saida/ordem-migracao.md` | Ordem topológica sugerida + base CEI (SSO, RBAC, MinIO, Pessoas) |

## Passo 4 — Devolver resultado ao agente Cursor

Após rodar localmente, no chat:

1. Anexe ou peça para ler `saida/inventario-latest.json` e `saida/ordem-migracao.md`.
2. Se alguma planilha retornou erro 403, compartilhe a planilha com o e-mail da conta OAuth (Leitor).
3. Para apps sem `apps_mapeamento.json`, o script ainda inventaria URLs e planilhas explícitas no markdown.

## Alternativa: browser Cursor (sessão manual)

Se preferir não usar OAuth local agora:

1. Abra um link AppSheet no browser logado.
2. Peça ao agente para inspecionar via browser MCP **depois** do login.
3. Limite: mais lento e incompleto versus inventário JSON de todas as abas.

## Próximo passo após inventário

Com o JSON completo, o agente pode:

- Nomear UCs (`Manter …`) por tabela/app real.
- Refinar ordem usando colunas Ref + volume de dados + anexos.
- Marcar apps substituíveis (Homologação OEU, Planos Anuais duplicados).
- Propor schema relacional inicial por módulo.
