"""
Testes de trechos do main.py: gravacao dos itens dos editais e reconciliacao
dos editais que sumiram da lista (excluidos, suspensos...).

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


# ---------------------------------------------------------------------------
# reconciliar_editais_sumidos: o que acontece com edital que sumiu da lista
# ---------------------------------------------------------------------------

AGORA_DE_TESTE = datetime(2026, 11, 24, 10, 0)


def _salvar_edital_aberto(conexao, sequencial, situacao="Divulgada no PNCP"):
    """Grava no banco um edital aberto (prazo 10/12) com link_pncp de verdade,
    que e de onde a reconciliacao tira cnpj/ano/sequencial."""
    edital = _edital_de_teste(None, numero_controle_pncp=f"00000000000000-1-{sequencial:06d}/2026")
    edital.link_pncp = f"https://pncp.gov.br/app/editais/00000000000000/2026/{sequencial}"
    edital.situacao = situacao
    edital.data_encerramento_proposta = datetime(2026, 12, 10, 9, 0)
    banco.salvar(conexao, [(edital, "novo", None)])
    return edital


def _preparar_reconciliacao(monkeypatch, respostas_por_sequencial):
    """Troca o relogio, a pausa e a consulta ao PNCP por versoes falsas.
    Devolve a lista de sequenciais consultados, na ordem."""
    consultados = []

    def consultar_falso(cnpj, ano, sequencial):
        consultados.append(sequencial)
        return respostas_por_sequencial[sequencial]

    monkeypatch.setattr(main, "agora_em_brasilia", lambda: AGORA_DE_TESTE)
    monkeypatch.setattr(main.time, "sleep", lambda segundos: None)
    monkeypatch.setattr(main.pncp_client, "consultar_compra", consultar_falso)
    return consultados


def test_reconciliacao_marca_como_excluido_quando_o_pncp_responde_410(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 218)
    _preparar_reconciliacao(monkeypatch, {218: {"excluida": True}})

    resumo = main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert resumo["excluidos"] == 1
    assert banco.consultar_historico(conexao) == []
    assert len(banco.consultar_historico(conexao, incluir_excluidos=True)) == 1


def test_reconciliacao_grava_a_situacao_nova_de_edital_suspenso(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 68)
    _preparar_reconciliacao(monkeypatch, {68: {"excluida": False, "situacao_id": 4, "situacao_nome": "Suspensa"}})

    resumo = main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert resumo["situacao_mudou"] == 1
    linha = banco.consultar_historico(conexao)[0]
    assert linha["situacao"] == "Suspensa"
    assert linha["excluido_em"] is None


def test_reconciliacao_nao_mexe_em_edital_que_continua_divulgado(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 1)
    divulgada = {"excluida": False, "situacao_id": 1, "situacao_nome": "Divulgada no PNCP"}
    _preparar_reconciliacao(monkeypatch, {1: divulgada})

    resumo = main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert resumo["sem_mudanca"] == 1
    assert banco.consultar_historico(conexao)[0]["situacao"] == "Divulgada no PNCP"


def test_reconciliacao_com_falha_ao_consultar_nao_mexe_em_nada(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 1)
    _preparar_reconciliacao(monkeypatch, {1: None})

    resumo = main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert resumo["falhas"] == 1
    linha = banco.consultar_historico(conexao)[0]
    assert linha["situacao"] == "Divulgada no PNCP"
    assert linha["excluido_em"] is None


def test_reconciliacao_so_consulta_quem_nao_veio_na_lista(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    veio_na_lista = _salvar_edital_aberto(conexao, 1)
    _salvar_edital_aberto(conexao, 2)
    consultados = _preparar_reconciliacao(
        monkeypatch, {2: {"excluida": False, "situacao_id": 1, "situacao_nome": "Divulgada no PNCP"}}
    )

    main.reconciliar_editais_sumidos(conexao, [veio_na_lista], dias=30)

    assert consultados == [2]


def test_reconciliacao_sem_nenhum_sumido_nao_faz_chamada(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    veio_na_lista = _salvar_edital_aberto(conexao, 1)
    consultados = _preparar_reconciliacao(monkeypatch, {})

    resumo = main.reconciliar_editais_sumidos(conexao, [veio_na_lista], dias=30)

    assert consultados == []
    assert resumo["consultados"] == 0


def test_reconciliacao_ignora_edital_com_prazo_alem_da_janela_de_dias(tmp_path, monkeypatch):
    # prazo 10/12 com janela de 5 dias (ate 29/11): nao poderia estar na lista
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 1)
    consultados = _preparar_reconciliacao(monkeypatch, {})

    main.reconciliar_editais_sumidos(conexao, [], dias=5)

    assert consultados == []


def test_reconciliacao_nao_consulta_de_novo_edital_ja_excluido(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    edital = _salvar_edital_aberto(conexao, 218)
    banco.marcar_excluido(conexao, edital.numero_controle_pncp, datetime(2026, 11, 23, 12, 0))
    consultados = _preparar_reconciliacao(monkeypatch, {})

    main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert consultados == []


def test_reconciliacao_usa_cnpj_ano_e_sequencial_do_link_salvo(tmp_path, monkeypatch):
    conexao = _banco_de_teste(tmp_path)
    _salvar_edital_aberto(conexao, 359)
    chamadas = []

    def consultar_falso(cnpj, ano, sequencial):
        chamadas.append((cnpj, ano, sequencial))
        return {"excluida": True}

    monkeypatch.setattr(main, "agora_em_brasilia", lambda: AGORA_DE_TESTE)
    monkeypatch.setattr(main.pncp_client, "consultar_compra", consultar_falso)

    main.reconciliar_editais_sumidos(conexao, [], dias=30)

    assert chamadas == [("00000000000000", 2026, 359)]
