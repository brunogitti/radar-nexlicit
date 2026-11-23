# Operação do banco de dados (branches data e backups)

Este documento explica como o banco `dados/radar.db` é guardado entre uma execução e outra do workflow "Captura diaria", o que o workflow bloqueia de propósito, e como recuperar o banco se algo der errado. Qualquer restauração manual só acontece com a aprovação do Bruno (protocolo de banco).

## Como funciona

O workflow roda duas vezes por dia (7h e 13h, horário de Brasília) e, em cada execução:

1. **Restaura** o banco da branch `data` (script `.github/scripts/restaurar_banco.sh`).
2. Roda os testes, captura os editais e envia o e-mail.
3. **Publica** o banco atualizado (script `.github/scripts/publicar_banco.sh`).

A branch `data` guarda um commit só, com o código da `master` mais o arquivo `dados/radar.db`. É recriada do zero a cada execução. O painel público lê o banco dela.

A branch `backups` guarda os **7 backups mais recentes**, um arquivo `radar-AAAAMMDD-HHMMSS.db.gz` por execução (horário UTC, compactado com gzip). Cada backup é uma cópia do banco **como estava antes** daquela execução, ou seja, o estado em que a execução anterior terminou. Com duas execuções por dia, os 7 backups cobrem cerca de 3 dias e meio. Para guardar mais, basta mudar `QUANTIDADE_DE_BACKUPS` em `publicar_banco.sh`.

## O que o workflow bloqueia (o job fica vermelho e o GitHub avisa por e-mail)

Na hora de restaurar:

| Situação | O que acontece |
|---|---|
| Não deu para falar com o GitHub (rede, instabilidade) | Tenta 4 vezes (esperas de 10, 30 e 60 s). Se não der, falha. Nada é apagado. |
| A branch `data` existe, mas o banco dela está estragado ou ausente | Falha e pede restauração manual. |
| A branch `data` **não existe** e a `backups` **tem arquivos** | Falha e pede restauração manual. Nem o input `permitir_inicio_do_zero` libera esse caso. |
| Nem `data` nem `backups` existem, e o input `permitir_inicio_do_zero` está desligado | Falha. |
| Nem `data` nem `backups` existem, e o input `permitir_inicio_do_zero` está ligado | Começa do zero (só para a primeira execução de todas). |

Na hora de publicar:

| Situação | O que acontece |
|---|---|
| Banco local ausente, corrompido ou **vazio** | Bloqueia. Nada é publicado. |
| Banco local com **menos editais** que o banco da branch `data` | Bloqueia. A aplicação nunca apaga editais, então essa contagem nunca pode cair. |
| O backup não pôde ser enviado | Bloqueia. O banco novo não é publicado sem backup. |
| Falha de rede ao enviar `backups` ou `data` | Tenta 4 vezes (10, 30 e 60 s). Se não der, falha, e o banco anterior continua intacto. |

Duas execuções nunca rodam ao mesmo tempo: a segunda espera a primeira terminar (`concurrency` no workflow).

Um aviso importante: o e-mail da captura sai **antes** da publicação. Se a publicação for bloqueada ou falhar, a próxima execução vai achar esses mesmos editais "novos" e reenviar o e-mail. Por isso a verificação de banco duvidoso acontece no começo do job (restaurar), antes de capturar e enviar qualquer coisa.

## Inputs do disparo manual

Em Actions, "Captura diaria", "Run workflow":

- `permitir_inicio_do_zero`: só para a primeira execução de todas. Deixe desligado.
- `permitir_reducao_do_banco`: só se o banco novo tiver menos editais de propósito (por exemplo, uma limpeza). Nunca libera banco vazio.
- `reprocessar_itens_truncados`: roda uma vez, a mão, depois de restaurar e antes da captura. Busca de novo os itens dos editais abertos que ficaram com exatamente 10 itens (ou nenhum) e grava no banco (`scripts/reprocessar_itens_truncados.py --gravar`). Não reclassifica e não envia e-mail. Passa pelas mesmas conferências de publicação (backup antes, banco não pode encolher).

## Como restaurar um backup (só com aprovação do Bruno)

Rode no Git Bash, na pasta do projeto.

1. Veja os backups disponíveis (do mais antigo para o mais novo):

   ```
   git fetch origin backups
   git ls-tree --name-only FETCH_HEAD
   ```

2. Baixe e descompacte o que você escolheu (troque o nome pelo do arquivo):

   ```
   git show FETCH_HEAD:radar-20261119-130712.db.gz > radar_restaurado.db.gz
   gzip -d radar_restaurado.db.gz
   ```

3. Confira que o banco está inteiro e quantos editais tem:

   ```
   python .github/scripts/verificar_banco.py integridade radar_restaurado.db
   python .github/scripts/verificar_banco.py contar radar_restaurado.db
   ```

4. Para voltar esse banco à produção, publique-o na branch `data` (isto sobrescreve a `data`):

   ```
   git switch -c restaura-banco master
   mkdir -p dados
   cp radar_restaurado.db dados/radar.db
   git add -f dados/radar.db
   git commit -m "Restaura banco do backup radar-20261119-130712"
   git push --force origin restaura-banco:data
   git switch master
   git branch -D restaura-banco
   ```

5. Rode o workflow manualmente para conferir que ele restaura o banco normalmente.

Se a branch `data` foi apagada e a `backups` também (nenhum backup disponível), não há o que restaurar: a única saída é uma primeira execução do zero, com `permitir_inicio_do_zero` ligado, e isso perde o histórico de "já vistos" (os editais abertos seriam reenviados por e-mail como novos).
