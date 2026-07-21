"""
Este modulo so fala com o banco SQLite: cria a tabela se nao existir,
descobre se um edital ja foi visto antes, e grava/atualiza os editais.
Nao sabe nada sobre HTTP nem sobre palavra-chave, so sabe persistir um
objeto Edital ja pronto (ver modelos.py).

sqlite3 e um modulo que ja vem instalado com o Python (nao precisa
adicionar no requirements.txt). Ele guarda o banco inteiro num arquivo so
(dados/radar.db), sem precisar instalar nem configurar um servidor de
banco de dados separado.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

CAMINHO_BANCO_PADRAO = "dados/radar.db"

# So esses tres campos contam como "mudanca relevante" pra reaparecer como
# atualizado. objeto/orgao/etc quase nunca mudam depois de publicados;
# prazo, situacao e valor sao os que realmente importam acompanhar.
CAMPOS_QUE_IMPORTAM_PARA_ATUALIZACAO = ["situacao", "valor_estimado", "data_encerramento_proposta"]

CRIAR_TABELA_SQL = """
CREATE TABLE IF NOT EXISTS editais (
    numero_controle_pncp TEXT PRIMARY KEY,
    orgao TEXT,
    municipio TEXT,
    uf TEXT,
    codigo_ibge TEXT,
    modalidade TEXT,
    objeto TEXT,
    informacao_complementar TEXT,
    situacao TEXT,
    valor_estimado REAL,
    data_encerramento_proposta TEXT,
    link_sistema_origem TEXT,
    link_pncp TEXT,
    segmentos TEXT,
    beneficios_itens TEXT,
    visto_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
)
"""

SQL_UPSERT = """
INSERT INTO editais (
    numero_controle_pncp, orgao, municipio, uf, codigo_ibge, modalidade,
    objeto, informacao_complementar, situacao, valor_estimado,
    data_encerramento_proposta, link_sistema_origem, link_pncp,
    segmentos, beneficios_itens, visto_em, atualizado_em
) VALUES (
    :numero_controle_pncp, :orgao, :municipio, :uf, :codigo_ibge, :modalidade,
    :objeto, :informacao_complementar, :situacao, :valor_estimado,
    :data_encerramento_proposta, :link_sistema_origem, :link_pncp,
    :segmentos, :beneficios_itens, :visto_em, :atualizado_em
)
ON CONFLICT(numero_controle_pncp) DO UPDATE SET
    orgao = excluded.orgao,
    municipio = excluded.municipio,
    uf = excluded.uf,
    codigo_ibge = excluded.codigo_ibge,
    modalidade = excluded.modalidade,
    objeto = excluded.objeto,
    informacao_complementar = excluded.informacao_complementar,
    situacao = excluded.situacao,
    valor_estimado = excluded.valor_estimado,
    data_encerramento_proposta = excluded.data_encerramento_proposta,
    link_sistema_origem = excluded.link_sistema_origem,
    link_pncp = excluded.link_pncp,
    segmentos = excluded.segmentos,
    beneficios_itens = excluded.beneficios_itens,
    atualizado_em = excluded.atualizado_em
"""
# ON CONFLICT(...) DO UPDATE SET e o "upsert": tenta inserir uma linha nova,
# e se ja existir uma linha com essa numero_controle_pncp (a chave primaria),
# atualiza os campos listados em vez de dar erro de chave duplicada.
# Reparem que visto_em NAO esta no SET: ele so e gravado na insercao,
# nunca sobrescrito, entao a data da "primeira vez que vimos" fica fixa.

# Tabela filha de editais (um edital tem varios itens). A chave e composta
# (numero_controle_pncp + numero_item) porque numero_item so e unico DENTRO
# de um edital, dois editais diferentes podem ter os dois um "item 1".
# FOREIGN KEY aqui e so documentacao da relacao: o SQLite nao chega a
# impedir uma linha orfa por causa disso (precisaria de
# "PRAGMA foreign_keys = ON", que este projeto nunca ligou), mas como hoje
# nao existe nenhum caminho que apague um edital, isso nao e um risco real.
CRIAR_TABELA_ITENS_SQL = """
CREATE TABLE IF NOT EXISTS itens_edital (
    numero_controle_pncp TEXT NOT NULL,
    numero_item INTEGER NOT NULL,
    descricao TEXT,
    material_ou_servico TEXT,
    quantidade REAL,
    valor_unitario_estimado REAL,
    valor_total REAL,
    tipo_beneficio TEXT,
    PRIMARY KEY (numero_controle_pncp, numero_item),
    FOREIGN KEY (numero_controle_pncp) REFERENCES editais(numero_controle_pncp)
)
"""

SQL_UPSERT_ITEM = """
INSERT INTO itens_edital (
    numero_controle_pncp, numero_item, descricao, material_ou_servico,
    quantidade, valor_unitario_estimado, valor_total, tipo_beneficio
) VALUES (
    :numero_controle_pncp, :numero_item, :descricao, :material_ou_servico,
    :quantidade, :valor_unitario_estimado, :valor_total, :tipo_beneficio
)
ON CONFLICT(numero_controle_pncp, numero_item) DO UPDATE SET
    descricao = excluded.descricao,
    material_ou_servico = excluded.material_ou_servico,
    quantidade = excluded.quantidade,
    valor_unitario_estimado = excluded.valor_unitario_estimado,
    valor_total = excluded.valor_total,
    tipo_beneficio = excluded.tipo_beneficio
