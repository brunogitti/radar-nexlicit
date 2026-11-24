"""
Testes do entrega/resumo.py.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_resumo.py -v
"""

from datetime import datetime

from captura import banco
from captura.modelos import Edital
from entrega.resumo import montar_corpo_html


def _edital_de_teste(objeto="Aquisição de material de limpeza", segmentos=None, beneficios_itens=None):
    return Edital(
        numero_controle_pncp="00000000000000-1-000001/2026",
        cnpj_orgao="00000000000000",
        ano_compra=2026,
        sequencial_compra=1,
        orgao="Prefeitura de Teste",
        municipio="Votuporanga",
        uf="SP",
        codigo_ibge="3557105",
        modalidade="Pregão - Eletrônico",
        objeto=objeto,
        situacao="Divulgada no PNCP",
        data_encerramento_proposta=datetime(2026, 12, 31, 8, 0),
        valor_estimado=1000.0,
        beneficios_itens=beneficios_itens,
        segmentos=segmentos or [{"segmento": "Limpeza", "termos": ["material", "limpeza"]}],
    )


def test_um_segmento_aparece_com_o_edital(tmp_path=None):
    edital = _edital_de_teste()
    html = montar_corpo_html([(edital, "novo", None)])

    assert "Limpeza (1)" in html
    assert "Aquisição de material de limpeza" in html
    assert "[NOVO]" in html


def test_edital_com_dois_segmentos_aparece_nos_dois_blocos():
    edital = _edital_de_teste(segmentos=[
        {"segmento": "Limpeza", "termos": ["limpeza"]},
        {"segmento": "Informática", "termos": ["notebook"]},
    ])
    html = montar_corpo_html([(edital, "novo", None)])

    assert "Limpeza (1)" in html
    assert "Informática (1)" in html


def test_texto_com_caractere_especial_e_escapado():
    edital = _edital_de_teste(objeto="Aquisição de cabo <flexível> & conectores")
    html = montar_corpo_html([(edital, "novo", None)])

    assert "<flexível>" not in html
    assert "&lt;flexível&gt;" in html


def test_selo_aparece_quando_ha_beneficio_relevante():
    edital = _edital_de_teste(beneficios_itens=["Participação exclusiva para ME/EPP"])
    html = montar_corpo_html([(edital, "novo", None)])

    assert "Participação exclusiva para ME/EPP" in html


def test_selo_nao_aparece_quando_sem_beneficio():
    edital = _edital_de_teste(beneficios_itens=["Sem benefício"])
    html = montar_corpo_html([(edital, "novo", None)])

    assert "Selo:" not in html


def test_contagem_no_cabecalho_do_segmento():
    edital_a = _edital_de_teste(objeto="Objeto A")
    edital_b = _edital_de_teste(objeto="Objeto B")
    html = montar_corpo_html([(edital_a, "novo", None), (edital_b, "novo", None)])

    assert "Limpeza (2)" in html


def test_email_de_edital_que_voltou_de_suspensa_para_divulgada_diz_a_mudanca(tmp_path):
    # Caminho completo, sem atalho: o edital fica salvo como Suspensa (foi o
    # que a reconciliacao gravou), depois reaparece na lista como "Divulgada
    # no PNCP". O banco o classifica como atualizado e o e-mail tem que dizer
    # de onde para onde a situacao mudou.
    conexao = banco.conectar(str(tmp_path / "teste.db"))
    suspenso = _edital_de_teste()
    suspenso.situacao = "Suspensa"
    banco.salvar(conexao, [(suspenso, "novo", None)])

    voltou = _edital_de_teste()  # situacao "Divulgada no PNCP"
    classificados = banco.classificar(conexao, [voltou])
    assert classificados[0][1] == "atualizado"

    html = montar_corpo_html(classificados)

    # o texto passa por escape de HTML (as aspas simples viram &#x27;)
    assert "situação mudou de &#x27;Suspensa&#x27; para &#x27;Divulgada no PNCP&#x27;" in html
