"""
Testes do entrega/batimento.py: quando o e-mail semanal "Radar ativo" deve
sair, que numeros ele leva e o texto. O relogio nunca e consultado: cada
teste passa o "agora" que quer.

Datas usadas: 23/11/2026 e uma segunda-feira, 24/11/2026 e terca.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_batimento.py -v
"""

from datetime import datetime

from captura import banco
from captura.modelos import Edital
from entrega import batimento

SEGUNDA_06H = datetime(2026, 11, 23, 6, 0)


def _edital_de_teste(numero="00000000000000-1-000001/2026", prazo=None, situacao="Divulgada no PNCP"):
    return Edital(
        numero_controle_pncp=numero,
        cnpj_orgao="00000000000000",
        ano_compra=2026,
        sequencial_compra=1,
        orgao="Prefeitura de Teste",
        municipio="Votuporanga",
        uf="SP",
        codigo_ibge="3557105",
        modalidade="Pregão - Eletrônico",
        objeto="Aquisição de material de limpeza",
        situacao=situacao,
        data_encerramento_proposta=prazo or datetime(2026, 12, 31, 8, 0),
        valor_estimado=1000.0,
        segmentos=[{"segmento": "Limpeza", "termos": ["material", "limpeza"]}],
    )


def _banco_de_teste(tmp_path):
    return banco.conectar(str(tmp_path / "teste.db"))


# ---------------------------------------------------------------------------
# deve_enviar: dia, hora e "ja mandei hoje?"
# ---------------------------------------------------------------------------


def test_envia_na_segunda_depois_das_05h_se_nunca_enviou():
    assert batimento.deve_enviar(SEGUNDA_06H, None) is True


def test_envia_exatamente_as_05h_da_segunda():
    assert batimento.deve_enviar(datetime(2026, 11, 23, 5, 0), None) is True


def test_nao_envia_na_segunda_antes_das_05h():
    assert batimento.deve_enviar(datetime(2026, 11, 23, 4, 59), None) is False


def test_nao_envia_na_madrugada_de_segunda_mesmo_depois_da_meia_noite():
    assert batimento.deve_enviar(datetime(2026, 11, 23, 0, 30), None) is False


def test_nao_envia_em_nenhum_outro_dia_da_semana():
    # 24/11 terca ... 29/11 domingo, sempre as 10h
    for dia in range(24, 30):
        assert batimento.deve_enviar(datetime(2026, 11, dia, 10, 0), None) is False


def test_nao_envia_de_novo_no_mesmo_dia():
    ja_enviado_hoje = datetime(2026, 11, 23, 6, 0).isoformat()

    assert batimento.deve_enviar(datetime(2026, 11, 23, 13, 0), ja_enviado_hoje) is False


def test_envia_na_segunda_seguinte_depois_de_ter_enviado_na_anterior():
    enviado_segunda_passada = datetime(2026, 11, 16, 6, 0).isoformat()

    assert batimento.deve_enviar(SEGUNDA_06H, enviado_segunda_passada) is True


def test_valor_guardado_ilegivel_conta_como_nunca_enviado():
    assert batimento.deve_enviar(SEGUNDA_06H, "isto nao e uma data") is True


def test_texto_vazio_guardado_conta_como_nunca_enviado():
    assert batimento.deve_enviar(SEGUNDA_06H, "") is True


# ---------------------------------------------------------------------------
# montar_resumo: os numeros
# ---------------------------------------------------------------------------


def _registrar(conexao, quando, resultado="completa", falhas=0):
    banco.registrar_execucao(conexao, quando, resultado, 143, falhas, 330, 5)


def test_resumo_de_banco_vazio(tmp_path):
    conexao = _banco_de_teste(tmp_path)

    resumo = batimento.montar_resumo(conexao, SEGUNDA_06H)

    assert resumo == {
        "editais_abertos": 0,
        "editais_novos_na_semana": 0,
        "capturas_na_semana": 0,
        "capturas_com_falhas_na_semana": 0,
        "ultima_execucao": None,
        "maior_intervalo_em_horas": None,
    }


