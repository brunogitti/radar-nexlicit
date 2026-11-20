"""
Testes do trecho de main.py que grava os itens dos editais.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_main.py -v
"""

from datetime import datetime

import main
from captura import banco
from captura.modelos import Edital


def _edital_de_teste(itens, numero_controle_pncp="00000000000000-1-000001/2026"):
    edital = Edital(
        numero_controle_pncp=numero_controle_pncp,
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
        valor_estimado=1000.0,
        segmentos=[{"segmento": "Limpeza", "termos": ["material", "limpeza"]}],
    )
    edital.itens = itens
    return edital


def _itens_de_teste(quantidade):
    return [
        {"numero_item": numero, "descricao": f"Item {numero}", "material_ou_servico": "Material",
         "quantidade": 1, "valor_unitario_estimado": 1.0, "valor_total": 1.0, "tipo_beneficio": None}
        for numero in range(1, quantidade + 1)
    ]


def _banco_de_teste(tmp_path):
    return banco.conectar(str(tmp_path / "teste.db"))


def test_sem_mudanca_sem_itens_salvos_e_busca_ok_grava(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste(_itens_de_teste(3))

    main.salvar_itens_dos_editais(conexao, [(edital, "sem_mudanca", {})])

    assert len(banco.consultar_itens_do_edital(conexao, edital.numero_controle_pncp)) == 3


def test_sem_mudanca_sem_itens_salvos_e_busca_none_nao_grava(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste(None)

    main.salvar_itens_dos_editais(conexao, [(edital, "sem_mudanca", {})])

    assert banco.consultar_itens_do_edital(conexao, edital.numero_controle_pncp) == []


def test_sem_mudanca_com_busca_lista_vazia_nao_grava(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste([])

    main.salvar_itens_dos_editais(conexao, [(edital, "sem_mudanca", {})])

    assert banco.consultar_itens_do_edital(conexao, edital.numero_controle_pncp) == []


def test_sem_mudanca_que_ja_tem_itens_nao_e_regravado(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    numero = "00000000000000-1-000001/2026"
    banco.salvar_itens(conexao, numero, _itens_de_teste(2))
    edital = _edital_de_teste(_itens_de_teste(5))

    main.salvar_itens_dos_editais(conexao, [(edital, "sem_mudanca", {})])

    assert len(banco.consultar_itens_do_edital(conexao, numero)) == 2


def test_novo_continua_gravando_os_itens(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste(_itens_de_teste(4))

    main.salvar_itens_dos_editais(conexao, [(edital, "novo", None)])

    assert len(banco.consultar_itens_do_edital(conexao, edital.numero_controle_pncp)) == 4


def test_atualizado_regrava_mesmo_com_itens_ja_salvos(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    numero = "00000000000000-1-000001/2026"
    banco.salvar_itens(conexao, numero, _itens_de_teste(2))
    edital = _edital_de_teste(_itens_de_teste(5))

    main.salvar_itens_dos_editais(conexao, [(edital, "atualizado", {})])

    assert len(banco.consultar_itens_do_edital(conexao, numero)) == 5
