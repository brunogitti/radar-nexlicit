"""
Este modulo le o config/keywords.yaml e decide quais segmentos (e quais
termos especificos) batem no texto de um edital. Nao sabe como o edital
chegou ate aqui (se veio de uma chamada HTTP, de um arquivo, etc), so
sabe aplicar as regras num objeto Edital ja pronto (ver modelos.py).
"""

import yaml

from .normalizacao import termo_bate_no_texto

# Nome do campo no keywords.yaml (campos_analisados) -> nome do atributo
# correspondente no objeto Edital. So esses dois sao suportados por
# enquanto, porque sao os dois campos de texto livre que a API do PNCP
# devolve (confirmado na Tarefa 1.0).
CAMPOS_SUPORTADOS = {
    "objetoCompra": "objeto",
    "informacaoComplementar": "informacao_complementar",
}


class ErroConfiguracaoYAML(Exception):
    """Erro usado quando o keywords.yaml esta com uma estrutura invalida."""


def carregar_keywords(caminho="config/keywords.yaml"):
    """Le e valida o keywords.yaml.

    Levanta ErroConfiguracaoYAML com uma mensagem apontando o segmento e a
    regra problematicos se algo estiver escrito errado (por exemplo, uma
    regra sem 'termos'), em vez de deixar o programa quebrar mais adiante
    com um KeyError generico e dificil de entender.
    """
    with open(caminho, encoding="utf-8") as arquivo:
        config = yaml.safe_load(arquivo)

    _validar_config(config)
    return config


def _validar_config(config):
    for chave_obrigatoria in ("config", "segmentos", "exclusoes_globais"):
        if chave_obrigatoria not in config:
            raise ErroConfiguracaoYAML(
                f"O keywords.yaml precisa ter a chave '{chave_obrigatoria}' no nivel principal."
            )

    if not config["segmentos"]:
        raise ErroConfiguracaoYAML("O keywords.yaml precisa ter pelo menos um segmento em 'segmentos'.")

    for indice_segmento, segmento in enumerate(config["segmentos"], start=1):
        nome_segmento = segmento.get("nome")
        if not nome_segmento:
            raise ErroConfiguracaoYAML(
                f"O segmento #{indice_segmento} do keywords.yaml nao tem a chave 'nome'."
            )

        regras = segmento.get("regras")
        if not regras:
            raise ErroConfiguracaoYAML(
                f"O segmento '{nome_segmento}' do keywords.yaml nao tem nenhuma regra em 'regras'."
            )

        for indice_regra, regra in enumerate(regras, start=1):
            termos = regra.get("termos")
            if not termos:
                raise ErroConfiguracaoYAML(
                    f"No segmento '{nome_segmento}', a regra #{indice_regra} nao tem "
                    "nenhum termo em 'termos'."
                )


def montar_texto_do_edital(edital, config):
    """Junta os campos que o campos_analisados do keywords.yaml pede
    (hoje, objeto + informacao_complementar) num texto so, pronto pra
    comparar com um termo. Publica porque tambem e usada pelo comando
    --testar-termo do main.py (Tarefa 1.7), nao so pelo avaliar_edital.
    """
    campos_analisados = config["config"]["campos_analisados"]
    partes = []

    for campo_yaml in campos_analisados:
        nome_atributo = CAMPOS_SUPORTADOS.get(campo_yaml)
        if nome_atributo is None:
            raise ErroConfiguracaoYAML(
                f"O keywords.yaml pede o campo '{campo_yaml}' em campos_analisados, mas "
                f"esse campo nao existe no Edital. Campos aceitos: {', '.join(CAMPOS_SUPORTADOS)}."
            )
        valor = getattr(edital, nome_atributo) or ""
        partes.append(valor)

    return " ".join(partes)


def _regra_bate(termos, excluir, texto, min_radical):
    """Devolve a lista de termos que bateram se a regra inteira bateu
    (todos os termos obrigatorios apareceram e nenhum termo de excluir
    apareceu), ou None se a regra nao bateu.
    """
    termos_que_bateram = [termo for termo in termos if termo_bate_no_texto(termo, texto, min_radical)]

    todos_os_termos_bateram = len(termos_que_bateram) == len(termos)
    if not todos_os_termos_bateram:
        return None

    for termo_excluido in excluir or []:
        if termo_bate_no_texto(termo_excluido, texto, min_radical):
            return None

    return termos_que_bateram


def avaliar_edital(edital, config):
    """Aplica todas as regras do keywords.yaml no texto do edital.

    Devolve uma lista de dicionarios no formato
    {"segmento": "Limpeza", "termos": ["material", "limpeza"]}, um para
    cada segmento que bateu (um edital pode bater em mais de um segmento).

    Lista vazia significa "nenhum segmento bateu", seja porque nenhuma
    regra casou, seja porque um termo de exclusoes_globais derrubou o
    edital inteiro.
    """
    min_radical = config["config"]["min_radical"]
    texto = montar_texto_do_edital(edital, config)

    for termo_proibido in config["exclusoes_globais"]:
        if termo_bate_no_texto(termo_proibido, texto, min_radical):
            return []

    matches = []
    for segmento in config["segmentos"]:
        termos_do_segmento_que_bateram = []

        for regra in segmento["regras"]:
            resultado = _regra_bate(regra["termos"], regra.get("excluir"), texto, min_radical)
            if resultado is not None:
                termos_do_segmento_que_bateram.extend(resultado)

        if termos_do_segmento_que_bateram:
            # dict.fromkeys(lista) tira duplicata mantendo a ordem original,
            # caso duas regras do mesmo segmento compartilhem um termo
            termos_unicos = list(dict.fromkeys(termos_do_segmento_que_bateram))
            matches.append({"segmento": segmento["nome"], "termos": termos_unicos})

    return matches
