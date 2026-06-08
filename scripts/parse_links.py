"""
Extrai entradas de um markdown de catálogo ([Link](url)) para inventário AppSheet/Sheets.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EntradaLink:
    """Representa um link catalogado no documento de aplicações."""

    titulo: str
    url: str
    tipo: str  # appsheet | sheets | desconhecido
    app_name: str | None = None
    spreadsheet_id: str | None = None
    gid: str | None = None
    view: str | None = None
    table: str | None = None
    observacao: str | None = None


PADRAO_LINK = re.compile(r"\[Link\]\((https?://[^)]+)\)", re.IGNORECASE)
PADRAO_SHEETS = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
PADRAO_GID = re.compile(r"[?#&]gid=(\d+)")


def _extrair_app_name(url: str) -> str | None:
    fragmento = urllib.parse.urlparse(url).fragment
    if not fragmento:
        return None
    params = urllib.parse.parse_qs(fragmento)
    nomes = params.get("appName") or params.get("appname")
    return nomes[0] if nomes else None


def _extrair_view(url: str) -> str | None:
    fragmento = urllib.parse.urlparse(url).fragment
    if not fragmento:
        return None
    params = urllib.parse.parse_qs(fragmento)
    views = params.get("view")
    return urllib.parse.unquote(views[0]) if views else None


def _extrair_table(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "table" in params:
        return params["table"][0]
    if parsed.fragment:
        frag_params = urllib.parse.parse_qs(parsed.fragment)
        tables = frag_params.get("table")
        if tables:
            return tables[0]
    return None


def parsear_markdown(caminho: Path) -> list[EntradaLink]:
    """
    Lê o markdown e retorna entradas com metadados extraídos das URLs.

    Parâmetros:
        caminho: caminho para 'Link das aplicações.md'.

    Retorno:
        Lista de EntradaLink na ordem do arquivo.
    """
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    entradas: list[EntradaLink] = []
    titulo_atual = ""
    observacao_buffer: list[str] = []

    def flush_observacao() -> str | None:
        if not observacao_buffer:
            return None
        obs = " ".join(l.strip() for l in observacao_buffer if l.strip())
        observacao_buffer.clear()
        return obs or None

    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue

        match_link = PADRAO_LINK.search(linha)
        if match_link:
            url = match_link.group(1)
            obs = flush_observacao()
            if linha_limpa.startswith("[Link]"):
                titulo = titulo_atual or "Sem título"
            else:
                titulo = linha_limpa.split("[Link]")[0].strip(" :-")

            tipo = "desconhecido"
            spreadsheet_id = None
            gid = None
            if "appsheet.com" in url:
                tipo = "appsheet"
            elif "docs.google.com/spreadsheets" in url:
                tipo = "sheets"
                match_sheet = PADRAO_SHEETS.search(url)
                spreadsheet_id = match_sheet.group(1) if match_sheet else None
                match_gid = PADRAO_GID.search(url)
                gid = match_gid.group(1) if match_gid else None

            entradas.append(
                EntradaLink(
                    titulo=titulo,
                    url=url,
                    tipo=tipo,
                    app_name=_extrair_app_name(url),
                    spreadsheet_id=spreadsheet_id,
                    gid=gid,
                    view=_extrair_view(url),
                    table=_extrair_table(url),
                    observacao=obs,
                )
            )
            continue

        if linha_limpa.startswith("Entendimento") or linha_limpa.startswith("Requisito ") or linha_limpa.startswith("Acredito"):
            observacao_buffer.append(linha_limpa)
            continue

        if "[Link]" not in linha and not linha_limpa.startswith("O objetivo") and not linha_limpa.startswith("Relaciona") and not linha_limpa.startswith("Possivelmente") and not linha_limpa.startswith("Uma atividade") and not linha_limpa.startswith("Tem um filtro") and not linha_limpa.startswith("Replica") and not linha_limpa.startswith("A funcionalidade") and not linha_limpa.startswith("Como é"):
            titulo_atual = linha_limpa.replace("\\-", "-").strip()
            flush_observacao()
        else:
            observacao_buffer.append(linha_limpa)

    return entradas


def agrupar_por_app(entradas: list[EntradaLink]) -> dict[str, list[EntradaLink]]:
    """Agrupa entradas AppSheet pelo appName."""
    grupos: dict[str, list[EntradaLink]] = {}
    for entrada in entradas:
        if not entrada.app_name:
            continue
        grupos.setdefault(entrada.app_name, []).append(entrada)
    return grupos
