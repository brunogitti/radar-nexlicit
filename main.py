"""
Ponto de entrada do Radar NexLicit. Junta captura (pncp_client) + filtro
de palavra-chave (filtro.py), itera pelos municipios ativos do
config/municipios.csv, busca o selo ME/EPP dos editais que bateram, e
salva o resultado em dados/.

Como rodar (com o venv ativado):
    python main.py --dias 7
    python main.py --dias 7 --municipio Votuporanga
    python main.py --dias 7 --segmento Limpeza
    python main.py --dias 7 --dry-run
    python main.py --dias 7 --incluir-vistos
    python main.py --dias 30 --testar-termo "cesta basica"
    python main.py --historico --dias 90 --segmento Limpeza --municipio Votuporanga
    python main.py --dias 7 --enviar-email seuemail@gmail.com
"""

import argparse
import csv
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from captura import banco, filtro, pncp_client
from captura.apresentacao import formatar_selo_me_epp, formatar_status, formatar_valor
from captura.normalizacao import normalizar_texto, termo_bate_no_texto
from entrega import email_sender, resumo

logger = logging.getLogger("main")

CAMINHO_MUNICIPIOS = "config/municipios.csv"
CAMINHO_KEYWORDS = "config/keywords.yaml"
PASTA_DADOS = Path("dados")

# Pausa entre um municipio e outro. Descobrimos rodando de verdade que
# bater a API 142 vezes em sequencia, sem pausa nenhuma, gera bastante
# erro 429 (limite de requisicoes), mesmo o limite nao sendo documentado
# em lugar nenhum. Essa pausa e uma prevencao, nao uma garantia.
PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS = 1.5


def configurar_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def carregar_municipios_ativos(caminho=CAMINHO_MUNICIPIOS, filtro_municipio=None):
    """Le o municipios.csv e devolve so os municipios com ativo=sim.

    Se filtro_municipio for informado, devolve so o municipio cujo nome
    bate (comparando normalizado, sem acento/maiuscula) com o texto pedido.
    """
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    ativos = [linha for linha in linhas if linha["ativo"].strip().lower() == "sim"]

    if filtro_municipio:
        alvo_normalizado = normalizar_texto(filtro_municipio)
        ativos = [linha for linha in ativos if normalizar_texto(linha["municipio"]) == alvo_normalizado]

    return ativos


def capturar_editais(municipios, dias):
    """Busca os editais de cada municipio. Se um municipio falhar (depois
    das tentativas do pncp_client), registra o erro e segue para os
    proximos, em vez de derrubar a execucao inteira.
    """
    todos_os_editais = []

    for indice, municipio in enumerate(municipios):
        if indice > 0:
            time.sleep(PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS)

        try:
            editais_do_municipio = pncp_client.buscar_contratacoes_com_proposta_aberta(
                municipio["codigo_ibge"], dias_janela=dias
            )
        except Exception as erro:
            logger.error(
                "Falhei ao buscar editais de %s/%s, pulando este municipio: %s",
                municipio["municipio"], municipio["uf"], erro,
            )
            continue

        todos_os_editais.extend(editais_do_municipio)

    return todos_os_editais


def aplicar_filtro_de_palavras_chave(editais, config, filtro_segmento=None):
    """Marca cada edital com os segmentos que bateram e descarta quem nao
    bateu em nenhum. Se filtro_segmento for informado, mantem so os
    editais que bateram naquele segmento especifico.
    """
    editais_filtrados = []

    for edital in editais:
        matches = filtro.avaliar_edital(edital, config)
        if not matches:
            continue

        edital.segmentos = matches

        if filtro_segmento:
            alvo_normalizado = normalizar_texto(filtro_segmento)
            bateu_no_segmento_pedido = any(
                normalizar_texto(match["segmento"]) == alvo_normalizado for match in matches
            )
            if not bateu_no_segmento_pedido:
                continue

        editais_filtrados.append(edital)

    return editais_filtrados


def testar_termo(termo, editais, config):
    """Verifica quantos editais JA CAPTURADOS (abertos agora) bateriam com
    um termo ad-hoc, sem precisar cadastrar ele no keywords.yaml antes.

    Versao simples da Tarefa 1.7 (decisao do Bruno): olha so pro que esta
    aberto agora, reaproveitando a mesma captura do fluxo principal. Nao
    cobre editais ja encerrados dos ultimos N dias, isso ficou registrado
    no plano como melhoria futura (exigiria outro endpoint da API, com
    modalidade obrigatoria e bem mais chamadas).
    """
    min_radical = config["config"]["min_radical"]

    return [
        edital for edital in editais
        if termo_bate_no_texto(termo, filtro.montar_texto_do_edital(edital, config), min_radical)
    ]


