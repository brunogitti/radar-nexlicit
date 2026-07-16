"""
Testes do captura/filtro.py.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_filtro.py -v
"""

from datetime import datetime

import pytest

from captura.filtro import ErroConfiguracaoYAML, avaliar_edital, carregar_keywords
from captura.modelos import Edital

CONFIG_DE_TESTE = {
    "config": {
        "min_radical": 5,
        "campos_analisados": ["objetoCompra", "informacaoComplementar"],
    },
    "exclusoes_globais": [],
    "segmentos": [
        {
            "nome": "Limpeza",
            "regras": [
                {"termos": ["material", "limpeza"]},
                {"termos": ["alcool"], "excluir": ["alcool em gel hospitalar"]},
            ],
        },
        {
            "nome": "Informatica",
            "regras": [{"termos": ["notebook"]}],
        },
    ],
}


def _edital_de_teste(objeto, informacao_complementar=None):
    """Monta um Edital com valores fixos nos campos que o filtro nao usa,
    pra nao repetir os mesmos 9 argumentos em cada teste.
    """
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
        data_encerramento_proposta=datetime(2026, 12, 31),
        informacao_complementar=informacao_complementar,
    )


def test_bate_um_segmento():
    edital = _edital_de_teste("Aquisição de material de limpeza para escolas")
    matches = avaliar_edital(edital, CONFIG_DE_TESTE)

    assert matches == [{"segmento": "Limpeza", "termos": ["material", "limpeza"]}]


def test_bate_mais_de_um_segmento():
    edital = _edital_de_teste("Aquisição de material de limpeza e notebooks para escolas")
    matches = avaliar_edital(edital, CONFIG_DE_TESTE)

    nomes_dos_segmentos = {match["segmento"] for match in matches}
    assert nomes_dos_segmentos == {"Limpeza", "Informatica"}


def test_regra_com_exclusao_nao_bate_quando_termo_excluido_aparece():
    edital = _edital_de_teste("Aquisição de álcool em gel hospitalar")
    matches = avaliar_edital(edital, CONFIG_DE_TESTE)

    assert matches == []


def test_regra_com_exclusao_bate_quando_termo_excluido_nao_aparece():
    edital = _edital_de_teste("Aquisição de álcool 70")
    matches = avaliar_edital(edital, CONFIG_DE_TESTE)

    assert matches == [{"segmento": "Limpeza", "termos": ["alcool"]}]


def test_exclusao_global_derruba_o_edital_inteiro():
    config = {
        **CONFIG_DE_TESTE,
        "exclusoes_globais": ["ata de registro de precos cancelada"],
    }
    edital = _edital_de_teste(
        "Aquisição de material de limpeza. Ata de registro de preços cancelada."
    )

    assert avaliar_edital(edital, config) == []


def test_analisa_informacao_complementar_tambem():
    edital = _edital_de_teste(
        objeto="Aquisição de diversos materiais",
        informacao_complementar="Trata-se de compra de notebooks para o setor de TI",
    )
    matches = avaliar_edital(edital, CONFIG_DE_TESTE)

    assert matches == [{"segmento": "Informatica", "termos": ["notebook"]}]


def test_nada_bate_devolve_lista_vazia():
    edital = _edital_de_teste("Aquisição de gêneros alimentícios diversos")
    assert avaliar_edital(edital, CONFIG_DE_TESTE) == []


def test_carrega_o_keywords_yaml_real_sem_erro():
    config = carregar_keywords("config/keywords.yaml")
    assert "segmentos" in config
    assert len(config["segmentos"]) > 0


def test_erro_claro_quando_regra_nao_tem_termos(tmp_path):
    yaml_torto = """
config:
  min_radical: 5
  campos_analisados: [objetoCompra]
exclusoes_globais: []
segmentos:
  - nome: Limpeza
    regras:
      - excluir: [alcool em gel hospitalar]
"""
    arquivo = tmp_path / "keywords_torto.yaml"
    arquivo.write_text(yaml_torto, encoding="utf-8")

    with pytest.raises(ErroConfiguracaoYAML) as erro:
        carregar_keywords(str(arquivo))

    assert "Limpeza" in str(erro.value)
    assert "termos" in str(erro.value)


def test_erro_claro_quando_segmento_nao_tem_nome(tmp_path):
    yaml_torto = """
config:
  min_radical: 5
  campos_analisados: [objetoCompra]
exclusoes_globais: []
segmentos:
  - regras:
      - termos: [notebook]
"""
    arquivo = tmp_path / "keywords_torto.yaml"
    arquivo.write_text(yaml_torto, encoding="utf-8")

    with pytest.raises(ErroConfiguracaoYAML) as erro:
        carregar_keywords(str(arquivo))

    assert "nome" in str(erro.value)
