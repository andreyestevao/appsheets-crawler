/**
 * Executado no contexto da página AppSheet via page.evaluate.
 * Coleta UI visível e classifica botões conforme padrões AppSheet.
 */
() => {
  const textoPagina = (document.body && document.body.innerText) || "";
  const urlAtual = window.location.href;

  const emLogin =
    urlAtual.includes("/Account/Login") ||
    /sign in with/i.test(textoPagina) ||
    /entrar com/i.test(textoPagina);

  const seletorTexto = (seletor) =>
    [...document.querySelectorAll(seletor)]
      .map((el) => (el.innerText || el.textContent || "").trim())
      .filter((t) => t.length > 0 && t.length < 200);

  const seletorAria = (seletor) =>
    [...document.querySelectorAll(seletor)]
      .map((el) => (el.getAttribute("aria-label") || "").trim())
      .filter(Boolean);

  /**
   * Classifica botão AppSheet: salvar/excluir (persistência), abrir_formulario_novo (+),
   * filtro, cancelar, aba_view ou outro.
   */
  const classificarBotao = (textoBruto, ariaBruto) => {
    const texto = ((textoBruto || "") + " " + (ariaBruto || "")).toLowerCase().trim();
    if (!texto) {
      return "desconhecido";
    }
    if (/\b(delete|excluir|remover|apagar|trash|lixeira)\b/.test(texto)) {
      return "excluir";
    }
    if (/\b(save|salvar|guardar)\b/.test(texto) && !/\b(excluir|delete)\b/.test(texto)) {
      return "salvar";
    }
    if (
      texto === "+" ||
      /^\+/.test(textoBruto.trim()) ||
      /\b(add|new|novo|adicionar|criar|incluir|insert)\b/.test(texto)
    ) {
      return "abrir_formulario_novo";
    }
    if (/\b(cancel|cancelar|voltar|back|fechar|close|descartar|discard)\b/.test(texto)) {
      return "cancelar";
    }
    if (/\b(filter|filtro|filtrar|refinar|buscar|search|procurar)\b/.test(texto)) {
      return "filtro";
    }
    if (/\b(view|lista|list|deck|card|cards|table|tabela|map|mapa|calendar|calend[aá]rio|gallery|galeria|chart|gr[aá]fico)\b/.test(texto)) {
      return "aba_view";
    }
    return "outro";
  };

  const elementosClique = [
    ...document.querySelectorAll("button, [role='button'], [role='tab'], nav a, nav button"),
  ];

  const botoesClassificados = elementosClique
    .map((el, indice) => {
      const texto = (el.innerText || el.textContent || "").trim().slice(0, 120);
      const aria = (el.getAttribute("aria-label") || "").trim().slice(0, 120);
      const retangulo = el.getBoundingClientRect();
      const visivel =
        retangulo.width > 0 &&
        retangulo.height > 0 &&
        window.getComputedStyle(el).visibility !== "hidden" &&
        window.getComputedStyle(el).display !== "none";
      return {
        indice_dom: indice,
        texto,
        aria_label: aria,
        classificacao: classificarBotao(texto, aria),
        visivel,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
      };
    })
    .filter((b) => b.visivel && (b.texto || b.aria_label));

  const linksMenu = [...document.querySelectorAll("a[href]")]
    .map((a) => ({
      texto: (a.innerText || "").trim().slice(0, 120),
      href: a.getAttribute("href") || "",
    }))
    .filter((l) => l.texto.length > 0)
    .slice(0, 80);

  const campos = [...document.querySelectorAll("input, textarea, select")]
    .map((el) => ({
      tag: el.tagName.toLowerCase(),
      tipo: el.getAttribute("type") || "",
      nome: el.getAttribute("name") || "",
      placeholder: el.getAttribute("placeholder") || "",
      ariaLabel: el.getAttribute("aria-label") || "",
      id: el.id || "",
    }))
    .filter((c) => c.nome || c.placeholder || c.ariaLabel || c.id)
    .slice(0, 120);

  const perigosos = botoesClassificados.filter((b) =>
    ["salvar", "excluir"].includes(b.classificacao),
  );
  const abrirFormulario = botoesClassificados.filter(
    (b) => b.classificacao === "abrir_formulario_novo",
  );
  const filtros = botoesClassificados.filter((b) => b.classificacao === "filtro");
  const abasViews = [
    ...new Set([
      ...botoesClassificados
        .filter((b) => b.classificacao === "aba_view")
        .map((b) => b.texto || b.aria_label),
      ...seletorTexto("[role='tab'], nav a, nav button"),
    ]),
  ].filter(Boolean);

  return {
    url: urlAtual,
    titulo: document.title,
    em_login: emLogin,
    cabecalhos: seletorTexto("h1, h2, h3, h4, h5, [role='heading']"),
    itens_navegacao: [
      ...new Set([
        ...seletorTexto("nav a, nav button, [role='tab'], [role='menuitem'], [role='link']"),
        ...seletorAria("[role='tab'], [role='menuitem'], button"),
      ]),
    ].slice(0, 60),
    rotulos: [...new Set(seletorTexto("label"))].slice(0, 80),
    botoes: [...new Set(seletorTexto("button"))].slice(0, 40),
    botoes_classificados: botoesClassificados.slice(0, 80),
    botoes_salvar_excluir: perigosos,
    botoes_abrir_formulario: abrirFormulario,
    botoes_filtro: filtros,
    candidatos_abas: abasViews.slice(0, 20),
    campos_formulario: campos,
    links_visiveis: linksMenu,
    trecho_texto: textoPagina.replace(/\s+/g, " ").trim().slice(0, 2500),
  };
}
