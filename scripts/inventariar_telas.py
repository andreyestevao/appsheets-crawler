#!/usr/bin/env python3
"""
Inventário de telas AppSheet autenticadas via browser (Playwright).

Objetivo: ler views/navegação na UI — sem alterar dados no AppSheet.

Política somente leitura:
  - Varredura ~30s por link: abas, filtros, formulário novo (sem Salvar).
  - Cataloga botões Salvar/Excluir sem clicar.
  - Bloqueio HTTP e clique DOM em Salvar/Excluir.

Uso típico:
  ./inventariar-telas.sh --login          # 1ª vez: abrir browser e autenticar Google
  ./inventariar-telas.sh                  # percorrer todos os links do markdown
  ./inventariar-telas.sh --app atividadesEcompras

Sessão Google persiste em credentials/browser-appsheet-profile/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
sys.path.insert(0, str(SCRIPTS))

from parse_links import EntradaLink, parsear_markdown  # noqa: E402
from varredura_tela import varrer_tela  # noqa: E402

DOCUMENTO_PADRAO = Path("/home/andrey/Documentos/CEI/Link das aplicações.md")
PERFIL_BROWSER = RAIZ / "credentials" / "browser-appsheet-profile"
SCRIPT_EXTRACAO = SCRIPTS / "extrair_ui_appsheet.js"
PASTA_SAIDA = RAIZ / "saida" / "telas"
URL_LOGIN_TESTE = "https://www.appsheet.com/start/20e23b05-a740-497c-800e-9434b92e4f6e"

# Ações AppSheet API que alteram dados — bloqueadas durante inventário.
_ACOES_ESCRITA_API = ('"Action":"Add"', '"Action": "Add"', '"Action":"Edit"', '"Action": "Edit"', '"Action":"Delete"', '"Action": "Delete"')
_METODOS_ESCRITA_HTTP = frozenset({"PUT", "PATCH", "DELETE"})


def _slug(texto: str, max_len: int = 48) -> str:
    """Gera nome de pasta seguro a partir de título/view."""
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "-", texto.strip().lower())
    limpo = re.sub(r"-+", "-", limpo).strip("-")
    return (limpo or "sem-nome")[:max_len]


def _carregar_extrator_js() -> str:
    return SCRIPT_EXTRACAO.read_text(encoding="utf-8")


def _aguardar_carregamento(pagina, timeout_ms: int) -> None:
    """Espera carregamento inicial (varredura usa orçamento próprio por link)."""
    try:
        pagina.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 15000))
    except Exception:
        pass
    pagina.wait_for_timeout(800)


def _extrair_ui(pagina) -> dict | None:
    """Executa script JS na página e retorna estrutura da tela."""
    try:
        return pagina.evaluate(_carregar_extrator_js())
    except Exception:
        return None


def _verificar_sessao(pagina, timeout_ms: int) -> bool:
    """
    Abre URL de teste e retorna True se já autenticado (fora da tela de login).
    """
    try:
        pagina.goto(URL_LOGIN_TESTE, wait_until="domcontentloaded", timeout=timeout_ms)
        _aguardar_carregamento(pagina, min(timeout_ms, 45000))
        ui = _extrair_ui(pagina)
        if not ui:
            return False
        return not ui.get("em_login", True)
    except Exception:
        return False


def _requisicao_tenta_escrita(requisicao) -> bool:
    """
    Indica se a requisição HTTP provavelmente altera dados no AppSheet.

    POST com Action Find permanece permitido (leitura via API interna do app).
    """
    if requisicao.method in _METODOS_ESCRITA_HTTP:
        return True
    if requisicao.method != "POST":
        return False
    corpo = requisicao.post_data or ""
    return any(token in corpo for token in _ACOES_ESCRITA_API)


def _handler_rota_somente_leitura(rota) -> None:
    """Aborta requisições de escrita; demais seguem normalmente."""
    requisicao = rota.request
    if _requisicao_tenta_escrita(requisicao):
        print(f"  [bloqueado escrita] {requisicao.method} {requisicao.url[:100]}")
        rota.abort("blockedbyclient")
        return
    rota.continue_()


def configurar_somente_leitura(contexto) -> None:
    """
    Aplica bloqueio de escrita em todas as páginas do contexto Playwright.

    Efeito colateral: impede Add/Edit/Delete acionados pela UI durante a sessão.
    """
    contexto.route("**/*", _handler_rota_somente_leitura)
    contexto.add_init_script(
        """
        () => {
          const bloquearTexto = (texto) => {
            const t = (texto || '').toLowerCase();
            return /\\b(save|salvar|guardar|delete|excluir|remover|apagar)\\b/.test(t);
          };
          document.addEventListener('click', (evento) => {
            const alvo = evento.target.closest('button, [role="button"], a');
            if (!alvo) return;
            const rotulo = (alvo.innerText || '') + ' ' + (alvo.getAttribute('aria-label') || '');
            if (bloquearTexto(rotulo)) {
              evento.preventDefault();
              evento.stopPropagation();
            }
          }, true);
          document.addEventListener('submit', (evento) => {
            evento.preventDefault();
            evento.stopPropagation();
          }, true);
        }
        """
    )


def _filtrar_entradas(
    entradas: list[EntradaLink],
    app_filtro: str | None,
    limite: int | None,
    somente_appsheet: bool,
) -> list[EntradaLink]:
    resultado = entradas
    if somente_appsheet:
        resultado = [e for e in resultado if e.tipo == "appsheet"]
    if app_filtro:
        filtro = app_filtro.lower()
        resultado = [
            e
            for e in resultado
            if e.app_name and filtro in e.app_name.lower()
        ]
    if limite is not None:
        resultado = resultado[:limite]
    return resultado


def _pagina_autenticada(pagina) -> bool:
    """Verifica autenticação na URL atual, sem navegar (seguro durante OAuth)."""
    try:
        if "/Account/Login" in (pagina.url or ""):
            return False
        ui = _extrair_ui(pagina)
        if not ui:
            return False
        return not ui.get("em_login", True)
    except Exception:
        return False


def modo_login(perfil: Path, timeout_ms: int, aguardar_autenticacao_s: int | None) -> int:
    """
    Abre browser visível para login Google manual; sessão fica no perfil persistente.

    Se aguardar_autenticacao_s > 0, detecta login automaticamente (sem Enter no terminal).
    """
    from playwright.sync_api import sync_playwright

    perfil.mkdir(parents=True, exist_ok=True)
    print("Abrindo browser para login Google AppSheet...")
    print(f"Perfil persistente: {perfil}")
    print("")
    print("1. Clique em Google e conclua o login.")
    print("2. Aguarde carregar qualquer app (não pare na tela de login).")
    if aguardar_autenticacao_s:
        print(f"3. Aguardando até {aguardar_autenticacao_s}s detectar sessão autenticada...")
    else:
        print("3. Feche a janela do browser OU pressione Enter aqui no terminal.")
    print("")

    with sync_playwright() as playwright:
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(perfil),
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        pagina.goto(URL_LOGIN_TESTE, wait_until="domcontentloaded", timeout=timeout_ms)

        autenticado = False
        if aguardar_autenticacao_s and aguardar_autenticacao_s > 0:
            limite = time.time() + aguardar_autenticacao_s
            while time.time() < limite:
                if _pagina_autenticada(pagina):
                    autenticado = True
                    print("Sessão autenticada detectada.")
                    break
                time.sleep(3)
            if not autenticado:
                print(
                    f"Tempo esgotado ({aguardar_autenticacao_s}s). Rode --login novamente.",
                    file=sys.stderr,
                )
                contexto.close()
                return 2
        else:
            try:
                input("Pressione Enter após autenticar... ")
            except KeyboardInterrupt:
                print("\nInterrompido.")
        contexto.close()

    print("Sessão salva. Execute: ./inventariar-telas.sh")
    return 0


def _persistir_relatorio(relatorio: dict, sessao: Path, pasta_saida: Path) -> None:
    """Grava JSON e resumo após cada link (checkpoint) e ao final."""
    caminho_json = sessao / "inventario-telas.json"
    caminho_json.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    ultimo = pasta_saida / "inventario-telas-latest.json"
    ultimo.write_text(caminho_json.read_text(encoding="utf-8"), encoding="utf-8")
    resumo = _montar_resumo_markdown(relatorio, sessao)
    (sessao / "resumo-sessao.md").write_text(resumo, encoding="utf-8")
    (pasta_saida / "resumo-sessao-latest.md").write_text(resumo, encoding="utf-8")


def inventariar(
    documento: Path,
    perfil: Path,
    pasta_saida: Path,
    app_filtro: str | None,
    limite: int | None,
    timeout_ms: int,
    headless: bool,
    sessao_existente: Path | None = None,
    pular_existentes: bool = False,
) -> int:
    """
    Percorre links do markdown com varredura completa por link.

    Sem limite de tempo: avança quando abas, filtros e form novo foram explorados
    e a UI estabilizou.
    """
    from playwright.sync_api import sync_playwright

    if not documento.is_file():
        print(f"Documento não encontrado: {documento}", file=sys.stderr)
        return 1

    entradas = _filtrar_entradas(
        parsear_markdown(documento),
        app_filtro=app_filtro,
        limite=limite,
        somente_appsheet=True,
    )
    if not entradas:
        print("Nenhuma entrada AppSheet para inventariar.", file=sys.stderr)
        return 1

    if sessao_existente:
        sessao = sessao_existente.resolve()
        if not sessao.is_dir():
            print(f"Sessão não encontrada: {sessao}", file=sys.stderr)
            return 1
        timestamp = sessao.name
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sessao = pasta_saida / timestamp
        sessao.mkdir(parents=True, exist_ok=True)
    perfil.mkdir(parents=True, exist_ok=True)

    caminho_json_sessao = sessao / "inventario-telas.json"
    if caminho_json_sessao.is_file():
        relatorio = json.loads(caminho_json_sessao.read_text(encoding="utf-8"))
        relatorio["total_links"] = len(entradas)
    else:
        relatorio = {
            "gerado_em": timestamp,
            "documento_origem": str(documento),
            "modo": "varredura_ate_estabilizar",
            "politica": {
                "alterar_registros": False,
                "cliques_permitidos": ["aba_view", "filtro", "abrir_formulario_novo", "cancelar"],
                "cliques_proibidos": ["salvar", "excluir"],
                "bloqueio_http_escrita": True,
                "bloqueio_dom_salvar_excluir": True,
            },
            "total_links": len(entradas),
            "telas": [],
            "login_pendente": [],
            "erros": [],
        }

    indices_ja_ok = {t["indice"] for t in relatorio.get("telas", []) if t.get("status") == "ok"}

    print(f"Sessão: {sessao}")
    print(f"Links AppSheet: {len(entradas)}")
    print(f"Modo: varredura até estabilizar | abas/filtros/form novo | sem Salvar/Excluir")

    with sync_playwright() as playwright:
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(perfil),
            headless=headless,
            viewport={"width": 1400, "height": 900},
        )
        configurar_somente_leitura(contexto)
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if not _verificar_sessao(pagina, timeout_ms):
            contexto.close()
            print(
                "\nSessão não autenticada. Execute primeiro:\n"
                "  ./inventariar-telas.sh --login\n",
                file=sys.stderr,
            )
            return 2

        for indice, entrada in enumerate(entradas, start=1):
            titulo_curto = entrada.titulo[:60]
            print(f"[{indice}/{len(entradas)}] {titulo_curto}...")

            pasta_entrada = sessao / _slug(entrada.app_name or "app") / f"{indice:02d}-{_slug(entrada.view or entrada.titulo)}"
            pasta_entrada.mkdir(parents=True, exist_ok=True)

            ja_capturado = (pasta_entrada / ".varredura-concluida").is_file() or (
                (pasta_entrada / "01-inicial.png").is_file()
                and (
                    (pasta_entrada / "04-formulario-novo-aberto.png").is_file()
                    or any(pasta_entrada.glob("02-aba-*"))
                )
            )
            if pular_existentes and ja_capturado:
                if indice in indices_ja_ok:
                    print("  — já capturado (pulado)")
                    continue
                registro_pulado = {
                    "indice": indice,
                    "titulo": entrada.titulo,
                    "url": entrada.url,
                    "app_name": entrada.app_name,
                    "view": entrada.view,
                    "table": entrada.table,
                    "status": "ok",
                    "pulado": True,
                    "pasta_capturas": str(pasta_entrada.relative_to(RAIZ)),
                }
                relatorio["telas"].append(registro_pulado)
                indices_ja_ok.add(indice)
                _persistir_relatorio(relatorio, sessao, pasta_saida)
                print("  — capturas existentes registradas (pulado)")
                continue

            registro = {
                "indice": indice,
                "titulo": entrada.titulo,
                "url": entrada.url,
                "app_name": entrada.app_name,
                "view": entrada.view,
                "table": entrada.table,
                "observacao_documento": entrada.observacao,
                "capturas": {},
            }

            try:
                varredura = varrer_tela(
                    pagina=pagina,
                    pasta_entrada=pasta_entrada,
                    extrair_ui=_extrair_ui,
                    raiz=RAIZ,
                    timeout_navegacao_ms=timeout_ms,
                    url=entrada.url,
                )

                if varredura.get("status") == "login_necessario":
                    registro["status"] = "login_necessario"
                    relatorio["login_pendente"].append(registro)
                    print("  ! Ainda na tela de login")
                    continue

                registro["varredura"] = varredura
                registro["capturas"] = varredura.get("capturas", {})
                registro["botoes_salvar_excluir"] = varredura.get(
                    "botoes_salvar_excluir_detectados", []
                )
                registro["passos"] = varredura.get("passos", [])
                registro["ui_inicial"] = varredura.get("ui_inicial")
                registro["duracao_segundos"] = varredura.get("duracao_segundos")
                registro["status"] = "ok"
                relatorio["telas"].append(registro)

                n_passos = len(registro["passos"])
                n_perigosos = len(registro["botoes_salvar_excluir"])
                duracao = registro.get("duracao_segundos", "?")
                print(
                    f"  ok — {n_passos} passo(s), {n_perigosos} Salvar/Excluir catalogado(s), "
                    f"{duracao}s, leitura concluída",
                    flush=True,
                )
                _persistir_relatorio(relatorio, sessao, pasta_saida)

            except Exception as exc:  # noqa: BLE001 — inventário registra falha por link
                registro["status"] = "erro"
                registro["erro"] = str(exc)
                relatorio["erros"].append(registro)
                print(f"  ! Erro: {exc}", flush=True)
                _persistir_relatorio(relatorio, sessao, pasta_saida)

            time.sleep(0.3)

        contexto.close()

    caminho_json = sessao / "inventario-telas.json"
    _persistir_relatorio(relatorio, sessao, pasta_saida)

    print("")
    print(f"JSON:    {caminho_json}")
    print(f"Resumo:  {sessao / 'resumo-sessao.md'}")
    print(f"OK: {len(relatorio['telas'])} | Login: {len(relatorio['login_pendente'])} | Erros: {len(relatorio['erros'])}")
    return 0 if not relatorio["login_pendente"] else 2


def _montar_resumo_markdown(relatorio: dict, sessao: Path) -> str:
    """Resumo legível para revisão humana e para o agente Cursor."""
    linhas = [
        "# Inventário de telas AppSheet",
        "",
        f"- Gerado em: `{relatorio['gerado_em']}`",
        f"- Pasta: `{sessao}`",
        f"- Links processados: {relatorio['total_links']}",
        f"- Política: `{relatorio.get('modo', 'somente_leitura')}`",
        "",
        "## Telas capturadas",
        "",
    ]
    for tela in relatorio.get("telas", []):
        linhas.append(f"### {tela['indice']}. {tela['titulo']}")
        linhas.append(f"- App: `{tela.get('app_name')}` | View: `{tela.get('view')}` | Table: `{tela.get('table')}`")
        if tela.get("duracao_segundos"):
            linhas.append(f"- Duração: {tela['duracao_segundos']}s | leitura_concluida: sim")
        if tela.get("observacao_documento"):
            linhas.append(f"- Nota doc: {tela['observacao_documento']}")
        for passo in tela.get("passos") or []:
            linhas.append(f"- Passo: `{passo.get('tipo')}` — {passo.get('nome') or passo.get('botao') or passo.get('observacao', '')}")
        perigosos = tela.get("botoes_salvar_excluir") or []
        if perigosos:
            rotulos = [
                f"{b.get('classificacao')}:{b.get('texto') or b.get('aria_label')}"
                for b in perigosos[:8]
            ]
            linhas.append(f"- Salvar/Excluir (detectados, não clicados): {', '.join(rotulos)}")
        if tela.get("capturas"):
            linhas.append(f"- Capturas: {len(tela['capturas'])} arquivo(s)")
        linhas.append("")

    if relatorio.get("login_pendente"):
        linhas.extend(["## Login pendente", ""])
        for item in relatorio["login_pendente"]:
            linhas.append(f"- {item['titulo']} — {item['url']}")

    if relatorio.get("erros"):
        linhas.extend(["", "## Erros", ""])
        for item in relatorio["erros"]:
            linhas.append(f"- {item['titulo']}: {item.get('erro')}")

    linhas.append("")
    linhas.append("_Peça ao agente Cursor: analise `saida/telas/inventario-telas-latest.json` e screenshots da pasta da sessão._")
    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventário de telas AppSheet autenticadas.")
    parser.add_argument(
        "--documento",
        type=Path,
        default=DOCUMENTO_PADRAO,
        help="Markdown com links (padrão: Link das aplicações.md)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Abre browser só para autenticar Google (primeira vez ou sessão expirada)",
    )
    parser.add_argument(
        "--aguardar-autenticacao",
        type=int,
        metavar="SEGUNDOS",
        default=60,
        help="Com --login: aguarda sessão autenticada sem Enter (padrão 60s)",
    )
    parser.add_argument(
        "--app",
        help="Filtra por trecho do appName (ex.: atividadesEcompras)",
    )
    parser.add_argument(
        "--limite",
        type=int,
        help="Processa apenas os N primeiros links (teste)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Browser invisível (use só se sessão já estiver válida)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20000,
        help="Timeout de navegação por goto em ms (padrão 20000)",
    )
    parser.add_argument(
        "--perfil",
        type=Path,
        default=PERFIL_BROWSER,
        help="Pasta do perfil Chromium persistente",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=PASTA_SAIDA,
        help="Pasta base de saída",
    )
    parser.add_argument(
        "--sessao",
        type=Path,
        help="Retoma/grava em pasta de sessão existente (ex.: saida/telas/20260608T193524Z)",
    )
    parser.add_argument(
        "--pular-existentes",
        action="store_true",
        help="Com --sessao: não re-varre links que já têm 01-inicial.png",
    )
    args = parser.parse_args()

    if args.login:
        return modo_login(args.perfil, args.timeout, args.aguardar_autenticacao if args.aguardar_autenticacao else None)

    return inventariar(
        documento=args.documento,
        perfil=args.perfil,
        pasta_saida=args.saida,
        app_filtro=args.app,
        limite=args.limite,
        timeout_ms=args.timeout,
        headless=args.headless,
        sessao_existente=args.sessao,
        pular_existentes=args.pular_existentes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
