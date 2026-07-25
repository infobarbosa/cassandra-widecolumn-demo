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

> Em elaboração (fase A3).

## 7. Não existe JOIN — existe outra tabela

> Em elaboração (fase A4).

## 8. Chave primária na prática

> Em elaboração (fase A4).

## 9. Cassandra 5: SAI e UCS

> Em elaboração (fase A4).

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
