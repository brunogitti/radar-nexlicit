"""
Este modulo so transforma texto: tira acento, deixa minusculo, tira
pontuacao, e decide se um termo do keywords.yaml "bate" num texto de
edital. Nao sabe nada sobre HTTP nem sobre segmento, so sabe comparar
duas strings.
"""

import re
import unicodedata


def normalizar_texto(texto):
    """Prepara um texto para comparacao: minusculo, sem acento, sem
    pontuacao, espacos multiplos viram um espaco so.

    unicodedata.normalize('NFKD', texto) separa cada letra acentuada em
    duas partes (a letra e o acento, como um caractere a parte). Depois
    disso, descartamos qualquer caractere que unicodedata.combining()
    reconhece como um desses acentos, sobrando so a letra sem acento.
    """
    if texto is None:
        return ""

    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))

    # troca qualquer caractere que nao seja letra, numero ou espaco por um
    # espaco (isso remove pontuacao: virgula, ponto, parenteses, etc)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)

    # colapsa espacos multiplos (incluindo os que a troca de pontuacao acima
    # pode ter criado) num espaco so, e tira espaco do inicio/fim
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def termo_bate_no_texto(termo, texto, min_radical=5):
    """Verifica se um termo aparece no texto, ja cuidando da normalizacao
    dos dois lados.

    Termos com min_radical caracteres ou mais casam por PREFIXO de palavra:
    "camiset" bate "camiseta" e "camisetas", porque pega variacao e plural.
    Termos mais curtos que isso exigem a PALAVRA INTEIRA: "cabo" (4 letras,
    menor que o min_radical de 5) so bate a palavra "cabo" sozinha, nunca
    como prefixo, senao bateria dentro de "cabotagem".

    Termos compostos por mais de uma palavra (ex.: "agua sanitaria") exigem
    a frase exata, sem essa flexibilidade de prefixo.
    """
    termo_normalizado = normalizar_texto(termo)
    texto_normalizado = normalizar_texto(texto)

    if not termo_normalizado or not texto_normalizado:
        return False

    termo_tem_mais_de_uma_palavra = " " in termo_normalizado
    if termo_tem_mais_de_uma_palavra:
        # cerca o texto com espacos para nao casar um pedaco de frase que
        # comeca ou termina no meio de uma palavra
        return f" {termo_normalizado} " in f" {texto_normalizado} "

    palavras_do_texto = texto_normalizado.split(" ")

    if len(termo_normalizado) >= min_radical:
        return any(palavra.startswith(termo_normalizado) for palavra in palavras_do_texto)

    return termo_normalizado in palavras_do_texto
