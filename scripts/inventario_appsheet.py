"""
Cliente AppSheet API v2 (Find) para listar tabelas quando appId e chave estão configurados.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import requests

URL_BASE = "https://api.appsheet.com/api/v2/apps"


@dataclass
class TabelaAppSheet:
    """Amostra de metadados de uma tabela AppSheet."""

    app_id: str
    app_name: str
    nome_tabela: str
    colunas: list[str] = field(default_factory=list)
    amostra_registros: int = 0
    erro: str | None = None


def carregar_mapeamento(caminho: Path) -> dict:
    """Carrega apps_mapeamento.json (copiado do exemplo)."""
    if not caminho.is_file():
        return {"apps": {}, "chave_acesso_global": None}
    return json.loads(caminho.read_text(encoding="utf-8"))


def descobrir_colunas_via_api(
    app_id: str,
    nome_tabela: str,
    chave_acesso: str,
    limite_amostra: int = 3,
) -> TabelaAppSheet:
    """
    Executa Action Find na tabela e infere colunas pela união das chaves retornadas.

    Requer API habilitada no app e permissão de leitura na tabela.
    """
    url = f"{URL_BASE}/{app_id}/tables/{nome_tabela}/Action"
    corpo = {
        "Action": "Find",
        "Properties": {
            "Locale": "pt-BR",
        },
    }
    try:
        resposta = requests.post(
            url,
            headers={
                "ApplicationAccessKey": chave_acesso,
                "Content-Type": "application/json",
            },
            json=corpo,
            timeout=60,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, list):
            return TabelaAppSheet(
                app_id=app_id,
                app_name="",
                nome_tabela=nome_tabela,
                erro=f"Resposta inesperada: {type(dados)}",
            )
        colunas: set[str] = set()
        for registro in dados[:limite_amostra]:
            if isinstance(registro, dict):
                colunas.update(registro.keys())
        return TabelaAppSheet(
            app_id=app_id,
            app_name="",
            nome_tabela=nome_tabela,
            colunas=sorted(colunas),
            amostra_registros=len(dados),
        )
    except requests.RequestException as exc:
        return TabelaAppSheet(
            app_id=app_id,
            app_name="",
            nome_tabela=nome_tabela,
            erro=str(exc),
        )


def inventariar_apps_configurados(
    mapeamento: dict,
    entradas_por_app: dict[str, list],
) -> list[TabelaAppSheet]:
    """
    Para cada app em apps_mapeamento.json, consulta tabelas indicadas nas entradas ou no JSON.
    """
    chave_global = mapeamento.get("chave_acesso_global")
    apps_cfg = mapeamento.get("apps", {})
    resultados: list[TabelaAppSheet] = []

    for app_name, cfg in apps_cfg.items():
        app_id = cfg.get("app_id")
        if not app_id or app_id.startswith("SUBSTITUA"):
            continue
        chave = cfg.get("chave_acesso") or chave_global
        if not chave or str(chave).startswith("OPCIONAL"):
            continue

        tabelas_cfg = cfg.get("tabelas_prioritarias") or []
        tabelas_urls = {
            e.table for e in entradas_por_app.get(app_name, []) if getattr(e, "table", None)
        }
        tabelas = sorted(set(tabelas_cfg) | tabelas_urls)
        if not tabelas:
            tabelas = ["Data"]  # fallback comum AppSheet

        for tabela in tabelas:
            item = descobrir_colunas_via_api(app_id, tabela, chave)
            item.app_name = app_name
            resultados.append(item)

    return resultados
