"""
Testes do captura/banco.py.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_banco.py -v
"""

from datetime import datetime, timedelta

from captura import banco
from captura.modelos import Edital


def _edital_de_teste(numero_controle_pncp="00000000000000-1-000001/2026", prazo=None):
    return Edital(
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
        data_encerramento_proposta=prazo or datetime(2026, 12, 31, 8, 0),
        valor_estimado=1000.0,
        segmentos=[{"segmento": "Limpeza", "termos": ["material", "limpeza"]}],
    )


def _banco_de_teste(tmp_path):
    return banco.conectar(str(tmp_path / "teste.db"))


def test_edital_nunca_visto_e_classificado_como_novo(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste()

    [(_, status, linha_anterior)] = banco.classificar(conexao, [edital])

    assert status == "novo"
    assert linha_anterior is None


def test_depois_de_salvar_edital_some_da_lista_de_novos(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste()

    classificados = banco.classificar(conexao, [edital])
    banco.salvar(conexao, classificados)

    [(_, status, _linha)] = banco.classificar(conexao, [edital])
    assert status == "sem_mudanca"


def test_mudanca_de_prazo_e_classificada_como_atualizado(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital_original = _edital_de_teste(prazo=datetime(2026, 12, 31, 8, 0))
    banco.salvar(conexao, banco.classificar(conexao, [edital_original]))

    edital_com_prazo_novo = _edital_de_teste(prazo=datetime(2027, 1, 15, 8, 0))
    [(_, status, linha_anterior)] = banco.classificar(conexao, [edital_com_prazo_novo])

    assert status == "atualizado"
    assert linha_anterior["data_encerramento_proposta"] == "2026-12-31T08:00:00"


def test_visto_em_nao_muda_quando_edital_e_atualizado(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital_original = _edital_de_teste(prazo=datetime(2026, 12, 31, 8, 0))
    banco.salvar(conexao, banco.classificar(conexao, [edital_original]))

    linha_apos_primeiro_save = conexao.execute(
        "SELECT visto_em FROM editais WHERE numero_controle_pncp = ?",
        (edital_original.numero_controle_pncp,),
    ).fetchone()

    edital_atualizado = _edital_de_teste(prazo=datetime(2027, 1, 15, 8, 0))
    banco.salvar(conexao, banco.classificar(conexao, [edital_atualizado]))

    linha_apos_segundo_save = conexao.execute(
        "SELECT visto_em, data_encerramento_proposta FROM editais WHERE numero_controle_pncp = ?",
        (edital_original.numero_controle_pncp,),
    ).fetchone()

    assert linha_apos_segundo_save["visto_em"] == linha_apos_primeiro_save["visto_em"]
    assert linha_apos_segundo_save["data_encerramento_proposta"] == "2027-01-15T08:00:00"


def test_dois_editais_diferentes_nao_se_confundem(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital_a = _edital_de_teste(numero_controle_pncp="11111111111111-1-000001/2026")
    banco.salvar(conexao, banco.classificar(conexao, [edital_a]))

    edital_b = _edital_de_teste(numero_controle_pncp="22222222222222-1-000002/2026")
    resultado = banco.classificar(conexao, [edital_a, edital_b])

    status_por_numero = {edital.numero_controle_pncp: status for edital, status, _ in resultado}
    assert status_por_numero["11111111111111-1-000001/2026"] == "sem_mudanca"
    assert status_por_numero["22222222222222-1-000002/2026"] == "novo"


def test_historico_vazio_quando_banco_esta_vazio(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    assert banco.consultar_historico(conexao) == []


def test_historico_devolve_edital_salvo_com_segmentos_decodificados(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    edital = _edital_de_teste()
    banco.salvar(conexao, banco.classificar(conexao, [edital]))

    [linha] = banco.consultar_historico(conexao)

    assert linha["numero_controle_pncp"] == edital.numero_controle_pncp
    assert linha["segmentos"] == [{"segmento": "Limpeza", "termos": ["material", "limpeza"]}]


def test_historico_com_dias_ignora_edital_antigo(tmp_path):
    conexao = _banco_de_teste(tmp_path)

    edital_antigo = _edital_de_teste(numero_controle_pncp="11111111111111-1-000001/2026")
    banco.salvar(conexao, banco.classificar(conexao, [edital_antigo]))
    visto_em_antigo = (datetime.now() - timedelta(days=200)).isoformat()
    conexao.execute(
        "UPDATE editais SET visto_em = ? WHERE numero_controle_pncp = ?",
        (visto_em_antigo, edital_antigo.numero_controle_pncp),
    )
    conexao.commit()

    edital_recente = _edital_de_teste(numero_controle_pncp="22222222222222-1-000002/2026")
    banco.salvar(conexao, banco.classificar(conexao, [edital_recente]))

    historico_90_dias = banco.consultar_historico(conexao, dias=90)

    numeros_no_historico = {linha["numero_controle_pncp"] for linha in historico_90_dias}
    assert numeros_no_historico == {"22222222222222-1-000002/2026"}