def buscar_selo_me_epp(editais):
    """So chama o endpoint de itens (mais lento, um por edital) para os
    editais que ja passaram no filtro de palavra-chave.
    """
    for edital in editais:
        edital.beneficios_itens = pncp_client.buscar_beneficios_da_compra(
            edital.cnpj_orgao, edital.ano_compra, edital.sequencial_compra
        )
    return editais


def imprimir_resumo(editais_classificados):
    print(f"\n{len(editais_classificados)} edital(is) encontrado(s):\n")

    for edital, status, linha_anterior in editais_classificados:
        segmentos_texto = "; ".join(
            f"{match['segmento']} (bateu em: {', '.join(match['termos'])})" for match in edital.segmentos
        )
        valor_texto = formatar_valor(edital.valor_estimado)
        selo = formatar_selo_me_epp(edital.beneficios_itens)

        print(f"- [{formatar_status(edital, status, linha_anterior)}] [{edital.municipio}/{edital.uf}] {edital.orgao}")
        print(f"  Modalidade: {edital.modalidade}")
        print(f"  Objeto: {edital.objeto}")
        print(f"  Valor estimado: {valor_texto}")
        print(f"  Prazo da proposta: {edital.data_encerramento_proposta:%d/%m/%Y %Hh%M}")
        print(f"  Segmento: {segmentos_texto}")
        if selo:
            print(f"  Selo: {selo}")
        print(f"  Link: {edital.link_pncp}")
        print()


def salvar_resultados(editais_classificados):
    PASTA_DADOS.mkdir(exist_ok=True)
    agora = datetime.now().strftime("%Y%m%d_%H%M%S")

    caminho_json = PASTA_DADOS / f"editais_{agora}.json"
    with open(caminho_json, "w", encoding="utf-8") as arquivo:
        json.dump(
            [{**asdict(edital), "status": status} for edital, status, _linha in editais_classificados],
            arquivo, ensure_ascii=False, indent=2, default=str,
        )

    caminho_csv = PASTA_DADOS / f"editais_{agora}.csv"
    campos_do_csv = [
        "status", "numero_controle_pncp", "orgao", "municipio", "uf", "modalidade",
        "objeto", "valor_estimado", "data_encerramento_proposta",
        "segmentos", "selo_me_epp", "link_pncp",
    ]
    with open(caminho_csv, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos_do_csv)
        escritor.writeheader()

        for edital, status, _linha in editais_classificados:
            segmentos_texto = "; ".join(
                f"{match['segmento']} ({', '.join(match['termos'])})" for match in edital.segmentos
            )
            escritor.writerow({
                "status": status,
                "numero_controle_pncp": edital.numero_controle_pncp,
                "orgao": edital.orgao,
                "municipio": edital.municipio,
                "uf": edital.uf,
                "modalidade": edital.modalidade,
                "objeto": edital.objeto,
                "valor_estimado": edital.valor_estimado,
                "data_encerramento_proposta": edital.data_encerramento_proposta,
                "segmentos": segmentos_texto,
                "selo_me_epp": formatar_selo_me_epp(edital.beneficios_itens) or "",
                "link_pncp": edital.link_pncp,
            })

    logger.info("Salvo em %s e %s", caminho_json, caminho_csv)


def filtrar_historico(linhas, municipio=None, segmento=None):
    """Filtra as linhas que banco.consultar_historico devolveu, por
    municipio e/ou segmento. Comparacao normalizada (sem acento/maiuscula),
    igual ao resto do programa, reaproveitando normalizar_texto.
    """
    if municipio:
        alvo = normalizar_texto(municipio)
        linhas = [linha for linha in linhas if normalizar_texto(linha["municipio"]) == alvo]

    if segmento:
        alvo = normalizar_texto(segmento)
        linhas = [
            linha for linha in linhas
            if any(normalizar_texto(match["segmento"]) == alvo for match in linha["segmentos"])
        ]

    return linhas


def imprimir_historico(linhas, dias):
    periodo = f"nos ultimos {dias} dia(s)" if dias is not None else "em todo o historico"
    print(f"\n{len(linhas)} edital(is) visto(s) {periodo}:\n")

    for linha in linhas:
        segmentos_texto = "; ".join(
            f"{match['segmento']} (bateu em: {', '.join(match['termos'])})" for match in linha["segmentos"]
        )
        prazo = datetime.fromisoformat(linha["data_encerramento_proposta"])
        visto_em = datetime.fromisoformat(linha["visto_em"])

        print(f"- [{linha['municipio']}/{linha['uf']}] {linha['orgao']}")
        print(f"  Objeto: {linha['objeto']}")
        print(f"  Segmento: {segmentos_texto}")
        print(f"  Prazo da proposta: {prazo:%d/%m/%Y %Hh%M}")
        print(f"  Visto pela primeira vez em: {visto_em:%d/%m/%Y %Hh%M}")
        print(f"  Link: {linha['link_pncp']}")
        print()


