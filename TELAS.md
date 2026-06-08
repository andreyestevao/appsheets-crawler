# Inventário de telas AppSheet (UI autenticada)

Varredura **sem limite de tempo por link**: avança quando abas, filtros e formulário novo foram explorados e a UI estabilizou. Browser **visível**, sem gravar nem excluir dados.

## Política somente leitura

| Ação | Comportamento |
|------|----------------|
| Menu views (Toggle menu) | Abre hamburger, lista views, captura |
| Abas / views | Clica por `indice_dom` / aria-label (não toolbar Add/Filter/Sync) |
| Filtros | Abre painel, captura, fecha |
| Botão + / Add / Novo | Abre formulário vazio, captura, fecha com Cancelar/Escape (**sem Salvar**) |
| **Salvar / Excluir** | **Só detecta e registra no JSON — nunca clica** |
| HTTP Add/Edit/Delete | Bloqueado no browser |

## Comandos

```bash
cd appsheets-crawler   # raiz do repositório clonado

./inventariar-telas.sh --login                    # aguarda login até 60s
./inventariar-telas.sh                            # varredura completa, browser visível
./inventariar-telas.sh --limite 2                 # teste
./inventariar-telas.sh --app atividadesEcompras
```

**Não use `--headless`** se quiser acompanhar abas e filtros.

## Saída por link

- `01-inicial.*` — view do link
- `01b-menu-views-aberto.*` — menu hamburger aberto (quando existir)
- `02-aba-NN-*.*` — cada aba/view explorada
- `03-filtro-NN.*` — painel de filtro
- `04-formulario-novo-aberto.*` — form aberto pelo + (sem salvar)
- `inventario-telas.json` — inclui `leitura_concluida`, `fases_concluidas`, `botoes_salvar_excluir`

## Sessão

Perfil: `credentials/browser-appsheet-profile/` (gitignored).
