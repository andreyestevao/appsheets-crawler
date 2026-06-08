"""
Inventário de planilhas Google (backends AppSheet e bancos diretos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class AbaPlanilha:
    """Metadados de uma aba (tabela) dentro de uma planilha."""

    nome: str
    sheet_id: int
    linhas_dados: int
    colunas: list[str] = field(default_factory=list)
    colunas_referencia: list[str] = field(default_factory=list)
    colunas_anexo: list[str] = field(default_factory=list)


@dataclass
class PlanilhaInventario:
    """Inventário completo de uma planilha Google."""

    spreadsheet_id: str
    titulo: str
    abas: list[AbaPlanilha] = field(default_factory=list)
    erro: str | None = None


SUFIXOS_REF = ("Id", "ID", "_id", "Ref", "REF")
PALAVRAS_ANEXO = ("anexo", "arquivo", "documento", "file", "image", "foto", "pdf")


def _normalizar_nome(nome: str) -> str:
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def _detectar_referencias(colunas: list[str], nomes_abas: set[str]) -> list[str]:
    """
    Heurística AppSheet/Sheets: coluna referencia outra aba se:
    - nome igual ou parecido com aba existente;
    - termina com Id/Ref e prefixo bate com aba.
    """
    refs: list[str] = []
    abas_norm = {_normalizar_nome(a): a for a in nomes_abas}

    for coluna in colunas:
        col_norm = _normalizar_nome(coluna)
        if col_norm in abas_norm:
            refs.append(coluna)
            continue
        for sufixo in SUFIXOS_REF:
            if coluna.endswith(sufixo):
                prefixo = coluna[: -len(sufixo)]
                prefixo_norm = _normalizar_nome(prefixo)
                if prefixo_norm in abas_norm:
                    refs.append(coluna)
                    break
    return refs


def _detectar_anexos(colunas: list[str]) -> list[str]:
    return [c for c in colunas if any(p in c.lower() for p in PALAVRAS_ANEXO)]


def inventariar_planilha(servico_sheets, spreadsheet_id: str) -> PlanilhaInventario:
    """
    Lê metadados e cabeçalhos de todas as abas de uma planilha.

    Parâmetros:
        servico_sheets: cliente retornado por google_auth.criar_servico_sheets.
        spreadsheet_id: ID da planilha na URL Google Sheets.
    """
    try:
        meta = (
            servico_sheets.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — erro de API repassado no inventário
        return PlanilhaInventario(
            spreadsheet_id=spreadsheet_id,
            titulo="",
            erro=str(exc),
        )

    titulo = meta.get("properties", {}).get("title", spreadsheet_id)
    sheets = meta.get("sheets", [])
    nomes_abas = {
        s.get("properties", {}).get("title", "")
        for s in sheets
        if s.get("properties", {}).get("title")
    }

    abas: list[AbaPlanilha] = []
    for sheet in sheets:
        props = sheet.get("properties", {})
        nome_aba = props.get("title", "Sem nome")
        sheet_id = props.get("sheetId", 0)
        grid = props.get("gridProperties", {})
        row_count = grid.get("rowCount", 0)

        cabecalho: list[str] = []
        try:
            resultado = (
                servico_sheets.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{nome_aba}'!1:1",
                    majorDimension="ROWS",
                )
                .execute()
            )
            linhas = resultado.get("values", [])
            if linhas and linhas[0]:
                cabecalho = [str(c).strip() for c in linhas[0] if str(c).strip()]
        except Exception:
            cabecalho = []

        abas.append(
            AbaPlanilha(
                nome=nome_aba,
                sheet_id=sheet_id,
                linhas_dados=max(row_count - 1, 0),
                colunas=cabecalho,
                colunas_referencia=_detectar_referencias(cabecalho, nomes_abas),
                colunas_anexo=_detectar_anexos(cabecalho),
            )
        )

    return PlanilhaInventario(spreadsheet_id=spreadsheet_id, titulo=titulo, abas=abas)
