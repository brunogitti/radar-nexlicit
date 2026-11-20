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


def _item_de_teste(numero_item=1, descricao="Material de limpeza diverso"):
    return {
        "numero_item": numero_item,
        "descricao": descricao,
        "material_ou_servico": "Material",
        "quantidade": 10.0,
        "valor_unitario_estimado": 25.5,
        "valor_total": 255.0,
        "tipo_beneficio": "Sem benefício",
    }


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


def test_consultar_itens_de_edital_sem_itens_devolve_lista_vazia(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    assert banco.consultar_itens_do_edital(conexao, "00000000000000-1-000001/2026") == []


def test_salvar_itens_grava_e_devolve_em_ordem(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    numero_controle = "00000000000000-1-000001/2026"

    banco.salvar_itens(conexao, numero_controle, [
        _item_de_teste(numero_item=2, descricao="Segundo item"),
        _item_de_teste(numero_item=1, descricao="Primeiro item"),
    ])

    itens = banco.consultar_itens_do_edital(conexao, numero_controle)

    assert [item["numero_item"] for item in itens] == [1, 2]
    assert itens[0]["descricao"] == "Primeiro item"
    assert itens[0]["valor_total"] == 255.0


def test_salvar_itens_de_um_edital_nao_aparece_no_de_outro(tmp_path):
    conexao = _banco_de_teste(tmp_path)

    banco.salvar_itens(conexao, "11111111111111-1-000001/2026", [_item_de_teste()])
    banco.salvar_itens(conexao, "22222222222222-1-000002/2026", [_item_de_teste(), _item_de_teste(numero_item=2)])

    assert len(banco.consultar_itens_do_edital(conexao, "11111111111111-1-000001/2026")) == 1
    assert len(banco.consultar_itens_do_edital(conexao, "22222222222222-1-000002/2026")) == 2


def test_salvar_itens_duas_vezes_atualiza_em_vez_de_duplicar(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    numero_controle = "00000000000000-1-000001/2026"

    banco.salvar_itens(conexao, numero_controle, [_item_de_teste(descricao="Descricao antiga")])
    banco.salvar_itens(conexao, numero_controle, [_item_de_teste(descricao="Descricao corrigida")])

    itens = banco.consultar_itens_do_edital(conexao, numero_controle)

    assert len(itens) == 1
    assert itens[0]["descricao"] == "Descricao corrigida"


# ---------------------------------------------------------------------------
# Conferencias do arquivo de banco (blindagem do workflow, Fase 0.5.2)
# ---------------------------------------------------------------------------


def _banco_com_editais(tmp_path, quantidade, nome="com_editais.db"):
    """Cria um arquivo de banco de verdade com `quantidade` editais e
    devolve o caminho dele."""
    caminho = str(tmp_path / nome)
    conexao = banco.conectar(caminho)
    editais = [
        (_edital_de_teste(f"00000000000000-1-{numero:06d}/2026"), "novo", None)
        for numero in range(1, quantidade + 1)
    ]
    banco.salvar(conexao, editais)
    conexao.close()
    return caminho


def test_contar_editais_de_banco_vazio_devolve_zero(tmp_path):
    caminho = _banco_com_editais(tmp_path, 0)

    assert banco.contar_editais(caminho) == 0


def test_contar_editais_conta_os_editais_salvos(tmp_path):
    caminho = _banco_com_editais(tmp_path, 3)

    assert banco.contar_editais(caminho) == 3


def test_banco_inteiro_passa_na_verificacao_de_integridade(tmp_path):
    caminho = _banco_com_editais(tmp_path, 2)

    assert banco.verificar_integridade(caminho) == (True, "ok")


def test_arquivo_que_nao_existe_falha_na_verificacao(tmp_path):
    esta_ok, motivo = banco.verificar_integridade(str(tmp_path / "nao_existe.db"))

    assert esta_ok is False
    assert "nao existe" in motivo


def test_arquivo_corrompido_falha_na_verificacao(tmp_path):
    caminho = tmp_path / "lixo.db"
    caminho.write_bytes(b"isto nao e um banco sqlite, e so texto solto" * 50)

    esta_ok, motivo = banco.verificar_integridade(str(caminho))

    assert esta_ok is False
    assert "nao abre como banco" in motivo or "integrity_check" in motivo


def test_banco_sem_a_tabela_editais_falha_na_verificacao(tmp_path):
    import sqlite3

    caminho = str(tmp_path / "outra_coisa.db")
    conexao = sqlite3.connect(caminho)
    conexao.execute("CREATE TABLE outra_coisa (id INTEGER)")
    conexao.commit()
    conexao.close()

    esta_ok, motivo = banco.verificar_integridade(caminho)

    assert esta_ok is False
    assert "editais" in motivo


def test_verificacao_nao_altera_o_arquivo(tmp_path):
    caminho = _banco_com_editais(tmp_path, 2)
    antes = (tmp_path / "com_editais.db").read_bytes()

    banco.verificar_integridade(caminho)
    banco.contar_editais(caminho)

    assert (tmp_path / "com_editais.db").read_bytes() == antes


def test_pode_publicar_quando_local_tem_mais_editais_que_o_remoto():
    assert banco.decidir_se_pode_publicar(105, 100) == (True, "ok")


def test_pode_publicar_quando_local_tem_o_mesmo_numero_de_editais():
    assert banco.decidir_se_pode_publicar(100, 100) == (True, "ok")


def test_pode_publicar_a_primeira_vez_sem_banco_remoto():
    assert banco.decidir_se_pode_publicar(10, None) == (True, "ok")


def test_bloqueia_banco_local_vazio():
    pode, motivo = banco.decidir_se_pode_publicar(0, 100)

    assert pode is False
    assert "vazio" in motivo


def test_bloqueia_banco_local_vazio_mesmo_sem_banco_remoto():
    pode, _motivo = banco.decidir_se_pode_publicar(0, None)

    assert pode is False


def test_bloqueia_banco_local_menor_que_o_remoto():
    pode, motivo = banco.decidir_se_pode_publicar(90, 100)

    assert pode is False
    assert "90" in motivo and "100" in motivo


def test_permitir_reducao_libera_banco_local_menor_que_o_remoto():
    pode, motivo = banco.decidir_se_pode_publicar(90, 100, permitir_reducao=True)

    assert pode is True
    assert "100 -> 90" in motivo


def test_permitir_reducao_nao_libera_banco_vazio():
    pode, _motivo = banco.decidir_se_pode_publicar(0, 100, permitir_reducao=True)

    assert pode is False


def test_edital_tem_itens_salvos(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    numero = "00000000000000-1-000001/2026"

    assert banco.edital_tem_itens_salvos(conexao, numero) is False

    banco.salvar_itens(conexao, numero, [_item_de_teste()])

    assert banco.edital_tem_itens_salvos(conexao, numero) is True
