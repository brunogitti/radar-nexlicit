"""
Este modulo so monta o HTML do e-mail a partir de uma lista de editais ja
classificados (mesma lista que o main.py usa pra imprimir na tela). Nao
sabe enviar e-mail, so sabe montar o texto (quem envia e o
entrega/email_sender.py).
"""

import html
from collections import defaultdict

from captura.apresentacao import formatar_selo_me_epp, formatar_status, formatar_valor

COR_TEXTO = "#222222"
COR_BORDA = "#dddddd"


def _esc(valor):
    """Escapa caracteres especiais de HTML (<, >, &, etc) antes de colocar
    um texto vindo da API do PNCP dentro do HTML. Sem isso, um objeto de
    edital que por acaso contenha um "<" ou "&" poderia quebrar a
    formatacao do e-mail.
    """
    return html.escape(str(valor))


def _agrupar_por_segmento(editais_classificados):
    """Devolve um dict {nome_do_segmento: [(edital, status, linha_anterior, termos), ...]}.

    defaultdict(list) evita ter que escrever "se a chave ainda nao existe,
    cria uma lista vazia antes de usar": na primeira vez que uma chave
    nova e acessada, ele mesmo cria a lista vazia sozinho.

    Um edital que bate em mais de um segmento aparece em mais de um grupo,
    igual ao filtro.py permite (nao forcamos segmento unico).
    """
    grupos = defaultdict(list)
    for edital, status, linha_anterior in editais_classificados:
        for match in edital.segmentos:
            grupos[match["segmento"]].append((edital, status, linha_anterior, match["termos"]))
    return grupos


def _html_de_um_edital(edital, status, linha_anterior, termos):
    selo = formatar_selo_me_epp(edital.beneficios_itens)
    linha_selo = f'<p style="margin:4px 0;">Selo: {_esc(selo)}</p>' if selo else ""

    return f"""
    <div style="margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid {COR_BORDA};">
        <p style="margin:4px 0;"><strong>[{_esc(formatar_status(edital, status, linha_anterior))}]
            {_esc(edital.municipio)}/{_esc(edital.uf)} &mdash; {_esc(edital.orgao)}</strong></p>
        <p style="margin:4px 0;">Modalidade: {_esc(edital.modalidade)}</p>
        <p style="margin:4px 0;">Objeto: {_esc(edital.objeto)}</p>
        <p style="margin:4px 0;">Valor estimado: {_esc(formatar_valor(edital.valor_estimado))}</p>
        <p style="margin:4px 0;">Prazo da proposta: {edital.data_encerramento_proposta:%d/%m/%Y %Hh%M}</p>
        <p style="margin:4px 0;">Bateu em: {_esc(', '.join(termos))}</p>
        {linha_selo}
        <p style="margin:4px 0;"><a href="{_esc(edital.link_pncp)}">Ver no PNCP</a></p>
    </div>
    """


def montar_corpo_html(editais_classificados):
    """Monta o corpo do e-mail em HTML, agrupado por segmento.

    Estilo inline (style="..." em cada tag) em vez de uma tag <style>
    separada, porque varios clientes de e-mail (o proprio Gmail, em certos
    contextos) ignoram <style> e so respeitam estilo escrito direto na tag.
    """
    grupos = _agrupar_por_segmento(editais_classificados)

    blocos_html = []
    for segmento in sorted(grupos):
        itens_do_segmento = grupos[segmento]
        itens_html = "".join(
            _html_de_um_edital(edital, status, linha_anterior, termos)
            for edital, status, linha_anterior, termos in itens_do_segmento
        )
        blocos_html.append(f"""
        <h2 style="font-size:16px; border-bottom:1px solid {COR_BORDA}; padding-bottom:4px;">
            {_esc(segmento)} ({len(itens_do_segmento)})
        </h2>
        {itens_html}
        """)

    return f"""
    <html>
    <body style="font-family:Arial, Helvetica, sans-serif; color:{COR_TEXTO}; line-height:1.5;">
        <h1 style="font-size:20px;">Radar NexLicit</h1>
        <p>{len(editais_classificados)} edital(is) novo(s)/atualizado(s).</p>
        {''.join(blocos_html)}
    </body>
    </html>
    """
