#!/usr/bin/env python3
"""
Inventário automatizado dos links AppSheet/Sheets para migração CEI.

Uso:
  cd /home/andrey/Documentos/CEI/migracao-appsheet
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python scripts/inventariar.py

Na primeira execução abre o navegador para login Google (OAuth).
Credenciais ficam em credentials/ (gitignored).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
sys.path.insert(0, str(SCRIPTS))

from google_auth import criar_servico_drive, criar_servico_sheets, obter_credenciais  # noqa: E402
from grafo_migracao import (  # noqa: E402
    adicionar_nos_appsheet,
    construir_grafo_planilhas,
    montar_relatorio_ordem,
    ordenar_migracao,
)
from inventario_appsheet import carregar_mapeamento, inventariar_apps_configurados  # noqa: E402
from inventario_planilhas import inventariar_planilha  # noqa: E402
from parse_links import agrupar_por_app, parsear_markdown  # noqa: E402

DOCUMENTO_LINKS = Path("/home/andrey/Documentos/CEI/Link das aplicações.md")
PASTA_SAIDA = RAIZ / "saida"
PASTA_CRED = RAIZ / "credentials"
MAPEAMENTO = RAIZ / "apps_mapeamento.json"


def _serializar(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(type(obj))


def main() -> int:
    if not DOCUMENTO_LINKS.is_file():
        print(f"Documento não encontrado: {DOCUMENTO_LINKS}", file=sys.stderr)
        return 1

    entradas = parsear_markdown(DOCUMENTO_LINKS)
    por_app = agrupar_por_app(entradas)

    spreadsheet_ids = sorted({e.spreadsheet_id for e in entradas if e.spreadsheet_id})
    titulos_por_sheet = {
        e.spreadsheet_id: e.titulo
        for e in entradas
        if e.spreadsheet_id
    }

    print("Autenticando Google (OAuth)...")
    credenciais = obter_credenciais(PASTA_CRED)
    servico_sheets = criar_servico_sheets(credenciais)
    servico_drive = criar_servico_drive(credenciais)

    inventarios_planilhas = []
    for sheet_id in spreadsheet_ids:
        print(f"  Planilha {sheet_id}...")
        inventarios_planilhas.append(inventariar_planilha(servico_sheets, sheet_id))

    # Drive: tenta localizar planilhas adicionais mencionadas só via AppSheet (opcional).
    planilhas_drive: list[dict] = []
    for app_name in por_app:
        consulta = f"mimeType='application/vnd.google-apps.spreadsheet' and name contains '{app_name.split('-')[0]}'"
        try:
            resultado = (
                servico_drive.files()
                .list(q=consulta, pageSize=5, fields="files(id,name,modifiedTime)")
                .execute()
            )
            for arquivo in resultado.get("files", []):
                planilhas_drive.append({"app_name": app_name, **arquivo})
        except Exception as exc:  # noqa: BLE001
            planilhas_drive.append({"app_name": app_name, "erro": str(exc)})

    mapeamento = carregar_mapeamento(MAPEAMENTO)
    inventario_api = inventariar_apps_configurados(mapeamento, por_app)

    nos = construir_grafo_planilhas(inventarios_planilhas, titulos_por_sheet)
    adicionar_nos_appsheet(nos, por_app)
    ordem, ciclos = ordenar_migracao(nos)

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "gerado_em": timestamp,
        "documento_origem": str(DOCUMENTO_LINKS),
        "entradas": [_serializar(e) for e in entradas],
        "planilhas": [_serializar(p) for p in inventarios_planilhas],
        "planilhas_drive_sugeridas": planilhas_drive,
        "appsheet_api": [_serializar(t) for t in inventario_api],
        "grafo": {
            node_id: {
                **_serializar(no),
                "dependencias": sorted(no.dependencias),
            }
            for node_id, no in nos.items()
        },
        "ordem_migracao": ordem,
        "ciclos": ciclos,
    }

    caminho_json = PASTA_SAIDA / f"inventario-{timestamp}.json"
    caminho_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    caminho_md = PASTA_SAIDA / "ordem-migracao.md"
    caminho_md.write_text(montar_relatorio_ordem(nos, ordem, ciclos), encoding="utf-8")

    # Mantém symlink lógico via cópia do último JSON.
    ultimo = PASTA_SAIDA / "inventario-latest.json"
    ultimo.write_text(caminho_json.read_text(encoding="utf-8"), encoding="utf-8")

    print("")
    print(f"Inventário JSON: {caminho_json}")
    print(f"Ordem migração:  {caminho_md}")
    print(f"Apps AppSheet:   {len(por_app)} agrupados; API consultada: {len(inventario_api)} tabelas")
    if ciclos:
        print(f"Atenção: {len(ciclos)} nó(s) com ciclo de dependência — revisar ordem-migracao.md")
    if not MAPEAMENTO.is_file():
        print("Dica: copie apps_mapeamento.exemplo.json -> apps_mapeamento.json para enriquecer via AppSheet API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