"""
# Upsert pela chave composta: rodar isso de novo pro mesmo edital so
# atualiza as mesmas linhas, nunca duplica. E o que deixa o script de
# backfill (Tarefa A.3) seguro de rodar mais de uma vez.


def conectar(caminho=CAMINHO_BANCO_PADRAO):
    """Abre a conexao com o banco (cria o arquivo se nao existir ainda) e
    garante que a tabela exista.

    conexao.row_factory = sqlite3.Row muda o formato das linhas que a
    gente le do banco: por padrao, o sqlite3 devolve cada linha como uma
    tupla (so os valores, sem nome). Com o row_factory, cada linha vira
    parecido com um dicionario, entao da pra escrever linha["situacao"]
    em vez de ter que decorar em que posicao da tupla cada campo esta.
    """
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute(CRIAR_TABELA_SQL)
    conexao.execute(CRIAR_TABELA_ITENS_SQL)
    conexao.commit()
    return conexao


def _buscar_edital_salvo(conexao, numero_controle_pncp):
    cursor = conexao.execute(
        "SELECT * FROM editais WHERE numero_controle_pncp = ?", (numero_controle_pncp,)
    )
    return cursor.fetchone()


def _valor_para_comparar(edital, campo):
    """Deixa o valor do Edital no mesmo formato que esta guardado no banco,
    pra comparacao dar certo. O unico caso especial e data, porque o
    SQLite nao tem um tipo de data proprio: a gente guarda como texto
    (isoformat), entao precisa comparar texto com texto.
    """
    valor = getattr(edital, campo)
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor


def classificar(conexao, editais):
    """So LE o banco, nao grava nada. Para cada edital, descobre o status:

    - "novo": nunca vimos esse numero_controle_pncp antes.
    - "atualizado": ja vimos, mas situacao, valor_estimado ou
      data_encerramento_proposta mudaram desde a ultima vez.
    - "sem_mudanca": ja vimos, e nada relevante mudou.

    Devolve uma lista de tuplas (edital, status, linha_anterior), onde
    linha_anterior e None para os novos.
    """
    resultado = []

    for edital in editais:
        linha_existente = _buscar_edital_salvo(conexao, edital.numero_controle_pncp)

        if linha_existente is None:
            resultado.append((edital, "novo", None))
            continue

        mudou = any(
            _valor_para_comparar(edital, campo) != linha_existente[campo]
            for campo in CAMPOS_QUE_IMPORTAM_PARA_ATUALIZACAO
        )
        status = "atualizado" if mudou else "sem_mudanca"
        resultado.append((edital, status, linha_existente))

    return resultado


def salvar(conexao, editais_classificados):
    """Grava (insere ou atualiza) cada edital classificado no banco.
    Recebe a mesma lista de tuplas que a funcao classificar devolveu.
    """
    agora = datetime.now().isoformat()

    for edital, _status, linha_existente in editais_classificados:
        visto_em = linha_existente["visto_em"] if linha_existente is not None else agora

        conexao.execute(SQL_UPSERT, {
            "numero_controle_pncp": edital.numero_controle_pncp,
            "orgao": edital.orgao,
            "municipio": edital.municipio,
            "uf": edital.uf,
            "codigo_ibge": edital.codigo_ibge,
            "modalidade": edital.modalidade,
            "objeto": edital.objeto,
            "informacao_complementar": edital.informacao_complementar,
            "situacao": edital.situacao,
            "valor_estimado": edital.valor_estimado,
            "data_encerramento_proposta": edital.data_encerramento_proposta.isoformat(),
            "link_sistema_origem": edital.link_sistema_origem,
            "link_pncp": edital.link_pncp,
            "segmentos": json.dumps(edital.segmentos, ensure_ascii=False),
            "beneficios_itens": json.dumps(edital.beneficios_itens, ensure_ascii=False),
            "visto_em": visto_em,
            "atualizado_em": agora,
        })

    conexao.commit()


def consultar_historico(conexao, dias=None):
    """Devolve tudo que ja passou pelo Radar (nao so o que esta aberto
    agora), visto pela primeira vez nos ultimos `dias` dias (ou todo o
    historico, se dias for None), do mais recente pro mais antigo.

    Nao filtra por municipio/segmento aqui: como json nao da pra comparar
    direito dentro de uma clausula WHERE do SQLite sem complicar a query,
    o main.py busca por data (essa funcao) e filtra municipio/segmento em
    Python depois, reaproveitando a mesma normalizacao usada no resto do
    programa.

    segmentos e beneficios_itens voltam decodificados (lista/None), nao
    como o texto JSON cru que fica guardado no banco.
    """
    if dias is not None:
        limite = (datetime.now() - timedelta(days=dias)).isoformat()
        cursor = conexao.execute(
            "SELECT * FROM editais WHERE visto_em >= ? ORDER BY visto_em DESC", (limite,)
        )
    else:
        cursor = conexao.execute("SELECT * FROM editais ORDER BY visto_em DESC")

    linhas = []
    for linha in cursor.fetchall():
        linha_dict = dict(linha)
        linha_dict["segmentos"] = json.loads(linha_dict["segmentos"]) if linha_dict["segmentos"] else []
        linha_dict["beneficios_itens"] = (
            json.loads(linha_dict["beneficios_itens"]) if linha_dict["beneficios_itens"] else None
        )
        linhas.append(linha_dict)

    return linhas


def atualizar_segmentos(conexao, numero_controle_pncp, novos_segmentos):
    """Corrige so a coluna segmentos (e marca atualizado_em) de uma linha
    que ja existe no banco, sem mexer no resto. Usada quando o
    keywords.yaml muda depois que o edital ja foi salvo (ver
    scripts/ressincronizar_banco.py): o edital continua no banco, so o
    segmento gravado e que fica desatualizado ate isso rodar.
    """
    conexao.execute(
        "UPDATE editais SET segmentos = ?, atualizado_em = ? WHERE numero_controle_pncp = ?",
        (json.dumps(novos_segmentos, ensure_ascii=False), datetime.now().isoformat(), numero_controle_pncp),
    )
    conexao.commit()


def salvar_itens(conexao, numero_controle_pncp, itens):
    """Grava (insere ou atualiza) a lista de itens de um edital especifico.
    Cada item e um dicionario com as chaves numero_item, descricao,
    material_ou_servico, quantidade, valor_unitario_estimado, valor_total
    e tipo_beneficio (e o formato que pncp_client.buscar_itens_da_compra
    devolve, ver Tarefa A.2).

    Usada tanto na captura diaria quanto no script de backfill
    (scripts/backfill_itens.py, Tarefa A.3): como a chave e composta
    (numero_controle_pncp + numero_item), rodar isso de novo pro mesmo
    edital so atualiza as linhas que ja existiam, nunca duplica.
    """
    for item in itens:
        conexao.execute(SQL_UPSERT_ITEM, {
            "numero_controle_pncp": numero_controle_pncp,
            "numero_item": item["numero_item"],
            "descricao": item.get("descricao"),
            "material_ou_servico": item.get("material_ou_servico"),
            "quantidade": item.get("quantidade"),
            "valor_unitario_estimado": item.get("valor_unitario_estimado"),
            "valor_total": item.get("valor_total"),
            "tipo_beneficio": item.get("tipo_beneficio"),
        })
    conexao.commit()


def consultar_itens_do_edital(conexao, numero_controle_pncp):
    """Le os itens ja salvos de um edital especifico, do item 1 em diante.

    Usada pelo painel (Tarefa A.4) so quando o usuario abre os detalhes
    de UM edital especifico, nunca busca os itens de todos os editais de
    uma vez (por isso essa funcao pede um numero_controle_pncp, diferente
    de consultar_historico que devolve tudo).
    """
    cursor = conexao.execute(
        "SELECT * FROM itens_edital WHERE numero_controle_pncp = ? ORDER BY numero_item",
        (numero_controle_pncp,),
    )
    return [dict(linha) for linha in cursor.fetchall()]
