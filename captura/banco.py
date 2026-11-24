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

# Texto que o PNCP usa na situacao de um edital normal, em aberto. Qualquer
# outra situacao (Suspensa, Revogada, Anulada...) o painel mostra num selo.
SITUACAO_DIVULGADA = "Divulgada no PNCP"

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

# Guarda pequenos fatos soltos que nao pertencem a um edital, no formato
# "chave = valor" (os dois em texto). Hoje so tem uma chave:
# "batimento_enviado_em" (quando o e-mail semanal "Radar ativo" saiu pela
# ultima vez, ver entrega/batimento.py). Fica no banco, e nao num arquivo,
# porque o banco e a unica coisa que o workflow publica entre uma execucao e
# outra (branch data).
CRIAR_TABELA_METADADOS_SQL = """
CREATE TABLE IF NOT EXISTS metadados (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
)
"""

# Uma linha por captura completa que terminou (nao em --dry-run, nao com
# --municipio). Serve ao e-mail semanal ("quantas capturas nos ultimos 7
# dias") e ja adianta o registro de execucoes da coleta v2. executada_em e o
# horario de Brasilia (isoformat) do FIM da captura. resultado:
# "completa" (todos os municipios responderam) ou "com_falhas" (alguns
# ficaram de fora). Captura em que TODOS os municipios falharam nao e
# registrada: nao foi uma captura de verdade.
CRIAR_TABELA_EXECUCOES_SQL = """
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executada_em TEXT NOT NULL,
    resultado TEXT NOT NULL,
    municipios_consultados INTEGER NOT NULL,
    municipios_com_falha INTEGER NOT NULL,
    editais_na_lista INTEGER NOT NULL,
    editais_novos_ou_atualizados INTEGER NOT NULL
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
    conexao.execute(CRIAR_TABELA_METADADOS_SQL)
    conexao.execute(CRIAR_TABELA_EXECUCOES_SQL)
    _garantir_coluna_excluido_em(conexao)
    conexao.commit()
    return conexao


def _garantir_coluna_excluido_em(conexao):
    """Adiciona a coluna excluido_em na tabela editais se ela ainda nao
    existir (banco criado antes desta coluna). Pode rodar quantas vezes
    quiser: so mexe no banco na primeira.

    Por que checar antes: ALTER TABLE ... ADD COLUMN da erro se a coluna ja
    existe, e o SQLite nao tem "ADD COLUMN IF NOT EXISTS". Entao a gente
    pergunta ao proprio banco quais colunas a tabela tem (PRAGMA
    table_info) e so adiciona se faltar.

    excluido_em guarda QUANDO o Radar descobriu que o PNCP excluiu o edital
    (resposta 410). Vazio (NULL) = edital normal. Nunca apagamos a linha:
    a conferencia de publicacao do banco exige que a contagem de editais
    nao diminua, e o historico continua valendo.
    """
    colunas = [linha["name"] for linha in conexao.execute("PRAGMA table_info(editais)")]
    if "excluido_em" not in colunas:
        conexao.execute("ALTER TABLE editais ADD COLUMN excluido_em TEXT")


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


def consultar_historico(conexao, dias=None, incluir_excluidos=False):
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

    Editais que o PNCP excluiu (coluna excluido_em preenchida) ficam de
    fora, a menos que incluir_excluidos=True.
    """
    condicoes = []
    parametros = []
    if dias is not None:
        condicoes.append("visto_em >= ?")
        parametros.append((datetime.now() - timedelta(days=dias)).isoformat())
    if not incluir_excluidos:
        condicoes.append("excluido_em IS NULL")

    filtro_sql = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    cursor = conexao.execute(
        f"SELECT * FROM editais {filtro_sql} ORDER BY visto_em DESC", parametros
    )

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


