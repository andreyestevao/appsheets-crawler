"""
Grafo de dependências entre tabelas/abas e ordenação topológica para migração.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from inventario_planilhas import PlanilhaInventario


@dataclass
class NoMigracao:
    """Nó do grafo de migração (tabela ou requisito)."""

    identificador: str
    titulo: str
    origem: str  # sheets | appsheet | cei_existente
    spreadsheet_id: str | None = None
    nome_aba: str | None = None
    app_name: str | None = None
    linhas_dados: int = 0
    tem_anexos: bool = False
    peso_complexidade: int = 0
    observacao: str | None = None
    dependencias: set[str] = field(default_factory=set)


# Pré-requisitos já previstos na arquitetura CEI (ordem fixa no início).
NOS_CEI_BASE = [
    ("cei:sso", "Manter Autenticação SSO", 0),
    ("cei:rbac", "Manter Permissões / RBAC", 1),
    ("cei:anexos", "Infraestrutura de anexos (MinIO)", 2),
    ("cei:pessoas", "Manter Pessoas / Colaborador", 3),
]


def _id_planilha(spreadsheet_id: str, aba: str) -> str:
    return f"sheet:{spreadsheet_id}:{aba}"


def construir_grafo_planilhas(
    inventarios: list[PlanilhaInventario],
    titulos_por_spreadsheet: dict[str, str],
) -> dict[str, NoMigracao]:
    """
    Constrói nós e arestas a partir do inventário de planilhas.

    Aresta A -> B significa: migrar B antes de A.
    """
    nos: dict[str, NoMigracao] = {}

    for inv in inventarios:
        if inv.erro:
            continue
        nomes_abas = {a.nome for a in inv.abas}
        for aba in inv.abas:
            node_id = _id_planilha(inv.spreadsheet_id, aba.nome)
            titulo_doc = titulos_por_spreadsheet.get(inv.spreadsheet_id, inv.titulo)
            nos[node_id] = NoMigracao(
                identificador=node_id,
                titulo=f"{titulo_doc} / {aba.nome}",
                origem="sheets",
                spreadsheet_id=inv.spreadsheet_id,
                nome_aba=aba.nome,
                linhas_dados=aba.linhas_dados,
                tem_anexos=bool(aba.colunas_anexo),
                peso_complexidade=len(aba.colunas) + (10 if aba.colunas_anexo else 0),
            )

            for col_ref in aba.colunas_referencia:
                alvo = None
                col_lower = col_ref.lower()
                for nome_aba in nomes_abas:
                    if col_lower == nome_aba.lower():
                        alvo = nome_aba
                        break
                    for sufixo in ("id", "ref"):
                        if col_lower.endswith(sufixo) and col_lower[: -len(sufixo)] in nome_aba.lower():
                            alvo = nome_aba
                            break
                    if alvo:
                        break
                if alvo and alvo != aba.nome:
                    dep_id = _id_planilha(inv.spreadsheet_id, alvo)
                    nos[node_id].dependencias.add(dep_id)

    return nos


def adicionar_nos_appsheet(
    nos: dict[str, NoMigracao],
    entradas_agrupadas: dict[str, list],
) -> None:
    """Cria nós por app/tabela quando a URL informa table=."""
    for app_name, entradas in entradas_agrupadas.items():
        tabelas = {e.table for e in entradas if e.table}
        for tabela in tabelas:
            node_id = f"appsheet:{app_name}:{tabela}"
            titulos = [e.titulo for e in entradas if e.table == tabela]
            nos[node_id] = NoMigracao(
                identificador=node_id,
                titulo=titulos[0] if titulos else f"{app_name} / {tabela}",
                origem="appsheet",
                app_name=app_name,
                nome_aba=tabela,
                observacao=next((e.observacao for e in entradas if e.observacao), None),
            )


def ordenar_migracao(nos: dict[str, NoMigracao]) -> tuple[list[str], list[str]]:
    """
    Ordenação topológica (Kahn) + desempate por complexidade/volume.

    Retorno:
        (ordem_ids, ciclos_detectados)
    """
    grafo: dict[str, set[str]] = defaultdict(set)
    grau_entrada: dict[str, int] = {node_id: 0 for node_id in nos}

    for node_id, no in nos.items():
        for dep in no.dependencias:
            if dep not in nos:
                continue
            grafo[dep].add(node_id)
            grau_entrada[node_id] += 1

    fila = deque(
        sorted(
            [n for n, g in grau_entrada.items() if g == 0],
            key=lambda n: (
                nos[n].origem != "sheets",
                nos[n].peso_complexidade,
                nos[n].linhas_dados,
                nos[n].titulo,
            ),
        )
    )

    ordem: list[str] = []
    while fila:
        atual = fila.popleft()
        ordem.append(atual)
        for vizinho in sorted(grafo[atual], key=lambda n: nos[n].titulo):
            grau_entrada[vizinho] -= 1
            if grau_entrada[vizinho] == 0:
                fila.append(vizinho)

    ciclos = [n for n, g in grau_entrada.items() if g > 0 and n not in ordem]
    return ordem, ciclos


def montar_relatorio_ordem(
    nos: dict[str, NoMigracao],
    ordem: list[str],
    ciclos: list[str],
) -> str:
    """Gera markdown com ordem sugerida e alertas."""
    linhas = [
        "# Ordem sugerida de migração (gerada automaticamente)",
        "",
        "Base CEI (fixa no início):",
        "",
    ]
    for idx, (_, titulo, _) in enumerate(NOS_CEI_BASE, start=1):
        linhas.append(f"{idx}. **{titulo}**")

    linhas.extend(["", "## Cadastros AppSheet / planilhas", ""])
    offset = len(NOS_CEI_BASE)
    for i, node_id in enumerate(ordem, start=offset + 1):
        no = nos[node_id]
        deps = [nos[d].titulo for d in no.dependencias if d in nos]
        extra = []
        if no.linhas_dados:
            extra.append(f"{no.linhas_dados} linhas")
        if no.tem_anexos:
            extra.append("anexos")
        if deps:
            extra.append(f"depende de: {', '.join(deps)}")
        sufixo = f" — {'; '.join(extra)}" if extra else ""
        linhas.append(f"{i}. **{no.titulo}** (`{no.identificador}`){sufixo}")

    if ciclos:
        linhas.extend(["", "## Ciclos / dependências não resolvidas", ""])
        for node_id in ciclos:
            linhas.append(f"- {nos[node_id].titulo}")

    linhas.append("")
    linhas.append(
        "_Revise manualmente: heurísticas de coluna Ref não capturam todas as regras AppSheet._"
    )
    return "\n".join(linhas)