def main():
    configurar_logging()

    parser = argparse.ArgumentParser(
        description="Radar NexLicit: captura editais do PNCP com proposta em aberto."
    )
    parser.add_argument("--dias", type=int, default=90, help="quantos dias a frente olhar (default: 90)")
    parser.add_argument("--municipio", help="filtra so por este municipio")
    parser.add_argument("--segmento", help="filtra so por este segmento")
    parser.add_argument("--dry-run", action="store_true", help="nao salva nada (nem arquivo, nem banco), so mostra na tela")
    parser.add_argument(
        "--incluir-vistos", action="store_true",
        help="mostra tambem os editais ja vistos sem mudanca, nao so os novos/atualizados",
    )
    parser.add_argument(
        "--testar-termo",
        help="nao aplica o keywords.yaml inteiro, so testa quantos editais abertos agora bateriam com esse termo",
    )
    parser.add_argument(
        "--historico", action="store_true",
        help="nao bate na API do PNCP, so consulta o banco local (--dias aqui vira 'vistos nos ultimos N dias')",
    )
    parser.add_argument(
        "--enviar-email",
        help="manda um e-mail com os editais novos/atualizados para este endereco (nao envia se nao houver nenhum novo, nem em --dry-run)",
    )
    argumentos = parser.parse_args()

    if argumentos.historico:
        conexao_banco = banco.conectar()
        linhas = banco.consultar_historico(conexao_banco, dias=argumentos.dias)
        linhas = filtrar_historico(linhas, municipio=argumentos.municipio, segmento=argumentos.segmento)
        imprimir_historico(linhas, argumentos.dias)
        conexao_banco.close()
        return

    municipios = carregar_municipios_ativos(filtro_municipio=argumentos.municipio)
    if argumentos.municipio and not municipios:
        logger.warning("Nenhum municipio ativo encontrado com o nome '%s'", argumentos.municipio)
    logger.info("%s municipio(s) ativo(s) para buscar", len(municipios))

    config_keywords = filtro.carregar_keywords(CAMINHO_KEYWORDS)

    editais_brutos = capturar_editais(municipios, argumentos.dias)
    logger.info("%s edital(is) com proposta em aberto, antes do filtro de palavra-chave", len(editais_brutos))

    if argumentos.testar_termo:
        editais_que_bateriam = testar_termo(argumentos.testar_termo, editais_brutos, config_keywords)
        print(
            f"\n'{argumentos.testar_termo}' bateria em {len(editais_que_bateriam)} de "
            f"{len(editais_brutos)} edital(is) aberto(s) agora (proximos {argumentos.dias} dias):\n"
        )
        for edital in editais_que_bateriam:
            print(f"- [{edital.municipio}/{edital.uf}] {edital.objeto}")
        return

    editais_filtrados = aplicar_filtro_de_palavras_chave(editais_brutos, config_keywords, argumentos.segmento)
    logger.info("%s edital(is) bateram no filtro de palavra-chave", len(editais_filtrados))

    editais_filtrados = buscar_selo_me_epp(editais_filtrados)

    conexao_banco = banco.conectar()
    editais_classificados = banco.classificar(conexao_banco, editais_filtrados)

    if not argumentos.incluir_vistos:
        editais_classificados = [item for item in editais_classificados if item[1] != "sem_mudanca"]

    imprimir_resumo(editais_classificados)

    if not argumentos.dry_run and editais_classificados:
        banco.salvar(conexao_banco, editais_classificados)
        salvar_resultados(editais_classificados)

    if argumentos.enviar_email and not argumentos.dry_run:
        # so entra no e-mail quem e novo/atualizado, mesmo que --incluir-vistos
        # tenha trazido tambem quem esta sem mudanca pra tela
        editais_para_email = [item for item in editais_classificados if item[1] != "sem_mudanca"]

        if editais_para_email:
            assunto = f"Radar NexLicit: {len(editais_para_email)} edital(is) novo(s) - {datetime.now():%d/%m/%Y}"
            corpo_html = resumo.montar_corpo_html(editais_para_email)
            email_sender.enviar_email(argumentos.enviar_email, assunto, corpo_html)
        else:
            logger.info("Nenhum edital novo/atualizado, e-mail nao enviado")

    conexao_banco.close()


if __name__ == "__main__":
    main()