def buscar_abertos_fora_da_lista(conexao, agora, limite, numeros_na_lista):
    """Devolve os editais do banco que o Radar ainda considera abertos mas
    que NAO vieram na lista desta captura: candidatos a terem sido
    excluidos, suspensos, revogados ou anulados no PNCP.

    Entra quem:
      - nao tem excluido_em (ainda nao sabemos que foi excluido);
      - tem prazo depois de `agora` (ainda nao encerrou) e ate `limite`
        (o fim da janela de dias que a captura pediu: um edital com prazo
        alem disso nem poderia aparecer na lista, entao a ausencia dele
        nao quer dizer nada);
      - nao esta em `numeros_na_lista` (conjunto de numero_controle_pncp
        que vieram na captura).

    `agora` e `limite` sao datetime em horario de Brasilia, porque o prazo
    guardado e em Brasilia (ver captura/relogio.py). Cada edital volta como
    dicionario com numero_controle_pncp, link_pncp, municipio e situacao.
    """
    cursor = conexao.execute(
        """
        SELECT numero_controle_pncp, link_pncp, municipio, situacao
        FROM editais
        WHERE excluido_em IS NULL
          AND data_encerramento_proposta > ?
          AND data_encerramento_proposta <= ?
        ORDER BY data_encerramento_proposta
        """,
        (agora.isoformat(), limite.isoformat()),
    )
    return [dict(linha) for linha in cursor.fetchall() if linha["numero_controle_pncp"] not in numeros_na_lista]


def marcar_excluido(conexao, numero_controle_pncp, quando):
    """Registra que o PNCP excluiu este edital (resposta 410). NAO apaga a
    linha, so preenche excluido_em. `quando` e um datetime (o carimbo de
    registro, mesmo relogio de visto_em e atualizado_em)."""
    conexao.execute(
        "UPDATE editais SET excluido_em = ?, atualizado_em = ? WHERE numero_controle_pncp = ?",
        (quando.isoformat(), quando.isoformat(), numero_controle_pncp),
    )
    conexao.commit()


def atualizar_situacao(conexao, numero_controle_pncp, situacao, quando):
    """Corrige so a coluna situacao (e atualizado_em) de um edital que
    ja existe, quando o PNCP passou a informar outra (ex.: Suspensa).
    Se o edital voltar a ser "Divulgada no PNCP", a captura normal o
    reconhece como atualizado e grava de volta."""
    conexao.execute(
        "UPDATE editais SET situacao = ?, atualizado_em = ? WHERE numero_controle_pncp = ?",
        (situacao, quando.isoformat(), numero_controle_pncp),
    )
    conexao.commit()


