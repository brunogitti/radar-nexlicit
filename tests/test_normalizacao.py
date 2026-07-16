"""
Testes do captura/normalizacao.py, com os casos que o Bruno definiu como
importantes na Tarefa 1.4.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_normalizacao.py -v
"""

from captura.normalizacao import normalizar_texto, termo_bate_no_texto


def test_maiuscula_bate_minuscula():
    assert termo_bate_no_texto("Limpeza", "limpeza")


def test_regra_composta_bate_em_ordem_diferente():
    # "material" e "limpeza" aparecem no texto, cada um em um lugar,
    # entao os dois termos da regra [material, limpeza] batem, um de cada vez
    texto = "AQUISIÇÃO DE MATERIAL DE LIMPEZA"
    assert termo_bate_no_texto("material", texto)
    assert termo_bate_no_texto("limpeza", texto)


def test_termo_curto_nao_bate_por_prefixo():
    # "cabo" tem 4 letras, menor que o min_radical padrao (5), entao exige
    # a palavra inteira. Nao pode bater dentro de "cabotagem".
    assert not termo_bate_no_texto("cabo", "servico de cabotagem")


def test_termo_curto_bate_a_palavra_inteira():
    assert termo_bate_no_texto("cabo", "aquisicao de cabo eletrico")


def test_termo_longo_bate_plural_por_prefixo():
    # "camiseta" tem 8 letras, maior que o min_radical padrao (5), entao
    # pode bater como prefixo de "camisetas" (plural)
    assert termo_bate_no_texto("camiseta", "confeccao de camisetas escolares")


def test_termo_que_nao_aparece_nao_bate():
    assert not termo_bate_no_texto("limpeza", "aquisicao de material de escritorio")


def test_termo_composto_exige_frase_exata():
    assert termo_bate_no_texto("agua sanitaria", "aquisicao de agua sanitaria")
    assert not termo_bate_no_texto("agua sanitaria", "agua para caixa sanitaria")


def test_normalizar_texto_remove_acento_e_pontuacao():
    assert normalizar_texto("Aquisição de Água, Sabão e Detergente!") == \
        "aquisicao de agua sabao e detergente"
