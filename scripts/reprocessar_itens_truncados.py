"""
Script auxiliar (roda sob demanda, nao faz parte da captura diaria).

Contexto (Fase 0.5): a busca de itens antes pedia a API sem dizer quantos
itens queria, e a API devolvia so os 10 primeiros. Resultado: editais com
mais de 10 itens ficaram salvos com exatamente 10. A busca ja foi corrigida
(captura/pncp_client.py), mas editais que ja estavam no banco e "sem mudanca"
nao tem os itens regravados na captura diaria, entao precisam ser buscados
de novo uma vez.

Este script pega todo edital ainda ABERTO (prazo da proposta no futuro) que
tem exatamente 10 itens salvos, ou nenhum item salvo, busca os itens de
novo na API e, so se pedido com --gravar, grava no banco.

Por padrao NAO grava nada (modo "dry-run", ensaio): so busca na API e mostra
o que faria. Pra cada edital, mostra tambem se, olhando os itens completos,
apareceria algum segmento que o edital hoje nao tem. Isso e so informacao na
tela: este script nunca reclassifica o edital (nunca mexe na coluna
segmentos) e nunca envia e-mail.

Seguro rodar mais de uma vez: banco.salvar_itens faz upsert pela chave
composta (numero_controle_pncp + numero_item), entao nunca duplica e nunca
apaga item nenhum.

Como rodar (com o venv ja ativado, na pasta do projeto):
    python scripts/reprocessar_itens_truncados.py                       # ensaio, nao grava
    python scripts/reprocessar_itens_truncados.py --gravar              # grava de verdade
    python scripts/reprocessar_itens_truncados.py --banco outro.db      # usa outro arquivo de banco
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_DO_PROJETO))

from captura import banco, filtro, pncp_client

CAMINHO_KEYWORDS = RAIZ_DO_PROJETO / "config" / "keywords.yaml"

# Quantidade de itens que a busca antiga deixava salva (o corte da API).
QUANTIDADE_TRUNCADA = 10


def buscar_editais_para_reprocessar(conexao):
    """Devolve os editais abertos (prazo da proposta depois de agora) que
    tem exatamente QUANTIDADE_TRUNCADA itens salvos, ou nenhum. Cada edital
    vem como dicionario, ja com a quantidade de itens salvos hoje.

    A contagem de itens e feita pelo proprio banco, numa sub-consulta
    (SELECT dentro do SELECT): pra cada edital, conta quantas linhas
    existem em itens_edital com o mesmo numero_controle_pncp.
    """
    agora = datetime.now().isoformat()
    cursor = conexao.execute(
        """
        SELECT
            e.numero_controle_pncp, e.link_pncp, e.segmentos, e.municipio, e.uf,
            (SELECT COUNT(*) FROM itens_edital i
              WHERE i.numero_controle_pncp = e.numero_controle_pncp) AS qtd_itens
        FROM editais e
        WHERE e.data_encerramento_proposta > ?
        ORDER BY e.data_encerramento_proposta
        """,
        (agora,),
    )
    editais_abertos = [dict(linha) for linha in cursor.fetchall()]
    return [e for e in editais_abertos if e["qtd_itens"] in (QUANTIDADE_TRUNCADA, 0)]


def segmentos_que_batem_nos_itens(itens, config):
    """Aplica as mesmas regras do keywords.yaml na descricao de cada item e
    devolve {nome_do_segmento: numero_do_primeiro_item_em_que_bateu}.

    O filtro.avaliar_edital espera um objeto com os campos "objeto" e
    "informacao_complementar". SimpleNamespace (do proprio Python) e so uma
    caixinha onde a gente coloca esses dois campos com o valor que quiser:
    aqui, a descricao do item no lugar do objeto do edital.
    """
    achados = {}
    for item in itens:
        item_como_edital = SimpleNamespace(objeto=item.get("descricao"), informacao_complementar=None)
        for match in filtro.avaliar_edital(item_como_edital, config):
            achados.setdefault(match["segmento"], item["numero_item"])
    return achados


def descrever_segmentos_novos(edital, itens, itens_salvos_antes, config):
    """Compara os segmentos que aparecem nos itens completos com os que o
    edital ja tem salvos. Devolve uma lista de textos, um por segmento novo,
    marcando se ele so aparece nos itens que estavam cortados (alem dos 10
    que ja estavam salvos) ou se ja aparecia nos 10 primeiros.
    """
    segmentos_salvos = {match["segmento"] for match in json.loads(edital["segmentos"] or "[]")}
    numeros_ja_salvos = {item["numero_item"] for item in itens_salvos_antes}

    em_todos_os_itens = segmentos_que_batem_nos_itens(itens, config)
    nos_itens_antigos = segmentos_que_batem_nos_itens(
        [item for item in itens if item["numero_item"] in numeros_ja_salvos], config
    )

    descricoes = []
    for segmento, numero_do_item in em_todos_os_itens.items():
        if segmento in segmentos_salvos:
            continue
        if segmento in nos_itens_antigos:
            origem = "ja aparecia nos 10 primeiros itens"
        else:
            origem = "SO nos itens que estavam cortados"
        descricoes.append(f"{segmento} (item {numero_do_item}, {origem})")
    return descricoes


def reprocessar(caminho_banco, gravar):
    if not Path(caminho_banco).exists():
        # banco.conectar cria um arquivo vazio se o caminho nao existe, o
        # que mascararia um erro de digitacao no caminho. Melhor parar aqui.
        print(f"Banco nao encontrado: {caminho_banco}")
        return

    config = filtro.carregar_keywords(str(CAMINHO_KEYWORDS))
    conexao = banco.conectar(caminho_banco)
    editais = buscar_editais_para_reprocessar(conexao)

    modo = "GRAVANDO no banco" if gravar else "ENSAIO (dry-run), nada sera gravado"
    print(f"{modo}. Banco: {caminho_banco}")
    print(f"{len(editais)} edital(is) aberto(s) com {QUANTIDADE_TRUNCADA} itens salvos ou nenhum.\n")

    com_itens_novos = 0
    com_segmento_novo = 0
    com_segmento_novo_so_nos_cortados = 0
    falharam = 0

    for indice, edital in enumerate(editais):
        if indice > 0:
            time.sleep(pncp_client.PAUSA_ENTRE_CHAMADAS_SEGUNDOS)

        numero = edital["numero_controle_pncp"]
        cnpj, ano, sequencial = pncp_client.extrair_cnpj_ano_sequencial(edital["link_pncp"])
        itens = pncp_client.buscar_itens_da_compra(cnpj, ano, sequencial)

        if itens is None:
            falharam += 1
            print(f"- {numero} [{edital['municipio']}/{edital['uf']}]: FALHOU ao buscar itens, nada alterado")
            continue

        itens_salvos_antes = banco.consultar_itens_do_edital(conexao, numero)
        antes, depois = edital["qtd_itens"], len(itens)

        if depois > antes:
            com_itens_novos += 1
            situacao_dos_itens = f"{antes} -> {depois} itens"
        elif depois == antes:
            situacao_dos_itens = f"continua com {depois} (a API confirma que tem {depois} mesmo)"
        else:
            # nao deveria acontecer: a API devolveu MENOS do que ja temos salvo
            situacao_dos_itens = f"ATENCAO: {antes} salvos, mas a API devolveu so {depois}"

        segmentos_novos = descrever_segmentos_novos(edital, itens, itens_salvos_antes, config)
        if segmentos_novos:
            com_segmento_novo += 1
            if any("SO nos itens" in texto for texto in segmentos_novos):
                com_segmento_novo_so_nos_cortados += 1

        print(f"- {numero} [{edital['municipio']}/{edital['uf']}]: {situacao_dos_itens}")
        for texto in segmentos_novos:
            print(f"    segmento novo com itens completos: {texto}")

        if gravar:
            banco.salvar_itens(conexao, numero, itens)

    conexao.close()

    print(f"\nResumo ({'gravado' if gravar else 'ensaio, nada gravado'}):")
    print(f"- {len(editais)} edital(is) na lista; {falharam} falharam na busca")
    print(f"- {com_itens_novos} ganharam itens (tinham itens cortados)")
    print(f"- {com_segmento_novo} teriam algum segmento novo olhando os itens completos")
    print(f"- {com_segmento_novo_so_nos_cortados} teriam segmento novo SO por causa dos itens que estavam cortados")
    print("(esses segmentos novos sao so informacao: este script nao reclassifica nada)")


def main():
    parser = argparse.ArgumentParser(
        description="Busca de novo os itens dos editais abertos que ficaram com 10 itens (ou nenhum)."
    )
    parser.add_argument(
        "--banco", default=banco.CAMINHO_BANCO_PADRAO,
        help=f"caminho do arquivo de banco (padrao: {banco.CAMINHO_BANCO_PADRAO})",
    )
    parser.add_argument(
        "--gravar", action="store_true",
        help="grava os itens no banco (sem isso, e so um ensaio que nao grava nada)",
    )
    argumentos = parser.parse_args()

    reprocessar(argumentos.banco, argumentos.gravar)


if __name__ == "__main__":
    main()
