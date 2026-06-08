"""
Varredura interativa de uma tela AppSheet (somente leitura).

Explora menu de views, abas, filtros e formulário vazio de adição.
Avança quando a tela estabiliza — sem limite de tempo por link.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

_CLiques_PERMITIDOS = frozenset({"aba_view", "filtro", "abrir_formulario_novo", "cancelar", "outro"})
_CLiques_PROIBIDOS = frozenset({"salvar", "excluir"})

# Itens de toolbar AppSheet — não são views/abas.
_TOOLBAR_TEXTO_EXATO = frozenset({
    "add",
    "filter",
    "sync",
    "toggle menu",
    "view app status",
    "account menu",
    "expand",
    "ok",
    "×",
    "search",
    "search...",
    "close",
})

_MAX_ABAS = 20
_MAX_FILTROS = 5
_SELETOR_BOTOES = "button, [role='button'], [role='tab'], nav a, nav button, div[role='button']"


def _slug_curto(texto: str, max_len: int = 28) -> str:
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "-", texto.strip().lower())
    return (limpo.strip("-") or "item")[:max_len]


def _texto_clicavel(botao: dict) -> str:
    return (botao.get("texto") or botao.get("aria_label") or "").strip()


def _eh_toolbar(nome: str) -> bool:
    """True se o rótulo é controle de toolbar, não uma view do app."""
    if not nome or len(nome.strip()) <= 1:
        return True
    t = nome.lower().strip()
    if t in _TOOLBAR_TEXTO_EXATO:
        return True
    if t.startswith("view ref") or "\nedit" in t or "\ndelete" in t:
        return True
    if len(nome) > 70:
        return True
    return False


def _filtrar_candidatos_abas(ui: dict) -> list[dict]:
    """
    Monta candidatos a views/abas como dicts de botão (com indice_dom quando existir).
    Exclui toolbar e botões de ação.
    """
    vistos: set[str] = set()
    candidatos: list[dict] = []

    def adicionar(nome: str, botao: dict | None = None) -> None:
        if not nome or _eh_toolbar(nome):
            return
        chave = nome.strip().lower()
        if chave in vistos:
            return
        vistos.add(chave)
        if botao:
            candidatos.append(botao)
        else:
            candidatos.append({"texto": nome, "aria_label": "", "classificacao": "aba_view"})

    for botao in ui.get("botoes_classificados") or []:
        classificacao = botao.get("classificacao", "")
        if classificacao in _CLiques_PROIBIDOS:
            continue
        if classificacao in {"abrir_formulario_novo", "filtro", "cancelar"}:
            continue
        nome = _texto_clicavel(botao)
        if classificacao == "aba_view" or (classificacao == "outro" and len(nome) > 3):
            adicionar(nome, botao)

    for nome in ui.get("candidatos_abas") or []:
        adicionar(nome)

    for nome in ui.get("itens_navegacao") or []:
        adicionar(nome)

    return candidatos


def _aguardar_estabilizacao(pagina, extrair_ui, timeout_ms: int = 12000) -> None:
    """
    Aguarda a leitura da tela estabilizar (DOM + rede + assinatura UI repetida).
    """
    try:
        pagina.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        pagina.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
    except Exception:
        pass

    limite = time.time() + (timeout_ms / 1000.0)
    assinatura_anterior: tuple | None = None
    while time.time() < limite:
        ui = extrair_ui(pagina)
        if not ui:
            pagina.wait_for_timeout(400)
            continue
        assinatura = (
            ui.get("url", ""),
            len(ui.get("botoes_classificados") or []),
            len(ui.get("rotulos") or []),
        )
        if assinatura == assinatura_anterior:
            return
        assinatura_anterior = assinatura
        pagina.wait_for_timeout(450)

    pagina.wait_for_timeout(600)


def _clicar_botao_por_indice(pagina, indice_dom: int | None) -> bool:
    """Clica elemento pelo índice na lista AppSheet (mais confiável que texto)."""
    if indice_dom is None:
        return False
    try:
        return bool(
            pagina.evaluate(
                """({ indice, seletor }) => {
                  const els = document.querySelectorAll(seletor);
                  const el = els[indice];
                  if (!el) return false;
                  const r = el.getBoundingClientRect();
                  if (r.width <= 0 || r.height <= 0) return false;
                  el.click();
                  return true;
                }""",
                {"indice": indice_dom, "seletor": _SELETOR_BOTOES},
            )
        )
    except Exception:
        return False


def _clicar_por_aria(pagina, aria_label: str, timeout_ms: int = 3000) -> bool:
    if not aria_label:
        return False
    try:
        pagina.get_by_role("button", name=aria_label, exact=True).first.click(timeout=timeout_ms)
        return True
    except Exception:
        pass
    try:
        pagina.locator(f"[aria-label='{aria_label}']").first.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


def _clicar_por_texto(pagina, texto: str, timeout_ms: int = 3000) -> bool:
    if not texto or (len(texto) < 2 and texto != "+"):
        return False
    try:
        pagina.get_by_text(texto, exact=True).first.click(timeout=timeout_ms)
        return True
    except Exception:
        pass
    try:
        pagina.get_by_text(texto, exact=False).first.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


def _clicar_botao(pagina, botao: dict) -> bool:
    """Ordem: índice DOM → aria-label → texto."""
    classificacao = botao.get("classificacao", "")
    if classificacao in _CLiques_PROIBIDOS:
        return False
    if _clicar_botao_por_indice(pagina, botao.get("indice_dom")):
        return True
    if _clicar_por_aria(pagina, botao.get("aria_label") or ""):
        return True
    return _clicar_por_texto(pagina, _texto_clicavel(botao))


def _clicar_botao_classificado(pagina, botao: dict) -> bool:
    classificacao = botao.get("classificacao", "")
    if classificacao in _CLiques_PROIBIDOS:
        return False
    if classificacao not in _CLiques_PERMITIDOS:
        return False
    return _clicar_botao(pagina, botao)


def _salvar_captura(pagina, pasta: Path, nome_base: str, extrair_ui, raiz: Path) -> dict:
    screenshot = pasta / f"{nome_base}.png"
    json_path = pasta / f"{nome_base}.json"
    pagina.screenshot(path=str(screenshot), full_page=True)
    ui = extrair_ui(pagina) or {}
    json_path.write_text(json.dumps(ui, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "screenshot": str(screenshot.relative_to(raiz)),
        "json": str(json_path.relative_to(raiz)),
        "ui": ui,
    }


def _fechar_formulario_ou_painel(pagina, ui_atual: dict, extrair_ui) -> None:
    canceladores = [
        b for b in (ui_atual.get("botoes_classificados") or []) if b.get("classificacao") == "cancelar"
    ]
    for botao in canceladores:
        if _clicar_botao_classificado(pagina, botao):
            _aguardar_estabilizacao(pagina, extrair_ui, 6000)
            return
    try:
        pagina.keyboard.press("Escape")
        pagina.wait_for_timeout(500)
    except Exception:
        pass


def _coletar_perigosos(ui: dict | None) -> list[dict]:
    if not ui:
        return []
    encontrados = list(ui.get("botoes_salvar_excluir") or [])
    for botao in ui.get("botoes_classificados") or []:
        if botao.get("classificacao") in _CLiques_PROIBIDOS:
            chave = f"{botao.get('classificacao')}::{_texto_clicavel(botao)}"
            if not any(f"{e.get('classificacao')}::{_texto_clicavel(e)}" == chave for e in encontrados):
                encontrados.append(botao)
    return encontrados


def _voltar_url_base(pagina, url: str, timeout_navegacao_ms: int, extrair_ui) -> None:
    if not url:
        return
    pagina.goto(url, wait_until="domcontentloaded", timeout=timeout_navegacao_ms)
    _aguardar_estabilizacao(pagina, extrair_ui)


def _abrir_menu_views(pagina, ui: dict, extrair_ui) -> dict:
    """AppSheet: views costumam ficar atrás de 'Toggle menu'."""
    for botao in ui.get("botoes_classificados") or []:
        aria = (botao.get("aria_label") or "").lower()
        if aria == "toggle menu":
            if _clicar_botao(pagina, botao):
                _aguardar_estabilizacao(pagina, extrair_ui)
                return extrair_ui(pagina) or ui
    return ui


def varrer_tela(
    pagina,
    pasta_entrada: Path,
    extrair_ui,
    raiz: Path,
    timeout_navegacao_ms: int = 20000,
    url: str = "",
) -> dict:
    """
    Varre uma URL até esgotar views, filtros e formulário novo (sem limite de tempo).

    Conclui quando todas as fases terminam e a UI estabiliza.
    """
    inicio = time.time()
    resultado: dict = {
        "modo_tempo": "ate_estabilizar",
        "passos": [],
        "botoes_salvar_excluir_detectados": [],
        "capturas": {},
        "fases_concluidas": [],
    }

    if url:
        pagina.goto(url, wait_until="domcontentloaded", timeout=timeout_navegacao_ms)
    _aguardar_estabilizacao(pagina, extrair_ui)

    ui_inicial = extrair_ui(pagina)
    if not ui_inicial or ui_inicial.get("em_login"):
        resultado["status"] = "login_necessario"
        resultado["ui_inicial"] = ui_inicial
        return resultado

    cap_inicial = _salvar_captura(pagina, pasta_entrada, "01-inicial", extrair_ui, raiz)
    resultado["capturas"]["inicial"] = {
        "screenshot": cap_inicial["screenshot"],
        "json": cap_inicial["json"],
    }
    resultado["ui_inicial"] = cap_inicial["ui"]
    resultado["botoes_salvar_excluir_detectados"].extend(_coletar_perigosos(cap_inicial["ui"]))
    resultado["fases_concluidas"].append("inicial")

    # --- Menu de views (hamburger) ---
    ui_menu = _abrir_menu_views(pagina, cap_inicial["ui"], extrair_ui)
    if ui_menu is not cap_inicial["ui"]:
        cap_menu = _salvar_captura(pagina, pasta_entrada, "01b-menu-views-aberto", extrair_ui, raiz)
        resultado["capturas"]["menu_views"] = {
            "screenshot": cap_menu["screenshot"],
            "json": cap_menu["json"],
        }
        resultado["passos"].append({"tipo": "menu_views", "observacao": "Toggle menu aberto"})
        resultado["fases_concluidas"].append("menu_views")

    candidatos_abas = _filtrar_candidatos_abas(ui_menu)
    abas_visitadas: set[str] = set()
    indice_aba = 0

    for botao_aba in candidatos_abas[:_MAX_ABAS]:
        nome_aba = _texto_clicavel(botao_aba)
        if not nome_aba or nome_aba.lower() in abas_visitadas:
            continue
        _voltar_url_base(pagina, url, timeout_navegacao_ms, extrair_ui)
        ui_base = _abrir_menu_views(pagina, extrair_ui(pagina) or {}, extrair_ui)

        alvo = botao_aba
        for candidato in _filtrar_candidatos_abas(ui_base):
            if _texto_clicavel(candidato).lower() == nome_aba.lower():
                alvo = candidato
                break

        if not _clicar_botao(pagina, alvo):
            continue

        _aguardar_estabilizacao(pagina, extrair_ui)
        indice_aba += 1
        abas_visitadas.add(nome_aba.lower())
        slug = _slug_curto(nome_aba)
        cap = _salvar_captura(
            pagina,
            pasta_entrada,
            f"02-aba-{indice_aba:02d}-{slug}",
            extrair_ui,
            raiz,
        )
        resultado["capturas"][f"aba_{indice_aba}"] = {
            "nome": nome_aba,
            "screenshot": cap["screenshot"],
            "json": cap["json"],
        }
        resultado["passos"].append({"tipo": "aba", "nome": nome_aba})
        resultado["botoes_salvar_excluir_detectados"].extend(_coletar_perigosos(cap["ui"]))

    resultado["fases_concluidas"].append(f"abas:{indice_aba}")

    # --- Filtros ---
    _voltar_url_base(pagina, url, timeout_navegacao_ms, extrair_ui)
    ui_filtro_base = extrair_ui(pagina) or {}
    filtros = ui_filtro_base.get("botoes_filtro") or [
        b for b in (ui_filtro_base.get("botoes_classificados") or []) if b.get("classificacao") == "filtro"
    ]
    filtros_vistos: set[str] = set()
    indice_filtro = 0

    for botao_filtro in filtros:
        if indice_filtro >= _MAX_FILTROS:
            break
        rotulo = _texto_clicavel(botao_filtro).lower() or str(botao_filtro.get("indice_dom"))
        if rotulo in filtros_vistos:
            continue
        _voltar_url_base(pagina, url, timeout_navegacao_ms, extrair_ui)
        if not _clicar_botao_classificado(pagina, botao_filtro):
            continue
        _aguardar_estabilizacao(pagina, extrair_ui)
        indice_filtro += 1
        filtros_vistos.add(rotulo)
        cap = _salvar_captura(
            pagina,
            pasta_entrada,
            f"03-filtro-{indice_filtro:02d}-{_slug_curto(rotulo)}",
            extrair_ui,
            raiz,
        )
        resultado["capturas"][f"filtro_{indice_filtro}"] = {
            "botao": _texto_clicavel(botao_filtro),
            "screenshot": cap["screenshot"],
            "json": cap["json"],
        }
        resultado["passos"].append({"tipo": "filtro", "botao": _texto_clicavel(botao_filtro)})
        resultado["botoes_salvar_excluir_detectados"].extend(_coletar_perigosos(cap["ui"]))
        _fechar_formulario_ou_painel(pagina, cap["ui"], extrair_ui)

    resultado["fases_concluidas"].append(f"filtros:{indice_filtro}")

    # --- Formulário novo (Add abre form; fecha sem Salvar) ---
    _voltar_url_base(pagina, url, timeout_navegacao_ms, extrair_ui)
    ui_add = extrair_ui(pagina) or {}
    botoes_add = ui_add.get("botoes_abrir_formulario") or [
        b for b in (ui_add.get("botoes_classificados") or []) if b.get("classificacao") == "abrir_formulario_novo"
    ]
    if botoes_add and _clicar_botao(pagina, botoes_add[0]):
        _aguardar_estabilizacao(pagina, extrair_ui)
        cap_form = _salvar_captura(
            pagina,
            pasta_entrada,
            "04-formulario-novo-aberto",
            extrair_ui,
            raiz,
        )
        perigosos_form = _coletar_perigosos(cap_form["ui"])
        resultado["capturas"]["formulario_novo"] = {
            "botao": _texto_clicavel(botoes_add[0]),
            "screenshot": cap_form["screenshot"],
            "json": cap_form["json"],
            "salvar_excluir_no_formulario": perigosos_form,
        }
        resultado["passos"].append(
            {
                "tipo": "formulario_novo_aberto",
                "botao": _texto_clicavel(botoes_add[0]),
                "observacao": "Formulário aberto sem Salvar",
            }
        )
        resultado["botoes_salvar_excluir_detectados"].extend(perigosos_form)
        _fechar_formulario_ou_painel(pagina, cap_form["ui"], extrair_ui)
        resultado["fases_concluidas"].append("formulario_novo")
    else:
        resultado["fases_concluidas"].append("formulario_novo:nao_encontrado")

    _aguardar_estabilizacao(pagina, extrair_ui, 5000)
    resultado["leitura_concluida"] = True
    resultado["motivo_proximo_link"] = "fases esgotadas e UI estabilizada"
    (pasta_entrada / ".varredura-concluida").write_text(
        json.dumps({"fases": resultado.get("fases_concluidas", [])}, ensure_ascii=False),
        encoding="utf-8",
    )

    vistos: set[str] = set()
    unicos: list[dict] = []
    for botao in resultado["botoes_salvar_excluir_detectados"]:
        chave = f"{botao.get('classificacao')}::{_texto_clicavel(botao)}"
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(botao)
    resultado["botoes_salvar_excluir_detectados"] = unicos

    resultado["duracao_segundos"] = round(time.time() - inicio, 1)
    resultado["status"] = "ok"
    return resultado
