"""
Testes do captura/modelos.py.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_modelos.py -v
"""

from datetime import datetime

from captura.modelos import Edital


def _edital_de_teste(**sobrescreve):
    campos = dict(
        numero_controle_pncp="00000000000000-1-000001/2026",
        cnpj_orgao="00000000000000",
        ano_compra=2026,
        sequencial_compra=1,
        orgao="Prefeitura de Teste",
        municipio="Votuporanga",
        uf="SP",
        codigo_ibge="3557105",
        modalidade="Pregão - Eletrônico",
        objeto="Aquisição de material de limpeza",
        situacao="Divulgada no PNCP",
        data_encerramento_proposta=datetime(2026, 12, 31, 8, 0),
    )
    campos.update(sobrescreve)
    return Edital(**campos)


def test_campos_opcionais_tem_valor_padrao_none():
    edital = _edital_de_teste()

    assert edital.informacao_complementar is None
    assert edital.valor_estimado is None
    assert edital.link_sistema_origem is None
    assert edital.link_pncp is None
    assert edital.beneficios_itens is None
    assert edital.itens is None


def test_segmentos_comeca_como_lista_vazia():
    assert _edital_de_teste().segmentos == []


def test_segmentos_de_dois_editais_nao_compartilham_a_mesma_lista():
    # field(default_factory=list) existe justamente pra evitar isso: sem
    # ele, todo Edital criado sem informar segmentos compartilharia a
    # MESMA lista por baixo dos panos, e alterar o segmento de um
    # vazaria pros outros. Esse teste trava esse comportamento.
    edital_a = _edital_de_teste()
    edital_b = _edital_de_teste()

    edital_a.segmentos.append({"segmento": "Limpeza", "termos": ["limpeza"]})

    assert edital_a.segmentos == [{"segmento": "Limpeza", "termos": ["limpeza"]}]
    assert edital_b.segmentos == []
