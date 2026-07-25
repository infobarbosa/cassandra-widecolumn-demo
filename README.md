# Wide-column com Apache Cassandra 5

Author: Prof. Barbosa<br>
Contact: infobarbosa@gmail.com<br>
Github: [infobarbosa](https://github.com/infobarbosa)

> **Esta branch está em revisão.** O laboratório em uso está na branch `main`.
> Ver o [plano de revisão](#plano-de-revisão) ao final para o que já está pronto.

[Cassandra](https://cassandra.apache.org/) é um banco de dados distribuído com modelo de armazenamento **wide-column**. Neste laboratório você vai construir uma tabela do zero, acompanhar o dado descer até o disco, descobrir o limite de consulta que o Cassandra impõe — e então ver como um sistema real resolve esse limite.

O laboratório inteiro cabe neste arquivo. Os comandos são copy-paste em terminal Linux, na ordem em que aparecem.

---

## O que você vai saber fazer ao final

- Criar keyspaces e declarar a estratégia de replicação adequada à topologia.
- Escrever `CREATE TABLE` cujo `PRIMARY KEY` responde a uma consulta específica, e explicar a diferença entre **partition key** e **clustering key**.
- Prever em qual partição uma linha vai cair, e por que a ordem física dos dados no disco é uma decisão de modelagem.
- Acompanhar o caminho de escrita — commit log, memtable, SSTable, compactação, tombstone — observando os arquivos que o Cassandra cria.
- Ler um modelo físico de verdade e dizer **qual consulta motivou cada tabela**.
- Reconhecer os erros que o Cassandra devolve e saber, para cada um, se a resposta é corrigir a consulta ou modelar outra tabela.
- Consultar o Cassandra a partir de uma aplicação Python, com prepared statements e paginação.

---

## Pré-requisitos

- **Docker** com o plugin `compose` (v2). Nada mais precisa ser instalado: o `cqlsh` e o `nodetool` vêm dentro do container.
- **Python 3** com `venv`, apenas para a Parte III.
- Cerca de **2 GB de RAM** livres e **5 GB de disco**.

Recomendo Linux. Caso não tenha um à disposição, use o **AWS Cloud9** — as instruções estão em [data-engineering-cloud9](https://github.com/infobarbosa/data-engineering-cloud9).

---

## Como o laboratório está organizado

| Parte | Assunto | Keyspace | Tempo |
|---|---|---|---|
| **I** | Fundamentos: do ambiente ao dado no disco | `lab`, criada por você | ~100 min |
| **II** | Modelagem: de sete consultas a doze tabelas | `infobarbank` | ~60 min |
| **III** | A aplicação: o mesmo fluxo em Python | `infobarbank` | ~30 min |
| **IV** | Trabalho final | `ecommerce` | — |

São três keyspaces, com papéis distintos:

- **`lab`** — sua bancada de trabalho. Você a cria na Parte I, erra nela à vontade, e apaga no final.
- **`infobarbank`** — o sistema de um banco digital, já carregado. É o caso de uso da modelagem.
- **`ecommerce`** — uma loja, também já carregada. É o **espelho** do banco: as mesmas convenções de modelagem em outro domínio. É sobre ela que o trabalho final é feito.

Ao longo de todo o laboratório os comandos são executados a partir do host, nunca de dentro do container, usando dois atalhos definidos na primeira seção:

```sh
alias cql='docker exec -it cassandra-database cqlsh -e'
alias nt='docker exec -it cassandra-database nodetool'
```

### Convenções

Nem todo bloco de código é para ser executado. Há três tipos:

| | |
|---|---|
| ```sh``` com prompt limpo | **Execute.** É o caminho do laboratório. |
| **Não execute** | Exemplo para leitura: descreve um ambiente que não é este — um cluster com vários datacenters, por exemplo. Rodar aqui só devolve erro de configuração. |
| **Provoque este erro** | Comando que falha de propósito, e a mensagem de erro é a lição. Estes você deve executar. |

A diferença entre os dois últimos importa: o Cassandra recusa consultas mal modeladas com mensagens muito informativas, e aprender a lê-las é metade do trabalho. O que não vale a pena é executar comandos que só falham porque o ambiente de estudo tem um nó.

---

## Índice

**Parte I — Fundamentos**

1. [O ambiente](#1-o-ambiente)
2. [Primeiro contato](#2-primeiro-contato)
3. [Keyspace: onde a replicação é decidida](#3-keyspace-onde-a-replicação-é-decidida)
4. [Sua primeira tabela](#4-sua-primeira-tabela)
5. [Onde o dado mora: partição e token](#5-onde-o-dado-mora-partição-e-token)
6. [Do memtable ao disco](#6-do-memtable-ao-disco)

**Parte II — Modelagem**

7. [Não existe JOIN — existe outra tabela](#7-não-existe-join--existe-outra-tabela)
8. [Chave primária na prática](#8-chave-primária-na-prática)
9. [Cassandra 5: SAI e UCS](#9-cassandra-5-sai-e-ucs)

**Parte III — A aplicação**

10. [O driver Python](#10-o-driver-python)

**Parte IV — Trabalho final**

11. [Enunciado](#11-enunciado)

**Apêndices**

- [A. Busca vetorial](#a-busca-vetorial)
- [B. Encerrando o ambiente](#b-encerrando-o-ambiente)
- [C. Troubleshooting](#c-troubleshooting)
- [D. Nota para o instrutor](#d-nota-para-o-instrutor)

---

## 1. O ambiente

Baixe o arquivo do Docker Compose:

```sh
wget https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/revisao-julho2026/compose.yaml

```

Veja o que ele descreve — um nó Cassandra e dois containers de carga, um por keyspace:

```sh
cat compose.yaml

```

Suba o ambiente:

```sh
docker compose up -d

```

```
 Network cassandra5-demo_default Created
 Container cassandra-database Creating
 Container cassandra-database Started
 Container cassandra-database Waiting
 Container cassandra-database Healthy
 Container cassandra-init-ecommerce Starting
 Container cassandra-init-infobarbank Starting
 Container cassandra-init-ecommerce Started
 Container cassandra-init-infobarbank Started
```

Repare na linha `Waiting`: o comando só retorna depois que o Cassandra passa no healthcheck, porque os containers de carga declaram `depends_on: service_healthy`. Isso leva cerca de **um minuto**. Depois disso, a carga das duas keyspaces leva outros **30 segundos** — e essa parte roda em segundo plano, então o prompt volta antes de terminar.

Para acompanhar a carga:

```sh
docker compose logs -f cassandra-init-ecommerce

```

```
cassandra-init-ecommerce  | Carregadas 11959 linhas em pedidos_por_produto (3.3s).
cassandra-init-ecommerce  | Keyspace ecommerce pronta em 25.8s. Cliente-âncora: CLI-000001.
```

> Para sair do `logs -f`, digite `Control+C` uma única vez.

### O que foi criado

```sh
docker ps -a

```

```
NAMES                        IMAGE                                        STATUS
cassandra-init-ecommerce     ...cassandra-gerador-esquema-ecommerce:2.0   Exited (0) 4 minutes ago
cassandra-init-infobarbank   ...cassandra-gerador-esquema-infobarbank:1.0 Exited (0) 4 minutes ago
cassandra-database           cassandra:5.0.8                              Up 6 minutes (healthy)
```

Os dois containers de carga aparecem como `Exited (0)`, e **é isso que se espera deles**: cada um cria a sua keyspace, insere os dados e termina. `Exited (0)` significa que terminaram sem erro. Só o `cassandra-database` fica no ar.

### Verificando o ambiente

```sh
curl -sS https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/revisao-julho2026/scripts/check.sh | bash

```

```
Keyspaces
  ✓ infobarbank: 12 tabelas (modelagem de dados)
  ✓ ecommerce: 11 tabelas (trabalho final)
  ! lab: ainda não criada — você a cria na Parte I

Dados
  ✓ infobarbank.cliente: 50 clientes
  ✓ ecommerce.pedido_detalhe: 11959 pedidos

Resultado
  Ambiente pronto.
```

Guarde este comando. Sempre que uma seção não se comportar como o texto descreve, rode-o: ele diz o que está faltando em vez de deixar você adivinhar.

### Dois atalhos

O `cqlsh` e o `nodetool` estão dentro do container, mas você **não vai entrar nele em momento algum** neste laboratório. Em vez disso, defina dois atalhos:

```sh
alias cql='docker exec -it cassandra-database cqlsh -e'
alias nt='docker exec -it cassandra-database nodetool'

```

Teste:

```sh
cql "SELECT release_version FROM system.local;"

```

```
 release_version
-----------------
           5.0.8

(1 rows)
```

> Os `alias` valem apenas para **este terminal**. Se abrir outro, ou fechar e reabrir, defina-os de novo. Se algum comando adiante devolver `cql: command not found`, é isso que aconteceu.

**→ Próxima seção.** O ambiente está no ar e duas keyspaces já foram carregadas por outra pessoa. Antes de criar as suas, vale saber o que exatamente está rodando aí.

---

## 2. Primeiro contato

### O que existe no nó

```sh
cql "DESCRIBE KEYSPACES;"

```

```
ecommerce    system_auth         system_traces
infobarbank  system_distributed  system_views
system       system_schema       system_virtual_schema
```

Duas keyspaces são do curso — `infobarbank` e `ecommerce`. As outras seis são do próprio Cassandra: `system_schema` guarda a definição das suas tabelas, `system_auth` os usuários, `system_views` e `system_virtual_schema` expõem métricas internas como se fossem tabelas. Você vai consultar algumas delas ao longo do laboratório.

### Quem é este nó

```sh
cql "SELECT cluster_name, release_version, cql_version, data_center, rack FROM system.local;"

```

```
 cluster_name   | release_version | cql_version | data_center | rack
----------------+-----------------+-------------+-------------+------
 infobarbosainc |           5.0.8 |       3.4.7 | datacenter1 | RAC1

(1 rows)
```

`system.local` é a tabela em que o nó guarda o que sabe sobre si mesmo. Note que ele se declara em um **datacenter** (`datacenter1`) e em um **rack** (`RAC1`) — nomes que vieram do `compose.yaml`. Um nó só, mas já se apresentando com endereço na topologia. Isso vai importar na próxima seção.

### O ponto de vista do operador

```sh
nt status

```

```
Datacenter: datacenter1
=======================
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address     Load        Tokens  Owns (effective)  Host ID                               Rack
UN  172.21.0.2  111.45 KiB  16      100.0%            15ae1f2b-82f9-4753-afaa-b21bc7813e4a  RAC1
```

O `Host ID`, o `Address` e o `Load` do seu ambiente serão diferentes dos que aparecem aqui — são gerados na criação do container. O que deve coincidir é o resto.

`UN` é a leitura mais frequente do dia a dia de quem opera Cassandra: **U**p e **N**ormal. A legenda logo acima do resultado explica as combinações possíveis — um nó entrando no cluster, por exemplo, aparece como `UJ` (Up, Joining).

Duas colunas para guardar: `Owns` diz que este nó responde por 100% dos dados, o que é esperado quando há um nó só; e `Tokens 16` diz que ele ocupa dezesseis posições no anel de tokens. O que são esses tokens é assunto da seção 5.

> Se o `nt status` devolver `Server is not initialized yet, cannot run nodetool`, o serviço ainda está subindo. Espere alguns segundos e repita.

### Sobre o `cqlsh`

O `cqlsh` é a linha de comando do Cassandra, e fala **CQL** (Cassandra Query Language). Ele tem dois modos:

- **Não interativo**, com `-e` ou `--execute`: executa um comando e sai. É o que o nosso `alias cql` faz, e é a forma usada em scripts de manutenção.
- **Interativo**, sem parâmetro: abre um prompt `cqlsh>` que fica aguardando comandos.

Este laboratório usa o modo não interativo do começo ao fim — assim nenhum comando depende de você estar "dentro" de algum lugar. Se quiser conhecer o modo interativo:

```sh
docker exec -it cassandra-database cqlsh

```

```
ATTENTION: All commands will be saved to history file: /root/.cassandra/cqlsh_history
This may include sensitive information such as passwords.
[...]

Connected to infobarbosainc at 127.0.0.1:9042
[cqlsh 6.2.0 | Cassandra 5.0.8 | CQL spec 3.4.7 | Native protocol v5]
Use HELP for help.
cqlsh>
```

O aviso do topo é normal: o `cqlsh` grava histórico de comandos, e o Cassandra 5 passou a alertar sobre isso porque o histórico pode conter senhas. Não é erro.

Para sair, digite `exit` ou `Control+D`.

**→ Próxima seção.** Você viu duas keyspaces prontas. Agora vai criar a sua — e a primeira decisão que o Cassandra pede não é sobre tabelas, é sobre quantas cópias do dado você quer.

---

## 3. Keyspace: onde a replicação é decidida

Uma `keyspace` é o repositório lógico das tabelas. Em outros bancos equivale a um *schema* ou *database*.

O papel importante dela, porém, é **físico**: é na keyspace que se define como o dado será replicado. Essa é a decisão que determina o que acontece com a sua aplicação quando um nó cai.

Crie a sua:

```sh
cql "
CREATE KEYSPACE lab
    WITH REPLICATION = {
        'class': 'NetworkTopologyStrategy',
        'datacenter1': 1
    };"

```

Conferindo:

```sh
cql "DESCRIBE KEYSPACE lab;"

```

```
CREATE KEYSPACE lab WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': '1'}  AND durable_writes = true;
```

### As duas estratégias

```
CREATE KEYSPACE [IF NOT EXISTS] nome_da_keyspace
   WITH REPLICATION = {
      'class' : 'SimpleStrategy', 'replication_factor' : N
    | 'class' : 'NetworkTopologyStrategy', 'nome_do_dc' : N [, ...]
   }
   [AND DURABLE_WRITES = true|false] ;
```

A `SimpleStrategy` distribui as réplicas ignorando a topologia: para ela não existem datacenters nem racks. Funciona, inclusive nesta versão, mas só faz sentido em ambiente de estudo com um nó.

Usamos `NetworkTopologyStrategy` porque é ela que permite dizer **quantas cópias em cada datacenter** — e porque é coerente com o `compose.yaml`, que configurou o nó com `GossipingPropertyFileSnitch`, `CASSANDRA_DC=datacenter1` e `CASSANDRA_RACK=RAC1`. É também a estratégia usada pelas duas keyspaces do curso.

Os nomes dos datacenters não são etiquetas livres: precisam existir na topologia declarada pelo administrador. Nomear um datacenter inexistente é recusado:

> **Não execute.** Exemplo para leitura.

```
CREATE KEYSPACE lab_erro
  WITH REPLICATION = { 'class':'NetworkTopologyStrategy', 'dc-brasil':1 };

ConfigurationException: Unrecognized strategy option {dc-brasil}
passed to NetworkTopologyStrategy for keyspace lab_erro
```

Guarde esse comportamento ao ler os exemplos a seguir: é por isso que nenhum deles roda aqui.

### Exemplos de produção

Os casos abaixo são para debate em sala.

> **Não execute.** Os três descrevem topologias com vários datacenters. Neste ambiente de um nó, todos devolveriam o `ConfigurationException` acima.

Distribuição geográfica em três países — três cópias no Brasil, três nos Estados Unidos, duas na Alemanha:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp' : 3 , // São Paulo/Brasil
   'usa-ny' : 3 , // Nova Iorque/Estados Unidos
   'deu-fr' : 2   // Frankfurt/Alemanha
  };
```

Uma região só, mas com quatro instalações em duas zonas de disponibilidade, segmentadas por propósito. Três cópias transacionais em cada zona (seis no total) e uma cópia analítica em cada (duas no total) — o mesmo cluster servindo OLTP e OLAP sem que a carga analítica pese nos nós transacionais:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp-az1-oltp' : 3 , // Transacional AZ1 em São Paulo/Brasil
   'bra-sp-az2-oltp' : 3 , // Transacional AZ2 em São Paulo/Brasil
   'bra-sp-az1-olap' : 1 , // Analítico AZ1 em São Paulo/Brasil
   'bra-sp-az2-olap' : 1   // Analítico AZ2 em São Paulo/Brasil
  };
```

O comando a seguir entrega a mesma quantidade de cópias do anterior, mas a distribuição física depende de como o administrador declarou a topologia. É um tópico mais avançado, para discutirmos em sala:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp-oltp' : 6,
   'bra-sp-olap' : 2
  };
```

Vale também segmentar keyspaces por assunto — pedidos, faturamento, contábil — ou uma por microsserviço. A segmentação facilita a administração e permite política de replicação diferente para cada conjunto de dados.

### Até onde este laboratório vai

O fator de replicação que você acabou de definir é o parâmetro mais consequente do Cassandra: ele decide quantas cópias de cada dado existem e, junto com o **consistency level** escolhido pela aplicação, determina o que acontece quando um nó cai — quanto o cluster tolera de falha e sob qual garantia de leitura.

Nada disso se demonstra com um nó. Derrubar réplicas, acompanhar `nodetool repair` redistribuindo dados e comparar `ONE`, `QUORUM` e `ALL` sob falha exige um cluster de verdade, e é assunto de um laboratório próprio. Aqui o fator de replicação fica no papel que ele tem nesta seção: uma decisão que se declara ao criar a keyspace.

**→ Próxima seção.** Com a keyspace criada, você já pode criar tabelas — e é aí que começam as decisões que o Cassandra não perdoa.

## 4. Sua primeira tabela

Vamos cadastrar clientes. Estas cinco pessoas você vai reencontrar na Parte II, no sistema do banco — inclusive com o mesmo `id_cliente`:

```sh
cql "
CREATE TABLE lab.cliente (
    id_cliente  text PRIMARY KEY,
    cpf         text,
    nome        text,
    sobrenome   text,
    email       text
);"

```

### O que o Cassandra realmente criou

```sh
cql "DESCRIBE TABLE lab.cliente;"

```

```
CREATE TABLE lab.cliente (
    id_cliente text PRIMARY KEY,
    cpf text,
    email text,
    nome text,
    sobrenome text
) WITH additional_write_policy = '99p'
    AND bloom_filter_fp_chance = 0.01
    AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
    AND compaction = {'class': 'org.apache.cassandra.db.compaction.SizeTieredCompactionStrategy', 'max_threshold': '32', 'min_threshold': '4'}
    AND compression = {'chunk_length_in_kb': '16', 'class': 'org.apache.cassandra.io.compress.LZ4Compressor'}
    AND default_time_to_live = 0
    AND gc_grace_seconds = 864000
    [... mais dez opções ...]
    AND speculative_retry = '99p';
```

Duas observações sobre esse resultado.

A primeira: **as colunas mudaram de ordem**. Você declarou `cpf, nome, sobrenome, email` e o Cassandra guardou `cpf, email, nome, sobrenome` — alfabética, depois da chave. A ordem em que você declara colunas não-chave é irrelevante para ele.

A segunda: você escreveu cinco linhas e o Cassandra completou umas vinte opções de armazenamento. Três delas voltam mais adiante neste laboratório:

| Opção | Onde reaparece |
|---|---|
| `compaction` | seção 6, quando vários arquivos de dados forem fundidos em um |
| `gc_grace_seconds` | seção 6, quando um registro apagado continuar no disco |
| `compression` | seção 6, ao inspecionar o arquivo de dados |

### INSERT

```sh
cql "
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b162060','987.539.360-60','MARIVALDA','KANAMARY','marivalda@bmail.com');
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b16242a','124.554.260-50','JUCILENE','MOREIRA CRUZ','jucilene@bmail.com');
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b16256a','324.873.000-51','GRACIMAR','BRASIL GUERRA','gracimar@bmail.com');
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b16353c','598.131.330-74','ALDENORA','VIANA MOREIRA','aldenora@gmail.com');
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b1636ae','797.399.520-03','VERA','LUCIA RODRIGUES SENA','vera@bmail.com');"

```

### SELECT

```sh
cql "SELECT id_cliente, nome, sobrenome FROM lab.cliente;"

```

```
 id_cliente | nome      | sobrenome
------------+-----------+----------------------
   2b1636ae |      VERA | LUCIA RODRIGUES SENA
   2b16242a |  JUCILENE |         MOREIRA CRUZ
   2b16256a |  GRACIMAR |        BRASIL GUERRA
   2b16353c |  ALDENORA |        VIANA MOREIRA
   2b162060 | MARIVALDA |             KANAMARY

(5 rows)
```

**Repare na ordem.** Não é a de inserção, não é alfabética, não é a do `id_cliente`. Também não é aleatória — e não vai mudar se você repetir a consulta. Essa ordem é o assunto da próxima seção.

Busca pela chave, que é a consulta que o Cassandra faz melhor:

```sh
cql "SELECT * FROM lab.cliente WHERE id_cliente = '2b162060';"

```

```
 id_cliente | cpf            | email               | nome      | sobrenome
------------+----------------+---------------------+-----------+-----------
   2b162060 | 987.539.360-60 | marivalda@bmail.com | MARIVALDA |  KANAMARY

(1 rows)
```

Agora uma busca por um campo que **não** é chave:

> **Provoque este erro.**

```sh
cql "SELECT * FROM lab.cliente WHERE nome = 'MARIVALDA';"

```

```
InvalidRequest: Error from server: code=2200 [Invalid query] message="Cannot execute
this query as it might involve data filtering and thus may have unpredictable
performance. If you want to execute this query despite the performance
unpredictability, use ALLOW FILTERING"
```

Cinco linhas na tabela e o Cassandra se recusa a varrê-las. Não é limitação de implementação: é uma escolha de projeto. Uma consulta que hoje varre cinco linhas vai varrer cinco bilhões amanhã, e ele prefere recusar a entregar uma consulta que funciona no desenvolvimento e derruba a produção.

O `ALLOW FILTERING` sugerido na mensagem existe e faz exatamente o que o nome diz. Vamos medir o custo dele na seção 8, junto com as duas outras respostas possíveis para esse erro.

### UPDATE

```sh
cql "UPDATE lab.cliente SET email = 'aldenora.moreira@bmail.com' WHERE id_cliente = '2b16353c';"

```

```sh
cql "SELECT id_cliente, nome, email FROM lab.cliente WHERE id_cliente = '2b16353c';"

```

```
 id_cliente | nome     | email
------------+----------+----------------------------
   2b16353c | ALDENORA | aldenora.moreira@bmail.com

(1 rows)
```

Agora experimente atualizar uma chave que não existe:

```sh
cql "UPDATE lab.cliente SET nome = 'FANTASMA' WHERE id_cliente = 'NAO-EXISTE';"

```

```sh
cql "SELECT id_cliente, nome, cpf FROM lab.cliente WHERE id_cliente = 'NAO-EXISTE';"

```

```
 id_cliente | nome     | cpf
------------+----------+------
 NAO-EXISTE | FANTASMA | null

(1 rows)
```

O `UPDATE` **criou** a linha. No Cassandra não existe diferença entre inserir e atualizar: as duas operações são a mesma escrita, e o termo para isso é *upsert*. Consequência prática que costuma pegar quem vem do mundo relacional: um `UPDATE` com a chave errada não devolve "0 linhas afetadas" — ele cria um registro novo, com `null` em tudo o que você não informou.

Por isso também não existe erro de chave duplicada. Um `INSERT` com uma chave que já existe sobrescreve os campos informados, silenciosamente.

### DELETE

```sh
cql "DELETE FROM lab.cliente WHERE id_cliente = 'NAO-EXISTE';"

```

```sh
cql "DELETE FROM lab.cliente WHERE id_cliente = '2b16256a';"

```

```sh
cql "SELECT id_cliente, nome FROM lab.cliente WHERE id_cliente = '2b16256a';"

```

```
 id_cliente | nome
------------+------


(0 rows)
```

A Gracimar desapareceu da consulta. Guarde esta frase, porque a seção 6 vai desmenti-la: **o dado dela não foi apagado do disco**.

Note também que apagar uma chave inexistente não deu erro. Faz sentido, pelo mesmo motivo do upsert: o Cassandra não vai ler antes de escrever só para conferir se havia algo lá.

**→ Próxima seção.** Você inseriu cinco clientes e o Cassandra os devolveu numa ordem que ninguém pediu. Essa ordem não é detalhe de apresentação: é o endereço físico de cada linha.

---

## 5. Onde o dado mora: partição e token

Toda linha que você grava vai para uma **partição**, e a partição é escolhida aplicando uma função de hash sobre a partition key. Em `lab.cliente`, a partition key é `id_cliente` — a única coluna da `PRIMARY KEY`.

O resultado dessa função é um número chamado **token**, e ele dá para consultar:

```sh
cql "SELECT id_cliente, token(id_cliente), nome FROM lab.cliente;"

```

```
 id_cliente | system.token(id_cliente) | nome
------------+--------------------------+-----------
   2b1636ae |     -4846341449078699481 |      VERA
   2b16242a |     -4461337310647205397 |  JUCILENE
   2b16353c |     -3218952037653612748 |  ALDENORA
   2b162060 |      -754340186604780055 | MARIVALDA

(4 rows)
```

Compare com o `SELECT` da seção anterior: **é a mesma ordem**. O Cassandra devolveu as linhas ordenadas por token, porque é assim que elas estão guardadas. A ordem que pareceu arbitrária é o endereço físico.

O token é um inteiro de 64 bits, produzido pelo particionador `Murmur3Partitioner` — o padrão desde a versão 1.2. Ele vai de -2⁶³ a 2⁶³-1, e esse intervalo é o **anel** de que se fala em Cassandra.

### O anel deste nó

```sh
nt ring

```

```
Datacenter: datacenter1
==========
Address          Rack        Status State   Load            Owns                Token
                                                                                9136285029854853100
172.21.0.2       RAC1        Up     Normal  113.55 KiB      100.00%             -7720454491340799877
[... quatro linhas ...]
172.21.0.2       RAC1        Up     Normal  113.55 KiB      100.00%             -1157312431376904826
172.21.0.2       RAC1        Up     Normal  113.55 KiB      100.00%              -312935783885743070
172.21.0.2       RAC1        Up     Normal  113.55 KiB      100.00%              1127332446016840168
[... mais oito linhas ...]

  Warning: "nodetool ring" is used to output all the tokens of a node.
  To view status related info of a node use "nodetool status" instead.
```

Dezesseis linhas para um único nó — o mesmo `Tokens 16` que o `nt status` mostrou na seção 2. O nó não ocupa uma posição no anel, ocupa dezesseis, e cada uma delas responde por uma faixa que **termina** no token da linha. Isso se chama **vnodes**, e existe para que a entrada ou saída de um nó redistribua o dado em pedaços pequenos, em vez de mover metade do cluster.

Agora localize a Marivalda. O token dela é `-754340186604780055`, e no trecho acima ele cai entre `-1157312431376904826` e `-312935783885743070`. Essa faixa é a que responde por ela.

> Os valores de token do **anel** são sorteados quando o nó é criado, então os do seu ambiente serão outros. Os valores de token das **linhas** não: `token('2b162060')` devolve `-754340186604780055` em qualquer instalação, porque é um hash da chave. Procure no seu `nt ring` a faixa que contém esse número.

Com um nó, todas as faixas são dele — daí `Owns 100.00%`. Com dois nós, cada um ficaria com aproximadamente metade das faixas, e cada partição passaria a ter um endereço não só no disco, mas na rede. Esse é o assunto do laboratório de cluster.

### Partição e linha não são a mesma coisa

Em `lab.cliente`, cada partição tem exatamente uma linha, porque a `PRIMARY KEY` tem só a partition key. É o caso mais simples que existe, e também o menos interessante: uma partição de uma linha só não aproveita nada do que o Cassandra sabe fazer.

O que muda quando a `PRIMARY KEY` tem mais colunas é o centro da Parte II. Por ora, guarde a distinção:

| | |
|---|---|
| **partition key** | decide **em qual partição** — e, num cluster, em qual nó — a linha mora |
| **clustering key** | decide **em que ordem** as linhas ficam dentro da partição |

**→ Próxima seção.** Você sabe onde cada linha mora e em que ordem. Falta ver o que existe de fato no disco — inclusive a Gracimar, que você apagou e que ainda está lá.

## 6. Do memtable ao disco

Quando você executou aqueles `INSERT`, o Cassandra fez duas coisas e só então respondeu:

1. gravou a operação no fim do **commit log**, um arquivo sequencial;
2. aplicou a mudança na **memtable**, uma estrutura em memória.

Só isso. Nenhuma escrita em arquivo de dados, nenhuma leitura do que já existia, nenhuma procura por onde encaixar a linha. É por esse motivo que a escrita no Cassandra é rápida — e é por isso que ela é rápida *igualmente*, com dez linhas ou dez bilhões.

Nesta seção vamos acompanhar o resto do caminho: da memtable até o disco, e daí até a compactação.

Um terceiro atalho, só para esta seção, porque vamos olhar arquivos:

```sh
alias cass='docker exec -it cassandra-database'

```

### Onde a tabela mora no disco

```sh
DIR=$(docker exec cassandra-database sh -c 'ls -rtd /var/lib/cassandra/data/lab/cliente-* | tail -1')
echo $DIR

```

```
/var/lib/cassandra/data/lab/cliente-c9940ef0885411f1896db93ac98379bd
```

O caminho é `keyspace/tabela-uuid`, e o UUID é sorteado na criação da tabela — o do seu ambiente será outro. Guardamos em `$DIR` para não repetir esse nome enorme.

> O `| tail -1` não é decoração. Um `DROP TABLE` não remove o diretório: ele guarda um snapshot e deixa a pasta antiga no lugar. Se você recriar a tabela, passam a existir dois diretórios `cliente-*`, e sem o `tail -1` a variável receberia os dois caminhos de uma vez. Pegando sempre o mais recente, o comando funciona quantas vezes você repetir esta seção.

```sh
cass ls -la $DIR

```

```
total 8
drwxr-xr-x 2 cassandra cassandra 4096 Jul 25 17:50 .
drwxr-xr-x 3 cassandra cassandra 4096 Jul 25 17:50 ..
```

**Vazio.** Você inseriu cinco clientes, atualizou um, apagou dois, e consultou tudo isso com sucesso — e não existe um único arquivo de dados. Onde está?

### No commit log

```sh
cass ls -la /var/lib/cassandra/commitlog/

```

```
-rw-r--r-- 1 cassandra cassandra 33554432 Jul 25 18:01 CommitLog-7-1785001531318.log
-rw-r--r-- 1 cassandra cassandra 33554432 Jul 25 17:45 CommitLog-7-1785001531319.log
```

Os 32 MB de cada arquivo são **pré-alocados**: o tamanho não diz nada sobre quanto dado existe. O Cassandra reserva o espaço adiantado justamente para que a escrita seja uma gravação sequencial no fim de um arquivo que já está lá.

Procure algo que só existe por causa do que você fez na seção 4 — a linha fantasma do upsert:

```sh
cass sh -c "grep --text -o 'FANTASMA' /var/lib/cassandra/commitlog/*.log"

```

```
FANTASMA
```

E o e-mail que você atualizou:

```sh
cass sh -c "grep --text -o 'aldenora.moreira@bmail.com' /var/lib/cassandra/commitlog/*.log"

```

```
aldenora.moreira@bmail.com
```

Está tudo ali, em texto claro. Agora experimente com um nome:

```sh
cass sh -c "grep -c --text 'MARIVALDA' /var/lib/cassandra/commitlog/*.log"

```

```
/var/lib/cassandra/commitlog/CommitLog-7-1785001531318.log:9
/var/lib/cassandra/commitlog/CommitLog-7-1785001531319.log:0
```

Nove ocorrências, e você inseriu a Marivalda uma vez. O motivo: **o commit log é do nó, não da tabela**. Ele recebe as escritas de todas as tabelas de todas as keyspaces, em um único fluxo sequencial — e a Marivalda também é cliente do `infobarbank` e da loja `ecommerce`, cada um com suas tabelas.

Isso responde por que a escrita não fica mais lenta conforme você cria tabelas: há um só arquivo recebendo tudo, e nunca uma busca por posição.

> **Durabilidade.** Se o processo morrer agora, a memtable se perde — mas o commit log não. Na volta, o Cassandra o relê e reconstrói a memtable. É esse arquivo que faz da escrita algo confirmado, não o arquivo de dados.

### Ciclo 1 — o flush

`nodetool flush` força a memtable a descer para o disco:

```sh
cass nodetool flush lab cliente

```

```sh
cass ls -la $DIR

```

```
total 44
-rw-r--r-- 1 cassandra cassandra   47 Jul 25 18:15 nb-1-big-CompressionInfo.db
-rw-r--r-- 1 cassandra cassandra  338 Jul 25 18:15 nb-1-big-Data.db
-rw-r--r-- 1 cassandra cassandra   10 Jul 25 18:15 nb-1-big-Digest.crc32
-rw-r--r-- 1 cassandra cassandra   24 Jul 25 18:15 nb-1-big-Filter.db
-rw-r--r-- 1 cassandra cassandra   78 Jul 25 18:15 nb-1-big-Index.db
-rw-r--r-- 1 cassandra cassandra 4973 Jul 25 18:15 nb-1-big-Statistics.db
-rw-r--r-- 1 cassandra cassandra   68 Jul 25 18:15 nb-1-big-Summary.db
-rw-r--r-- 1 cassandra cassandra   92 Jul 25 18:15 nb-1-big-TOC.txt
```

> O `Data.db` do seu ambiente pode ter um ou dois bytes de diferença. Os timestamps de cada escrita são gravados dentro do arquivo, em codificação de largura variável, e a sua execução aconteceu em outro instante.

Oito arquivos, todos com o prefixo `nb-1-big`. Juntos eles formam **uma SSTable**:

| Componente | Conteúdo |
|---|---|
| `Data.db` | as linhas propriamente ditas |
| `Index.db` | de cada partition key para a posição dela no `Data.db` |
| `Summary.db` | uma amostra do `Index.db`, mantida em memória |
| `Filter.db` | o *bloom filter*: responde, sem tocar no disco, "esta chave **certamente não** está aqui" |
| `CompressionInfo.db` | mapa dos blocos comprimidos, para conseguir ler um pedaço sem descomprimir tudo |
| `Statistics.db` | metadados: menor e maior timestamp, faixa de tokens, histogramas |
| `Digest.crc32` | checksum do `Data.db` |
| `TOC.txt` | a lista dos componentes acima |

### O que existe dentro do `Data.db`

São pouco mais de trezentos bytes. Cabe inteiro na tela:

```sh
cass sh -c "od -A d -t x1z -v $DIR/nb-1-big-Data.db"

```

```
0000000 99 01 00 00 f2 01 00 08 32 62 31 36 33 36 61 65  >........2b1636ae<
0000016 7f ff ff ff 80 00 01 00 f2 33 24 3f 16 8a b7 08  >.........3$?....<
0000032 0e 37 39 37 2e 33 39 39 2e 35 32 30 2d 30 33 08  >.797.399.520-03.<
0000048 0e 76 65 72 61 40 62 6d 61 69 6c 2e 63 6f 6d 08  >.vera@bmail.com.<
0000064 04 56 45 52 41 08 14 4c 55 43 49 41 20 52 4f 44  >.VERA..LUCIA ROD<
0000080 52 49 47 55 45 53 20 53 45 4e 41 01 58 00 4b 32  >RIGUES SENA.X.K2<
0000096 34 32 61 58 00 f7 0d 83 a3 08 0e 31 32 34 2e 35  >42aX.......124.5<
0000112 35 34 2e 32 36 30 2d 35 30 08 12 6a 75 63 69 6c  >54.260-50..jucil<
0000128 65 6e 65 5c 00 f4 21 08 4a 55 43 49 4c 45 4e 45  >ene\..!.JUCILENE<
0000144 08 0c 4d 4f 52 45 49 52 41 20 43 52 55 5a 01 00  >..MOREIRA CRUZ..<
0000160 0a 4e 41 4f 2d 45 58 49 53 54 45 6a 64 fd 36 00  >.NAO-EXISTEjd.6.<
0000176 06 57 73 78 b9 6f 2a 71 00 35 35 36 61 17 00 33  >.Wsx.o*q.556a..3<
0000192 bf ed a1 17 00 49 33 35 33 63 88 00 f9 18 4b 16  >.....I353c....K.<
0000208 88 63 08 0e 35 39 38 2e 31 33 31 2e 33 33 30 2d  >.c..598.131.330-<
0000224 37 34 00 c7 3b 01 1a 61 6c 64 65 6e 6f 72 61 2e  >74..;..aldenora.<
0000240 6d 6f 72 65 69 ef 00 f3 02 08 41 4c 44 45 4e 4f  >morei.....ALDENO<
0000256 52 41 08 0d 56 49 41 4e 41 20 99 00 03 64 00 49  >RA..VIANA ...d.I<
0000272 32 30 36 30 64 00 f8 0e 3c 16 00 08 0e 39 38 37  >2060d...<....987<
0000288 2e 35 33 39 2e 33 36 30 2d 36 30 08 13 6d 61 72  >.539.360-60..mar<
0000304 69 76 61 6c 64 48 01 f0 06 09 4d 41 52 49 56 41  >ivaldH....MARIVA<
0000320 4c 44 41 08 08 4b 41 4e 41 4d 41 52 59 01 ec 56  >LDA..KANAMARY..V<
0000336 65 e9                                            >e.<
0000338
```

Três coisas nesse despejo.

**A primeira linha começa com `2b1636ae`**, a Vera — não a Marivalda, que foi a primeira a ser inserida. É a ordem de token da seção 5, agora materializada em bytes. Esse é o primeiro **S** de SSTable: *Sorted*.

**`NAO-EXISTE` está lá, no offset 160**, e note que depois da chave não vem CPF, nem nome, nem e-mail. Você apagou aquela linha. Ela continua no arquivo, sem conteúdo.

**Tudo legível.** CPF, e-mail e nome completo em texto claro, sem nenhum esforço para lê-los. O `LZ4Compressor` que apareceu no `DESCRIBE TABLE` comprime, mas não cifra — e comprime por blocos, então trechos ficam intactos. Se dado sensível precisa estar cifrado em repouso, isso é configuração de disco ou de sistema de arquivos, não algo que o Cassandra faça por você.

> Se o seu ambiente tiver `hexdump` instalado, `hexdump -C` produz uma saída equivalente e um pouco mais confortável de ler. Usamos `od` porque ele já vem na imagem, e instalar pacote no meio do laboratório é atrito desnecessário.

### O tombstone

O hexadecimal mostra que a linha apagada está no arquivo. Para ver **o que** ela guarda, existe uma ferramenta melhor, que traduz a SSTable para JSON:

```sh
cass sh -c "/opt/cassandra/tools/bin/sstabledump $DIR/nb-1-big-Data.db"

```

Procure a Gracimar, `2b16256a`, e a linha fantasma:

```json
  {
    "partition" : {
      "key" : [ "NAO-EXISTE" ],
      "position" : 200,
      "deletion_info" : { "marked_deleted" : "2026-07-25T18:15:18.538026Z", "local_delete_time" : "2026-07-25T18:15:18Z" }
    },
    "rows" : [ ]
  },
  {
    "partition" : {
      "key" : [ "2b16256a" ],
      "position" : 223,
      "deletion_info" : { "marked_deleted" : "2026-07-25T18:15:18.963617Z", "local_delete_time" : "2026-07-25T18:15:18Z" }
    },
    "rows" : [ ]
  },
```

Aqui está a promessa da seção 4, cumprida. A Gracimar não foi apagada: o `DELETE` **escreveu** um registro novo, uma marca de exclusão com data e hora, e é isso que se chama **tombstone**. `"rows" : [ ]` — a partição existe, sem linhas vivas.

Faz sentido, dado tudo o que você viu: apagar de verdade exigiria localizar o dado e reescrever o arquivo. Num sistema em que arquivo de dados nunca é modificado, apagar é mais uma escrita. O `SELECT` da seção 4 devolveu vazio porque a leitura encontrou o tombstone e o respeitou.

> O `sstabledump` fica em `/opt/cassandra/tools/bin/`, que não está no `PATH` — daí o caminho completo.

### Ciclo 2 — arquivo de dados não se altera

Insira mais duas clientes:

```sh
cql "
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b16396a','661.428.060-00','IVONE','GLAUCIA VIANA DUTRA','ivone@bmail.com');
INSERT INTO lab.cliente(id_cliente, cpf, nome, sobrenome, email) VALUES ('2b163bcc','190.523.300-00','LUCILIA','ROSA LIMA PEREIRA','lucilia@yahoo.com');"

```

O arquivo que já existe mudou?

```sh
cass sh -c "ls -l $DIR/nb-1-big-Data.db; grep -c --text IVONE $DIR/nb-1-big-Data.db"

```

```
-rw-r--r-- 1 cassandra cassandra 338 Jul 25 18:15 .../nb-1-big-Data.db
0
```

Mesmo tamanho, mesmo horário, e a Ivone não está nele. Agora um novo flush:

```sh
cass nodetool flush lab cliente

```

```sh
cass sh -c "ls -1 $DIR/*-Data.db"

```

```
.../nb-1-big-Data.db
.../nb-2-big-Data.db
```

**SSTable é imutável.** Uma vez escrita, nunca é alterada — só criada ou removida. Todo flush produz uma nova.

Isso tem uma consequência incômoda: a mesma partição pode ter pedaços em várias SSTables, e uma leitura precisaria, em princípio, procurar em todas. É para evitar isso que existe o `Filter.db`, o bloom filter: antes de tocar no disco, o Cassandra pergunta a ele se aquela chave *pode* estar naquela SSTable, e na maioria das vezes a resposta é um "não" que custa nada.

Mas o número de arquivos não pode crescer para sempre.

### Ciclo 3 — compactação

Vamos atualizar o sobrenome da Marivalda para algo bem grande, de modo que fique fácil de achar no disco:

```sh
cql "
UPDATE lab.cliente
SET sobrenome = 'DE ALCÂNTARA FRANCISCO ANTÔNIO JOÃO CARLOS XAVIER DE PAULA MIGUEL RAFAEL JOAQUIM JOSÉ GONZAGA PASCOAL CIPRIANO SERAFIM DE BRAGANÇA E BOURBON KANAMARY'
WHERE id_cliente = '2b162060';"

```

```sh
cass nodetool flush lab cliente

```

```sh
cass sh -c "ls -l $DIR/*-Data.db | awk '{print \$5, \$NF}'"

```

```
338 .../nb-1-big-Data.db
171 .../nb-2-big-Data.db
193 .../nb-3-big-Data.db
```

Três arquivos. E agora existem **duas versões do sobrenome da Marivalda no disco**: o `KANAMARY` original no `nb-1` e o nome comprido no `nb-3`.

```sh
cass sh -c "grep --text -o 'BOURBON KANAMARY' $DIR/nb-3-big-Data.db"

```

```
BOURBON KANAMARY
```

A leitura resolve isso comparando timestamps e devolvendo o valor mais recente — o que funciona, mas custa. Cedo ou tarde é preciso consolidar. Normalmente o Cassandra faz isso sozinho, por conta da `SizeTieredCompactionStrategy` que apareceu no `DESCRIBE TABLE`; aqui vamos forçar:

```sh
cass nodetool compact lab cliente

```

```sh
cass sh -c "ls -l $DIR/*-Data.db | awk '{print \$5, \$NF}'"

```

```
632 .../nb-4-big-Data.db
```

Três arquivos viraram um. Isso é **compactação**, e o conceito por trás dela é a [Log-structured merge-tree](https://en.wikipedia.org/wiki/Log-structured_merge-tree), a **LSM tree**: escreve-se sempre em arquivo novo, e a consolidação acontece depois, em segundo plano.

> Se a numeração do seu ambiente for diferente de `nb-1` a `nb-4`, é porque houve algum flush a mais. Use os nomes que o `ls` mostrar.

Veja o que sobrou da Marivalda:

```sh
cass sh -c "/opt/cassandra/tools/bin/sstabledump $DIR/nb-4-big-Data.db"

```

```json
      "key" : [ "2b162060" ],
      "position" : 440
    },
    "rows" : [
      {
        "type" : "row",
        "liveness_info" : { "tstamp" : "2026-07-25T18:15:17.198812Z" },
        "cells" : [
          { "name" : "cpf", "value" : "987.539.360-60" },
          { "name" : "email", "value" : "marivalda@bmail.com" },
          { "name" : "nome", "value" : "MARIVALDA" },
          { "name" : "sobrenome", "value" : "DE ALCÂNTARA [...] BOURBON KANAMARY", "tstamp" : "2026-07-25T18:21:51.103215Z" }
        ]
      }
    ]
```

Uma única célula `sobrenome`, com o valor novo. E repare no detalhe: ela tem **timestamp próprio**, `18:21:51`, diferente do `liveness_info` da linha, `18:15:17`. O timestamp no Cassandra é por célula, não por linha — o que explica como a compactação resolveu o conflito sem precisar de nada além dos próprios arquivos: para cada célula, vence a escrita mais recente.

### O tombstone que sobreviveu

```sh
cass sh -c "/opt/cassandra/tools/bin/sstabledump $DIR/nb-4-big-Data.db" | grep -B3 deletion_info

```

```json
      "key" : [ "NAO-EXISTE" ],
      "deletion_info" : { "marked_deleted" : "2026-07-25T18:15:18.538026Z", ... }
      "key" : [ "2b16256a" ],
      "deletion_info" : { "marked_deleted" : "2026-07-25T18:15:18.963617Z", ... }
```

A compactação descartou o sobrenome antigo da Marivalda, mas **manteve os dois tombstones**. Por quê?

```sh
cql "SELECT gc_grace_seconds FROM system_schema.tables WHERE keyspace_name='lab' AND table_name='cliente';"

```

```
 gc_grace_seconds
------------------
           864000
```

864.000 segundos são **dez dias** — a terceira opção que separamos no `DESCRIBE TABLE` da seção 4. Antes desse prazo, nenhuma compactação remove um tombstone.

A razão está num cluster, não aqui. Imagine três réplicas e uma delas fora do ar no momento do `DELETE`. Quando ela voltar, ainda terá a Gracimar. Se as outras duas já tivessem descartado o tombstone, a réplica atrasada espalharia a linha de volta — o registro apagado ressuscitaria. O tombstone precisa sobreviver o tempo suficiente para que o `nodetool repair` o propague a todas as réplicas.

O preço de um tombstone é ocupar espaço e ser lido junto com o dado vivo. Uma tabela que apaga muito acumula tombstones, e leituras que atravessam milhares deles ficam lentas — é um dos problemas de desempenho mais comuns em Cassandra, e vem de decisões de modelagem, não de configuração.

### O que você deve conseguir explicar

- Por que a escrita é rápida, e por que não fica mais lenta com o volume.
- Por que o dado aparece na consulta antes de existir arquivo de dados, e o que garante que ele não se perca.
- O que significa cada **S** de SSTable, e por que arquivos imutáveis exigem compactação.
- Por que `DELETE` é uma escrita, e o que `gc_grace_seconds` protege.
- Por que dado sensível em Cassandra não está protegido por padrão.

**→ Parte II.** A tabela `lab.cliente` responde bem a uma pergunta: "quem é o cliente de id X?". Na próxima seção vamos fazer a pergunta que todo sistema faz em seguida — e descobrir que ela não tem resposta nesta tabela, nem em nenhuma outra que se pareça com ela.

## 7. Não existe JOIN — existe outra tabela

Sua tabela `lab.cliente` responde bem a uma pergunta: *"quem é o cliente de id X?"*. Um sistema bancário faz essa pergunta uma vez, no login, e depois faz outras dez. A mais imediata: *"quais os lançamentos desta cliente?"*

No modelo relacional isso é uma tabela `lancamento` com chave estrangeira e um `JOIN`. Vamos tentar — e não em tabelas que você acabou de inventar, mas em duas que existem, povoadas, no sistema do banco:

> **Provoque este erro.**

```sh
cql "
SELECT nome_completo, valor
FROM infobarbank.cliente
JOIN infobarbank.lancamentos_por_periodo
  ON cliente.id_cliente = lancamentos_por_periodo.id_cliente;"

```

```
SyntaxException: line 1:53 mismatched input 'JOIN' expecting EOF
(..., valor FROM infobarbank.cliente [JOIN]...)
```

Leia com atenção: **`expecting EOF`**. O interpretador chegou ao fim do nome da tabela e concluiu que a consulta deveria ter terminado ali. Não é que o `JOIN` seja proibido — é que a gramática do CQL não tem onde encaixar uma segunda tabela. Nem com a sintaxe antiga:

> **Provoque este erro.**

```sh
cql "SELECT * FROM infobarbank.cliente, infobarbank.conta_corrente;"

```

```
SyntaxException: line 1:33 mismatched input ',' expecting EOF
(SELECT * FROM infobarbank.cliente[,]...)
```

A razão é a mesma da seção 5. Um `JOIN` combina linhas de dois conjuntos, e num cluster essas linhas estão em partições diferentes, em nós diferentes. Fazer isso exigiria mover dados pela rede em quantidade imprevisível, no meio de uma consulta que alguém está esperando. O Cassandra não oferece essa operação — do mesmo modo que não oferece `WHERE` em coluna não indexada.

Então **como um sistema real resolve isso?**

### O sistema do banco

```sh
cql "SELECT table_name FROM system_schema.tables WHERE keyspace_name='infobarbank';"

```

```
 table_name
----------------------------
             cartao_credito
                    cliente
            cliente_por_cpf
          cliente_por_email
       cliente_por_telefone
             conta_corrente
 lancamentos_cartao_credito
        lancamentos_detalhe
    lancamentos_por_periodo
    lancamentos_por_produto
     lancamentos_por_status
       lancamentos_por_tipo

(12 rows)
```

Doze tabelas. Olhe os nomes com desconfiança: `cliente`, `cliente_por_cpf`, `cliente_por_email`, `cliente_por_telefone`. Parecem quatro tabelas diferentes. Procure a Marivalda em cada uma:

```sh
cql "SELECT id_cliente, nome_completo, estado FROM infobarbank.cliente WHERE id_cliente='2b162060';"

```

```sh
cql "SELECT id_cliente, nome_completo, estado FROM infobarbank.cliente_por_cpf WHERE cpf='987.539.360-60';"

```

```sh
cql "SELECT id_cliente, nome_completo, estado FROM infobarbank.cliente_por_email WHERE email='marivalda@bmail.com';"

```

```sh
cql "SELECT id_cliente, nome_completo, estado FROM infobarbank.cliente_por_telefone WHERE telefone='(11) 987654321';"

```

Os quatro comandos devolvem exatamente a mesma linha:

```
   2b162060 | MARIVALDA KANAMARY |     SP
```

**É o mesmo dado, gravado quatro vezes.** Não é redundância acidental, nem falta de normalização por descuido: é a resposta do Cassandra ao problema que você acabou de encontrar. A aplicação de banco precisa aceitar login por CPF, por e-mail ou por telefone, e cada uma dessas três formas é uma consulta diferente. Sem `JOIN` e sem `WHERE` livre, **cada consulta ganha a sua tabela**.

O preço é escrever quatro vezes e manter quatro cópias em sincronia — trabalho da aplicação, não do banco. O ganho é que qualquer uma das três telas de login responde com uma leitura pontual, em uma partição, em um nó, com custo que não muda quando a base cresce de mil para um bilhão de clientes.

> Essa é a frase que resume a modelagem em Cassandra: **escreve-se o dado N vezes para lê-lo barato N vezes.** No modelo relacional o dado é guardado uma vez e a consulta faz o trabalho; aqui a escrita faz o trabalho e a consulta é trivial.

E a Marivalda que você cadastrou na seção 4, com o mesmo `id_cliente` `2b162060`? É a mesma pessoa. A diferença é que aqui ela existe em um modelo que foi projetado a partir das perguntas que o sistema faz.

**→ Próxima seção.** Doze tabelas não saíram de um diagrama de entidades. Cada uma existe porque alguma tela do aplicativo precisa dela. Vamos ler o modelo ao contrário: das perguntas para as tabelas.

## 8. Chave primária na prática

O modelo do `infobarbank` nasceu de um **fluxo aplicacional**: a sequência de telas que a cliente percorre no aplicativo do banco. Cada tela é uma consulta:

| | Consulta | Tela |
|---|---|---|
| **Q1** | Exibir dados da conta | abertura |
| **Q2** | Exibir lista de cartões de crédito e seus limites | cartões |
| **Q3** | Últimos lançamentos aprovados de conta e cartão | extrato, visão inicial |
| **Q4** | Exibir extrato de lançamentos por período | extrato, filtro de datas |
| **Q5** | Exibir extrato dos lançamentos de um cartão | extrato de um cartão |
| **Q6** | Exibir extrato de lançamentos do tipo débito | extrato, filtro de tipo |
| **Q7** | Exibir detalhe do lançamento selecionado | detalhe |

Sete consultas, doze tabelas. Nesta seção vamos percorrer cada arranjo possível de `PRIMARY KEY` usando as consultas que o motivaram.

### Escolhendo a competência

Os lançamentos são gerados em relação à data de execução, então as competências disponíveis no seu ambiente são outras. Descubra:

```sh
cql "SELECT DISTINCT id_cliente, competencia FROM infobarbank.lancamentos_por_periodo;"

```

```
   2b162060 |     2026-05
   2b162060 |     2026-06
   2b162060 |     2026-07
[...]
```

Use a **penúltima** competência nos exemplos, não a mais recente. Compare:

```sh
cql "SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-06';"

```

```
    19
```

```sh
cql "SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-07';"

```

```
    11
```

A competência mais recente é o **mês corrente**, e portanto está pela metade — hoje é dia 25. Não é defeito do laboratório: é o que acontece em qualquer base de produção, onde o mês em curso sempre tem menos movimento que os fechados. Nos exemplos a seguir aparece `2026-06`; troque pela penúltima competência do seu ambiente.

### 8.1 Partition key de coluna única

O caso mais simples, o mesmo da sua `lab.cliente`: a `PRIMARY KEY` tem uma coluna, que é a partition key. Uma partição, uma linha.

É a forma da **Q7**, o detalhe de um lançamento:

```sh
cql "DESCRIBE TABLE infobarbank.lancamentos_detalhe;"

```

```
    PRIMARY KEY (id_lancamento)
```

```sh
cql "
SELECT id_lancamento, data_hora, estabelecimento, valor, status, codigo_autenticacao
FROM infobarbank.lancamentos_detalhe
WHERE id_lancamento='cc44552e';"

```

```
 id_lancamento | data_hora                       | estabelecimento   | valor     | status   | codigo_autenticacao
---------------+---------------------------------+-------------------+-----------+----------+--------------------------------------
      cc44552e | 2026-06-27 17:46:39.942000+0000 | Posto de gasolina | 708.40997 | APROVADA | b2c5db0d-ec3c-4a13-b116-a44e1ffd8e41
```

> Use um `id_lancamento` do seu ambiente. Você obtém um com:
> `cql "SELECT id_lancamento FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-06' LIMIT 1;"`

Repare no que essa tabela tem de diferente das outras de lançamento: uma coluna a mais, `codigo_autenticacao`. A tela de detalhe é a única que mostra esse campo, então ele existe só aqui. **Tabela por consulta significa também colunas por consulta.**

### 8.2 Partition key mais clustering key

Agora a `PRIMARY KEY` tem duas partes. A **Q1**, dados da conta:

```sh
cql "DESCRIBE TABLE infobarbank.conta_corrente;"

```

```
    PRIMARY KEY ((id_cliente), status, id_conta)
```

```sh
cql "
SELECT id_conta, status, apelido_cliente, saldo_disponivel
FROM infobarbank.conta_corrente
WHERE id_cliente='2b162060';"

```

```
 id_conta | status | apelido_cliente | saldo_disponivel
----------+--------+-----------------+------------------
 2b162060 |  ATIVA |       MARIVALDA |              100
```

E a **Q2**, cartões e limites, com a mesma forma:

```sh
cql "
SELECT status, id_cartao, num_cartao, limite_total, limite_disponivel
FROM infobarbank.cartao_credito
WHERE id_cliente='2b162060';"

```

```
 status  | id_cartao | num_cartao          | limite_total | limite_disponivel
---------+-----------+---------------------+--------------+-------------------
   ATIVO |  007c2c1c | 5450 3799 9172 8454 |         1000 |               900
   ATIVO |  897199aa | 5576 8924 9861 7490 |          200 |                50
 INATIVO |  9a748c3c | 5188 2716 2053 8850 |          500 |               100

(3 rows)
```

Três linhas em **uma** partição. É a diferença em relação a 8.1: com clustering key, uma partição guarda várias linhas, ordenadas fisicamente pela clustering key.

E note a ordem: os dois `ATIVO` vêm antes do `INATIVO`, porque `status` é a primeira clustering key e ordena alfabeticamente. Não é coincidência conveniente — é decisão de modelagem. A tela de cartões mostra primeiro os que a cliente pode usar, e essa ordenação **não custa nada em tempo de consulta** porque já está no disco. Compare com o mundo relacional, onde seria um `ORDER BY status` executado a cada requisição.

Essa é também a forma das tabelas de acesso alternativo que você viu na seção 7:

```sh
cql "DESCRIBE TABLE infobarbank.cliente_por_cpf;"

```

```
    PRIMARY KEY (cpf, id_cliente)
```

Por que `id_cliente` como clustering key, se um CPF identifica uma pessoa? Por segurança de modelagem: se dois registros vierem com o mesmo CPF, eles coexistem como duas linhas na mesma partição, em vez de um sobrescrever o outro silenciosamente — que é o que o upsert da seção 4 faria.

### 8.3 Partition key de múltiplas colunas

A **Q4**, extrato por período, é onde o modelo fica interessante:

```sh
cql "DESCRIBE TABLE infobarbank.lancamentos_por_periodo;"

```

```
    PRIMARY KEY ((id_cliente, competencia), data_hora, id_lancamento)
) WITH CLUSTERING ORDER BY (data_hora DESC, id_lancamento ASC)
```

A partition key agora tem **duas** colunas: `id_cliente` **e** `competencia`. O hash é calculado sobre o par.

```sh
cql "
SELECT data_hora, id_produto, tipo_operacao, estabelecimento, valor
FROM infobarbank.lancamentos_por_periodo
WHERE id_cliente='2b162060' AND competencia='2026-06'
  AND data_hora >= '2026-06-19' AND data_hora < '2026-06-28';"

```

```
 data_hora                       | id_produto | tipo_operacao | estabelecimento    | valor
---------------------------------+------------+---------------+--------------------+-----------
 2026-06-27 17:46:39.942000+0000 |   2b162060 |        DEBITO |  Posto de gasolina | 708.40997
 2026-06-27 17:46:39.770000+0000 |   897199aa |        DEBITO |    Salão de beleza | 835.98999
 2026-06-25 17:46:42.420000+0000 |   2b162060 |        DEBITO |    Salão de beleza |       936
 2026-06-21 17:46:39.620000+0000 |   2b162060 |        DEBITO | Loja de brinquedos | 727.70001
 2026-06-19 17:46:39.360000+0000 |   2b162060 |        DEBITO |    Salão de beleza |    654.87

(5 rows)
```

Duas coisas nesse resultado.

**A ordem é decrescente** — do lançamento mais recente para o mais antigo, que é como um extrato se lê. Veio do `CLUSTERING ORDER BY (data_hora DESC)`, e portanto do disco. Sem `ORDER BY` na consulta.

**O filtro de datas funciona** sem `ALLOW FILTERING`, ao contrário do `WHERE nome=...` da seção 4. Porque `data_hora` é clustering key: dentro da partição as linhas estão ordenadas por ela, então buscar um intervalo é ir a duas posições e ler o que está entre elas.

Por que `competencia` entrou na partition key? Se a partição fosse só `id_cliente`, todos os lançamentos de uma cliente ao longo de anos ficariam em uma única partição, que cresceria para sempre. Uma partição não se divide entre nós — o cluster escala em **número** de partições, não em tamanho delas. Colocar a competência na chave quebra o histórico em uma partição por mês, cada uma com algumas dezenas de linhas.

O preço é que **toda consulta precisa informar a competência**. É por isso que a tela de extrato do seu banco tem um seletor de mês, e não um campo livre de datas. A interface do aplicativo é consequência do modelo de dados.

### 8.4 A mesma partição, quatro ordenações

Q3, Q5 e Q6 pedem os mesmos lançamentos da mesma cliente no mesmo mês. Só a forma de filtrar muda. Compare as chaves:

| Consulta | Tabela | PRIMARY KEY |
|---|---|---|
| Q4 por período | `lancamentos_por_periodo` | `((id_cliente, competencia), data_hora, id_lancamento)` |
| Q3 por situação | `lancamentos_por_status` | `((id_cliente, competencia), status, data_hora, id_lancamento)` |
| Q5 por cartão | `lancamentos_por_produto` | `((id_cliente, competencia), id_produto, data_hora, id_lancamento)` |
| Q6 por tipo | `lancamentos_por_tipo` | `((id_cliente, competencia), tipo_operacao, data_hora, id_lancamento)` |

**Partition key idêntica nas quatro. O que muda é a primeira clustering key.** É o mesmo dado, gravado quatro vezes, ordenado de quatro maneiras.

Q3 — últimos aprovados:

```sh
cql "
SELECT status, data_hora, id_produto, estabelecimento, valor
FROM infobarbank.lancamentos_por_status
WHERE id_cliente='2b162060' AND competencia='2026-06' AND status='APROVADA'
LIMIT 5;"

```

```
 status   | data_hora                       | id_produto | estabelecimento    | valor
----------+---------------------------------+------------+--------------------+-----------
 APROVADA | 2026-06-27 17:46:39.942000+0000 |   2b162060 |  Posto de gasolina | 708.40997
 APROVADA | 2026-06-27 17:46:39.770000+0000 |   897199aa |    Salão de beleza | 835.98999
 APROVADA | 2026-06-25 17:46:42.420000+0000 |   2b162060 |    Salão de beleza |       936
 APROVADA | 2026-06-21 17:46:39.620000+0000 |   2b162060 | Loja de brinquedos | 727.70001
 APROVADA | 2026-06-19 17:46:39.360000+0000 |   2b162060 |    Salão de beleza |    654.87
```

Q5 — lançamentos de um cartão específico:

```sh
cql "
SELECT id_produto, data_hora, estabelecimento, valor
FROM infobarbank.lancamentos_por_produto
WHERE id_cliente='2b162060' AND competencia='2026-06' AND id_produto='897199aa';"

```

```
 id_produto | data_hora                       | estabelecimento    | valor
------------+---------------------------------+--------------------+-----------
   897199aa | 2026-06-27 17:46:39.770000+0000 |    Salão de beleza | 835.98999
   897199aa | 2026-06-11 17:46:42.373000+0000 |       Supermercado | 529.60999
   897199aa | 2026-06-09 17:46:42.640000+0000 | Loja de brinquedos | 302.48001
   897199aa | 2026-06-08 17:46:40.793000+0000 |        Restaurante | 817.54999
   897199aa | 2026-06-01 17:46:42.085000+0000 |        Restaurante | 615.17999
```

`id_produto` é a conta ou o cartão que originou o lançamento — `897199aa` é um dos cartões que a Q2 listou.

Q6 — por tipo de operação:

```sh
cql "
SELECT tipo_operacao, data_hora, estabelecimento, valor
FROM infobarbank.lancamentos_por_tipo
WHERE id_cliente='2b162060' AND competencia='2026-06' AND tipo_operacao='DEBITO'
LIMIT 4;"

```

```
 tipo_operacao | data_hora                       | estabelecimento    | valor
---------------+---------------------------------+--------------------+-----------
        DEBITO | 2026-06-27 17:46:39.942000+0000 |  Posto de gasolina | 708.40997
        DEBITO | 2026-06-27 17:46:39.770000+0000 |    Salão de beleza | 835.98999
        DEBITO | 2026-06-25 17:46:42.420000+0000 |    Salão de beleza |       936
        DEBITO | 2026-06-21 17:46:39.620000+0000 | Loja de brinquedos | 727.70001
```

`tipo_operacao` é a **direção contábil** do lançamento: `DEBITO` é saída de dinheiro, `CREDITO` é entrada — salário caindo na conta, estorno no cartão. Num extrato, entradas são naturalmente raras, então uma consulta filtrando `CREDITO` pode devolver poucas linhas ou nenhuma. Não é erro seu.

### 8.5 Os erros que ensinam

Quatro tentativas que o Cassandra recusa. Cada mensagem diz algo diferente sobre a chave primária.

**Partition key composta pela metade.** A tabela pede `(id_cliente, competencia)`:

> **Provoque este erro.**

```sh
cql "SELECT * FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060';"

```

```
InvalidRequest: ... "Cannot execute this query as it might involve data filtering
and thus may have unpredictable performance..."
```

O hash é calculado sobre o par completo. Com metade da chave, o Cassandra não sabe calcular a partição — teria que procurar em todas. Guarde a diferença: **partition key composta exige todas as colunas**; clustering key, não.

**Clustering key sem a partition key.**

> **Provoque este erro.**

```sh
cql "SELECT * FROM infobarbank.lancamentos_por_status WHERE status='APROVADA';"

```

```
InvalidRequest: ... "Cannot execute this query as it might involve data filtering..."
```

Mesma mensagem, outra causa. `status` ordena as linhas *dentro* da partição; sem saber a partição, essa ordenação não serve de nada.

**Pular uma clustering key.** Em `lancamentos_por_produto` a ordem é `id_produto`, depois `data_hora`. Tente filtrar a segunda sem a primeira:

> **Provoque este erro.**

```sh
cql "
SELECT * FROM infobarbank.lancamentos_por_produto
WHERE id_cliente='2b162060' AND competencia='2026-06' AND data_hora>='2026-06-01';"

```

```
InvalidRequest: ... "PRIMARY KEY column "data_hora" cannot be restricted as
preceding column "id_produto" is not restricted"
```

Esta é a mensagem mais informativa das quatro, e vale decorar o princípio: as clustering keys formam uma ordem, como as palavras num dicionário. Você pode procurar por prefixo, não por meio. Filtrar `data_hora` sem `id_produto` seria procurar todas as palavras cuja segunda letra é "a".

**Ordenar por coluna que não é clustering key.**

> **Provoque este erro.**

```sh
cql "
SELECT * FROM infobarbank.lancamentos_por_periodo
WHERE id_cliente='2b162060' AND competencia='2026-06'
ORDER BY valor DESC;"

```

```
InvalidRequest: ... "Order by is currently only supported on the clustered columns
of the PRIMARY KEY, got valor"
```

O Cassandra não ordena em tempo de consulta: ele **entrega** na ordem em que gravou. Querer os lançamentos por valor não é uma consulta diferente — é uma **tabela** diferente, com `valor` como clustering key. Foi exatamente esse raciocínio que produziu as quatro tabelas de 8.4.

### 8.6 O que o `ALLOW FILTERING` faz

O erro sugere `ALLOW FILTERING` desde a seção 4. Vamos ver o que ele custa, com o `TRACING` ligado.

Primeiro a consulta correta, com a partition key completa:

```sh
cql "TRACING ON; SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-06';"

```

Nas linhas do rastro, duas importam:

```
Executing single-partition query on lancamentos_por_periodo
Read 19 live rows and 0 tombstone cells
```

**Uma partição, 19 linhas lidas.** Agora a mesma pergunta, sem informar a cliente, forçando o filtro:

```sh
cql "TRACING ON; SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE competencia='2026-06' ALLOW FILTERING;"

```

```
Computing ranges to query
Submitting range requests on 17 ranges with a concurrency of 1 (169.92 rows per range expected)
Executing seq scan across 1 sstables for (min(-9223372036854775808), min(-9223372036854775808)]
Read 170 live rows and 0 tombstone cells
```

Não é mais uma consulta a uma partição: é uma **varredura sequencial** de todo o anel de tokens, de -2⁶³ a 2⁶³-1, para depois descartar o que não bate. Leu 170 linhas para devolver 86.

O relógio não vai te avisar: esta tabela tem mil linhas, e as duas consultas respondem instantaneamente. É por isso que o Cassandra recusa por padrão em vez de deixar você descobrir — a consulta que varre mil linhas em desenvolvimento varre mil vezes mais em produção, e nesse dia ela não é lenta, ela é uma varredura em todos os nós do cluster ao mesmo tempo.

> `ALLOW FILTERING` tem lugar legítimo: consulta administrativa pontual, exploração de dados, tabela pequena e limitada por natureza. O que ele não é: solução para uma consulta que a aplicação faz a cada requisição.

### O que você deve conseguir explicar

- Por que um mesmo dado aparece em quatro tabelas, e quem paga essa conta.
- A diferença entre partition key composta e múltiplas clustering keys — inclusive quais colunas cada uma exige na consulta.
- Por que `ORDER BY` só funciona em clustering key.
- Por que a tela de extrato do seu banco tem um seletor de mês.
- Dado um `PRIMARY KEY`, qual consulta ele responde. E dada uma consulta, qual `PRIMARY KEY` ela pede.

**→ Próxima seção.** Você viu a resposta clássica do Cassandra para "não posso filtrar por essa coluna": modele outra tabela. A versão 5 trouxe uma terceira via — e o mais instrutivo dela é entender por que ela não substitui a modelagem.

## 9. Cassandra 5: SAI e UCS

Duas novidades da versão 5 mexem exatamente no que você viu nas seções 6 e 8.

### SAI — Storage Attached Index

Volte à consulta que falhou na seção 4:

> **Provoque este erro.**

```sh
cql "SELECT nome, sobrenome FROM lab.cliente WHERE nome='MARIVALDA';"

```

```
InvalidRequest: ... "Cannot execute this query as it might involve data filtering..."
```

Agora crie um índice sobre `nome`:

```sh
cql "CREATE INDEX cliente_nome_sai ON lab.cliente(nome) USING 'sai';"

```

E repita a consulta:

```sh
cql "SELECT id_cliente, nome, sobrenome FROM lab.cliente WHERE nome='MARIVALDA';"

```

```
 id_cliente | nome      | sobrenome
------------+-----------+--------------------------------------------------
   2b162060 | MARIVALDA | DE ALCÂNTARA FRANCISCO ANTÔNIO [...] KANAMARY

(1 rows)
```

Funciona. O `USING 'sai'` seleciona o **Storage Attached Index**, que na versão 5 substituiu os índices secundários antigos — mais rápidos para escrever, muito menos custosos em memória, e com suporte a mais tipos de consulta.

O nome não é decorativo: o índice está *anexado ao armazenamento*. Veja o que apareceu no diretório da tabela:

```sh
cass sh -c "ls -1 $DIR | grep SAI"

```

> Se o comando não devolver nada, é porque `$DIR` e o atalho `cass` foram definidos na seção 6 e você está em outro terminal. Redefina:
> ```sh
> alias cass='docker exec -it cassandra-database'
> DIR=$(docker exec cassandra-database sh -c 'ls -rtd /var/lib/cassandra/data/lab/cliente-* | tail -1')
> ```

```
nb-4-big-SAI+aa+GroupComplete.db
nb-4-big-SAI+aa+GroupMeta.db
nb-4-big-SAI+aa+PartitionKeyBlockOffsets.db
nb-4-big-SAI+aa+PartitionKeyBlocks.db
nb-4-big-SAI+aa+PartitionToSize.db
nb-4-big-SAI+aa+RowToPartition.db
nb-4-big-SAI+aa+RowToToken.db
nb-4-big-SAI+aa+cliente_nome_sai+ColumnComplete.db
nb-4-big-SAI+aa+cliente_nome_sai+Meta.db
nb-4-big-SAI+aa+cliente_nome_sai+PostingLists.db
nb-4-big-SAI+aa+cliente_nome_sai+TermsData.db
```

Onze componentes novos, com o prefixo da SSTable que você já conhece. Os quatro últimos trazem o nome do índice; os sete primeiros são estrutura compartilhada, reaproveitável por outros índices SAI na mesma tabela. O índice é parte da SSTable, e é reconstruído a cada flush e a cada compactação — junto do dado, pelo mesmo mecanismo da seção 6. Índice não é grátis: custa disco e custa em cada escrita.

#### Por que isso não substitui a modelagem

Ligue o `TRACING` e leia com cuidado:

```sh
cql "TRACING ON; SELECT id_cliente, nome FROM lab.cliente WHERE nome='MARIVALDA';"

```

```
Index mean cardinalities are cliente_nome_sai:9223372036854775807. Scanning with cliente_nome_sai.
Computing ranges to query
Submitting range requests on 17 ranges with a concurrency of 17
Executing read on lab.cliente using index cliente_nome_sai
Executing single-partition query on cliente
Read 1 live rows and 0 tombstone cells
Index query accessed memtable indexes, 1 SSTable index, and 1 segment,
post-filtered 1 row in 1 partition, and took 910 microseconds.
```

A boa notícia está no fim: **1 linha lida, 1 partição** — nada de varredura sequencial como no `ALLOW FILTERING` da seção 8.6.

A notícia importante está no meio: **`Submitting range requests on 17 ranges`**. O índice SAI é **local a cada nó**: ele sabe onde está o dado *dentro* do nó, mas não sabe em qual nó procurar. Então o coordenador pergunta a todos.

Aqui há um nó e 17 faixas de token. Num cluster de cinquenta nós, essa consulta fala com os cinquenta, e a resposta depende do mais lento deles. Compare com `cliente_por_cpf`: a partition key diz exatamente qual nó tem o dado, e a consulta fala com um.

| | Vai a quantos nós | Custo por nó |
|---|---|---|
| `WHERE` na partition key (`cliente_por_cpf`) | um | leitura pontual |
| `WHERE` em coluna com SAI | **todos** | leitura pontual |
| `WHERE` com `ALLOW FILTERING` | **todos** | varredura |

O SAI resolve o segundo problema, não o primeiro. Por isso ele é excelente para consulta de baixa frequência sobre coluna de alta cardinalidade — um relatório, uma busca administrativa, um filtro secundário dentro de uma partição já delimitada. E por isso ele **não** é a resposta para a consulta que a tela principal do aplicativo faz a cada acesso. Para essa, a resposta continua sendo a da seção 7: uma tabela cuja partition key é aquilo que você tem em mãos.

Remova o índice antes de seguir:

```sh
cql "DROP INDEX lab.cliente_nome_sai;"

```

### UCS — Unified Compaction Strategy

Na seção 6 você viu três SSTables virarem uma. A estratégia que decidiu isso apareceu no `DESCRIBE TABLE`:

```sh
cql "SELECT compaction FROM system_schema.tables WHERE keyspace_name='lab' AND table_name='cliente';"

```

```
{'class': 'org.apache.cassandra.db.compaction.SizeTieredCompactionStrategy', 'max_threshold': '32', 'min_threshold': '4'}
```

Historicamente era preciso escolher entre estratégias com comportamentos bem diferentes — `SizeTiered` (barata para escrever, ruim para ler), `Leveled` (o oposto), `TimeWindow` (para série temporal) — e trocar de estratégia depois, com a tabela em produção, era operação delicada.

A versão 5 trouxe a **Unified Compaction Strategy**, que unifica as duas primeiras em um único algoritmo com um parâmetro:

```sh
cql "ALTER TABLE lab.cliente WITH compaction = {'class':'UnifiedCompactionStrategy'};"

```

```sh
cql "SELECT compaction FROM system_schema.tables WHERE keyspace_name='lab' AND table_name='cliente';"

```

```
{'class': 'org.apache.cassandra.db.compaction.UnifiedCompactionStrategy'}
```

O parâmetro é o `scaling_parameters`:

| Valor | Comportamento |
|---|---|
| `T4`, `T8`… | *tiered*: menos trabalho de compactação, leitura toca mais arquivos |
| `L4`, `L8`… | *leveled*: mais trabalho de compactação, leitura toca menos arquivos |
| `N` | o meio do caminho |

```sh
cql "ALTER TABLE lab.cliente WITH compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'T4'};"

```

Também é possível declarar valores diferentes por nível, o que permite ser econômico nos dados recentes e agressivo nos antigos — algo que nenhuma estratégia anterior fazia.

> **O que este laboratório não mostra.** A diferença entre `T4` e `L4` aparece em carga sustentada de escrita, com gigabytes e dezenas de SSTables. Numa tabela de seis linhas, trocar a estratégia muda o que o `DESCRIBE TABLE` informa e nada mais. O que fica desta seção é onde essa decisão vive e o que ela negocia: **trabalho de compactação contra número de arquivos que uma leitura precisa consultar** — a mesma troca da seção 6, agora com um dial só.

Devolva a tabela à estratégia padrão:

```sh
cql "ALTER TABLE lab.cliente WITH compaction = {'class':'SizeTieredCompactionStrategy'};"

```

**→ Parte III.** Todas as consultas até aqui foram digitadas no `cqlsh`. Nenhum aplicativo funciona assim. Vamos executar o mesmo fluxo Q1 a Q7 de dentro de uma aplicação Python.

## 10. O driver Python

> Em elaboração (fase A5).

## 11. Enunciado

> Em elaboração (fase A6).

## A. Busca vetorial

> Em elaboração (fase A6).

## B. Encerrando o ambiente

```sh
docker compose down -v

```

O `-v` remove também o volume de dados. Como as duas keyspaces são recriadas em cerca de 30 segundos no próximo `up`, não há motivo para preservá-las.

## C. Troubleshooting

> Em elaboração (fase A6).

Enquanto isso, para verificar o ambiente:

```sh
bash scripts/check.sh

```

## D. Nota para o instrutor

> Em elaboração (fase A6).

---

## Plano de revisão

Esta branch reformula o laboratório, que antes estava dividido em sete subdiretórios, em um arquivo único e com um fio condutor só. O que mudou de fato:

| | |
|---|---|
| **Um único jeito de digitar** | Antes, o aluno entrava no container na seção 2, saía na 6 e voltava na 7. Agora tudo roda do host, via `alias`. |
| **Um único enredo** | Antes eram quatro keyspaces sem relação declarada (`ks001`, `infobarbank`, `ecommerce`, `infobarbank5`). Agora são três, com papéis explícitos. |
| **Cluster sai** | Tokens, réplicas e disponibilidade ganham repositório próprio. O que dava para manter em um nó — fator de replicação e consistency level — ficou. |
| **Cassandra 5 entra** | O laboratório se chamava `cassandra5` e não usava nenhum recurso da versão 5. Entram SAI, UCS e busca vetorial. |
| **Modelagem é o centro** | O modelo do `infobarbank` deixa de ser cenário e passa a ser o objeto: cada uma das doze tabelas é lida a partir da consulta que a motivou. |

Fases: **A0** estrutura · **A1** seções 1–3 (feitas) · A2 seções 4–5 · A3 seção 6 · A4 seções 7–9 · A5 seção 10 · A6 seção 11 e apêndices · A7 execução completa em ambiente limpo, com todos os outputs regerados.

### Pendências da revisão

- As URLs de `wget` e `curl` apontam para a branch `revisao-julho2026`, para que ela seja executável antes do merge. **No merge, trocar por `main`.**
- As imagens `ghcr.io/infobarbosa/cassandra-gerador-esquema-{infobarbank,ecommerce}` precisam ser publicadas e tornadas públicas. Enquanto isso, o `compose.yaml` só funciona em máquina que as tenha construído localmente.
- Fator de replicação aparece apenas como parâmetro de `CREATE KEYSPACE`. Alterar RF, `nodetool repair` e o comportamento de cada consistency level sob falha vão inteiros para o laboratório de cluster — demonstrar isso com um nó exigiria encenar uma configuração que ninguém usa.

### Mapa do que saiu

| Antes | Agora |
|---|---|
| `01-Cassandra-Start/` | seção 1 |
| `02-cqlsh/` | seção 2 |
| `03-Keyspaces/` | seção 3 |
| `04-Tables/` | seções 4 e 5 |
| `05-Datafiles/` | seção 6 |
| `06-Cluster/` | repositório próprio, a ser criado |
| `07-Cassandra-Driver/` | seção 10 |
| `ecommerce-samples.md` | seção 11 |
| `assets/scripts/standalone/compose.yaml` | `compose.yaml`, na raiz |
| `assets/scripts/cluster/*.yaml` | repositório de cluster |