def ler_metadado(conexao, chave):
    """Devolve o valor guardado para a chave, ou None se nunca foi gravada."""
    linha = conexao.execute("SELECT valor FROM metadados WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha is not None else None


def gravar_metadado(conexao, chave, valor):
    """Grava (ou troca) o valor de uma chave. E um upsert: se a chave ja
    existe, atualiza em vez de dar erro de chave duplicada."""
    conexao.execute(
        "INSERT INTO metadados (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )
    conexao.commit()


def registrar_execucao(
    conexao, executada_em, resultado, municipios_consultados, municipios_com_falha,
    editais_na_lista, editais_novos_ou_atualizados,
):
    """Acrescenta uma linha na tabela execucoes. executada_em e um datetime
    (horario de Brasilia, ver captura/relogio.py)."""
    conexao.execute(
        """
        INSERT INTO execucoes (
            executada_em, resultado, municipios_consultados, municipios_com_falha,
            editais_na_lista, editais_novos_ou_atualizados
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            executada_em.isoformat(), resultado, municipios_consultados,
            municipios_com_falha, editais_na_lista, editais_novos_ou_atualizados,
        ),
    )
    conexao.commit()


def consultar_execucoes_desde(conexao, desde):
    """Devolve as execucoes registradas a partir de `desde` (datetime), da
    mais recente pra mais antiga, cada uma como dicionario."""
    cursor = conexao.execute(
        "SELECT * FROM execucoes WHERE executada_em >= ? ORDER BY executada_em DESC, id DESC",
        (desde.isoformat(),),
    )
    return [dict(linha) for linha in cursor.fetchall()]


def contar_editais_abertos(conexao, agora):
    """Quantos editais estao valendo agora: situacao "Divulgada no PNCP",
    nao excluidos e com prazo depois de `agora` (horario de Brasilia)."""
    linha = conexao.execute(
        """
        SELECT COUNT(*) AS total FROM editais
        WHERE situacao = ? AND excluido_em IS NULL AND data_encerramento_proposta > ?
        """,
        (SITUACAO_DIVULGADA, agora.isoformat()),
    ).fetchone()
    return linha["total"]


def contar_editais_vistos_desde(conexao, desde):
    """Quantos editais (nao excluidos) o Radar viu pela primeira vez a
    partir de `desde` (datetime). Usa visto_em, o carimbo de registro."""
    linha = conexao.execute(
        "SELECT COUNT(*) AS total FROM editais WHERE visto_em >= ? AND excluido_em IS NULL",
        (desde.isoformat(),),
    ).fetchone()
    return linha["total"]


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


def edital_tem_itens_salvos(conexao, numero_controle_pncp):
    """Diz se ja existe pelo menos um item salvo pra esse edital.
    Usada pela captura pra decidir se um edital "sem mudanca" precisa ter
    os itens gravados agora (porque a busca anterior pode ter falhado).
    """
    cursor = conexao.execute(
        "SELECT 1 FROM itens_edital WHERE numero_controle_pncp = ? LIMIT 1",
        (numero_controle_pncp,),
    )
    return cursor.fetchone() is not None


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


# ---------------------------------------------------------------------------
# Conferencias do arquivo de banco (Fase 0.5.2, blindagem do workflow)
#
# Estas tres funcoes sao usadas pelos scripts em .github/scripts/ antes de
# publicar o banco na branch "data": elas respondem "esse arquivo esta
# inteiro?", "quantos editais tem?" e "pode ser publicado por cima do que ja
# esta la?". Ficam aqui (e nao dentro do script em shell) pra poderem ser
# testadas com pytest, como o resto do banco.
# ---------------------------------------------------------------------------


def _abrir_somente_leitura(caminho):
    """Abre o arquivo de banco SEM poder alterar nada nele (modo "ro",
    read-only). Assim uma conferencia nunca estraga o que esta conferindo.

    O caminho vira um endereco "file:///..." porque e esse formato que o
    SQLite exige pra aceitar o "?mode=ro". Path.as_uri() cuida de espacos
    e barras no caminho.
    """
    endereco = Path(caminho).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(endereco, uri=True)


def contar_editais(caminho):
    """Devolve quantos editais existem no arquivo de banco informado.
    Levanta sqlite3.DatabaseError se o arquivo nao abrir como banco ou nao
    tiver a tabela editais.
    """
    conexao = _abrir_somente_leitura(caminho)
    try:
        return conexao.execute("SELECT COUNT(*) FROM editais").fetchone()[0]
    finally:
        conexao.close()


def verificar_integridade(caminho):
    """Confere se o arquivo e um banco SQLite inteiro e com a tabela
    editais. Devolve uma tupla (esta_ok, motivo): quando esta_ok e False,
    motivo explica em texto o que deu errado.

    PRAGMA integrity_check e o comando do proprio SQLite que varre o
    arquivo procurando corrupcao. Ele responde a unica linha "ok" quando
    esta tudo certo.
    """
    if not Path(caminho).is_file():
        return False, f"o arquivo {caminho} nao existe"

    try:
        conexao = _abrir_somente_leitura(caminho)
        try:
            resultado = conexao.execute("PRAGMA integrity_check").fetchall()
            if resultado != [("ok",)]:
                return False, f"o integrity_check do SQLite reportou problema: {resultado[:3]}"

            tabela_editais = conexao.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'editais'"
            ).fetchone()
            if tabela_editais is None:
                return False, "o arquivo e um banco SQLite valido, mas nao tem a tabela editais"
        finally:
            conexao.close()
    except sqlite3.DatabaseError as erro:
        return False, f"o arquivo nao abre como banco SQLite: {erro}"

    return True, "ok"


def decidir_se_pode_publicar(quantidade_local, quantidade_remota, permitir_reducao=False):
    """Decide se o banco local pode ser publicado por cima do banco remoto
    (o que esta na branch "data"). Devolve (pode_publicar, motivo).

    quantidade_remota e None quando ainda nao existe banco remoto
    (primeira publicacao).

    A aplicacao nunca apaga editais (so itens, numa regra futura de 60
    dias), entao a contagem de editais nunca pode cair de uma execucao pra
    outra. Se caiu, algo deu errado (banco restaurado errado, arquivo
    novo no lugar do antigo...) e publicar por cima apagaria o historico.

    permitir_reducao e a valvula de escape pra uma reducao deliberada
    (ex.: limpeza de editais feita de proposito). Ela NAO libera banco
    vazio: publicar um banco vazio nunca e intencional.
    """
    if quantidade_local == 0:
        return False, "o banco local esta vazio (0 editais), publicar apagaria o historico"

    if quantidade_remota is not None and quantidade_local < quantidade_remota:
        if not permitir_reducao:
            return False, (
                f"o banco local tem menos editais ({quantidade_local}) que o remoto "
                f"({quantidade_remota}), publicar apagaria historico"
            )
        return True, (
            f"reducao permitida de proposito: {quantidade_remota} -> {quantidade_local} editais"
        )

    return True, "ok"