def test_resumo_conta_so_editais_abertos_validos(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    futuro = datetime(2026, 12, 20, 9, 0)
    banco.salvar(conexao, [
        (_edital_de_teste("ABERTO", futuro), "novo", None),
        (_edital_de_teste("VENCIDO", datetime(2026, 11, 20, 9, 0)), "novo", None),
        (_edital_de_teste("SUSPENSO", futuro, situacao="Suspensa"), "novo", None),
        (_edital_de_teste("EXCLUIDO", futuro), "novo", None),
    ])
    banco.marcar_excluido(conexao, "EXCLUIDO", datetime(2026, 11, 22, 10, 0))

    resumo = batimento.montar_resumo(conexao, SEGUNDA_06H)

    assert resumo["editais_abertos"] == 1


def test_resumo_so_conta_capturas_dos_ultimos_7_dias(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    _registrar(conexao, datetime(2026, 11, 10, 7, 0))   # 13 dias atras: fora
    _registrar(conexao, datetime(2026, 11, 16, 5, 59))  # 7 dias e 1 minuto atras: fora
    _registrar(conexao, datetime(2026, 11, 16, 6, 0))   # exatamente 7 dias atras: dentro
    _registrar(conexao, datetime(2026, 11, 18, 7, 0))
    _registrar(conexao, datetime(2026, 11, 22, 13, 0), resultado="com_falhas", falhas=3)

    resumo = batimento.montar_resumo(conexao, SEGUNDA_06H)

    assert resumo["capturas_na_semana"] == 3
    assert resumo["capturas_com_falhas_na_semana"] == 1


def test_resumo_traz_a_ultima_execucao(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    _registrar(conexao, datetime(2026, 11, 21, 7, 0))
    _registrar(conexao, datetime(2026, 11, 22, 13, 0), resultado="com_falhas", falhas=3)

    ultima = batimento.montar_resumo(conexao, SEGUNDA_06H)["ultima_execucao"]

    assert ultima["executada_em"] == "2026-11-22T13:00:00"
    assert ultima["municipios_com_falha"] == 3


# ---------------------------------------------------------------------------
# texto do e-mail
# ---------------------------------------------------------------------------


def _resumo_de_teste(ultima_execucao):
    return {
        "editais_abertos": 74,
        "editais_novos_na_semana": 12,
        "capturas_na_semana": 14,
        "capturas_com_falhas_na_semana": 1,
        "ultima_execucao": ultima_execucao,
        "maior_intervalo_em_horas": 30.0,
    }


def test_assunto_leva_a_data():
    assert batimento.montar_assunto(SEGUNDA_06H) == "Radar ativo: resumo da semana - 23/11/2026"


def test_corpo_traz_os_numeros_e_a_ultima_captura_completa():
    ultima = {
        "executada_em": "2026-11-22T13:00:00", "resultado": "completa",
        "municipios_consultados": 143, "municipios_com_falha": 0,
    }

    corpo = batimento.montar_corpo_html(_resumo_de_teste(ultima))

    assert "Radar ativo" in corpo
    assert "<strong>74</strong>" in corpo
    assert "<strong>12</strong>" in corpo
    assert "<strong>14</strong>" in corpo
    assert "Última captura bem-sucedida" in corpo
    assert "22/11/2026 13h00" in corpo
    assert "completa, 143 municípios consultados" in corpo
    assert "Execuções nos últimos 7 dias" in corpo
    assert "Maior intervalo entre duas capturas na semana: <strong>30 h</strong>" in corpo


def test_corpo_avisa_quando_a_ultima_captura_teve_falhas():
    ultima = {
        "executada_em": "2026-11-22T13:00:00", "resultado": "com_falhas",
        "municipios_consultados": 143, "municipios_com_falha": 3,
    }

    corpo = batimento.montar_corpo_html(_resumo_de_teste(ultima))

    assert "com falhas: 3 de 143 municípios ficaram de fora" in corpo


def test_corpo_sem_nenhuma_captura_registrada():
    resumo = _resumo_de_teste(None)
    resumo["maior_intervalo_em_horas"] = None

    corpo = batimento.montar_corpo_html(resumo)

    assert "nenhuma registrada" in corpo
    assert "sem dados suficientes" in corpo


def test_corpo_mostra_primeiro_o_que_diz_se_o_radar_esta_vivo():
    corpo = batimento.montar_corpo_html(_resumo_de_teste(None))

    assert corpo.index("Última captura bem-sucedida") < corpo.index("Editais abertos no banco")


# ---------------------------------------------------------------------------
# maior intervalo entre capturas: separa "sem novidade" de "Radar parado"
# ---------------------------------------------------------------------------


def test_maior_intervalo_e_o_maior_buraco_entre_capturas_seguidas(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    _registrar(conexao, datetime(2026, 11, 17, 7, 0))
    _registrar(conexao, datetime(2026, 11, 17, 13, 0))   # 6 h depois
    _registrar(conexao, datetime(2026, 11, 18, 19, 0))   # 30 h depois (o buraco)
    _registrar(conexao, datetime(2026, 11, 18, 22, 0))   # 3 h depois

    resumo = batimento.montar_resumo(conexao, SEGUNDA_06H)

    assert resumo["maior_intervalo_em_horas"] == 30.0


def test_maior_intervalo_com_uma_captura_so_nao_existe(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    _registrar(conexao, datetime(2026, 11, 22, 7, 0))

    assert batimento.montar_resumo(conexao, SEGUNDA_06H)["maior_intervalo_em_horas"] is None


def test_maior_intervalo_ignora_capturas_de_antes_da_janela_de_7_dias(tmp_path):
    conexao = _banco_de_teste(tmp_path)
    _registrar(conexao, datetime(2026, 11, 1, 7, 0))    # fora da janela: o buraco ate a proxima nao conta
    _registrar(conexao, datetime(2026, 11, 20, 7, 0))
    _registrar(conexao, datetime(2026, 11, 20, 13, 0))  # 6 h

    assert batimento.montar_resumo(conexao, SEGUNDA_06H)["maior_intervalo_em_horas"] == 6.0
