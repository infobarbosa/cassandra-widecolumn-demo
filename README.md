# Wide-column com Apache Cassandra 5

Author: Prof. Barbosa<br>
Contact: infobarbosa@gmail.com<br>
Github: [infobarbosa](https://github.com/infobarbosa)

[Cassandra](https://cassandra.apache.org/) é um banco de dados distribuído com modelo de armazenamento **wide-column**. Neste laboratório você vai construir uma tabela do zero, acompanhar o dado descer até o disco, descobrir o limite de consulta que o Cassandra impõe — e então ver como um sistema real resolve esse limite.

O laboratório inteiro cabe neste arquivo. Os comandos são copy-paste em terminal Linux, na ordem em que aparecem.

---

## O que você vai saber fazer ao final

- Criar keyspaces e declarar a estratégia de replicação adequada à topologia.
- Escrever `CREATE TABLE` cujo `PRIMARY KEY` responde a uma consulta específica, e explicar a diferença entre **partition key** e **clustering key**.
- Prever em qual partição uma linha vai cair, e por que a ordem física dos dados no disco é uma decisão de modelagem.
- Aplicar **bucketing** para impedir que uma partição cresça sem limite, e escolher a granularidade do bucket.
- Acompanhar o caminho de escrita — commit log, memtable, SSTable, compactação, tombstone — observando os arquivos que o Cassandra cria.
- Aplicar **modelagem orientada a consultas**: partir do fluxo de telas e chegar à `PRIMARY KEY` de cada tabela.
- Reconhecer a **desnormalização** como padrão e não como exceção, medir os três custos que ela cobra, e decidir quando uma consulta merece tabela própria.
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
| **II** | Modelagem orientada a consultas: de sete consultas a doze tabelas | `infobarbank` | ~90 min |
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

---

## 1. O ambiente

Baixe o arquivo do Docker Compose:

```sh
wget https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/main/compose.yaml

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
cassandra-init-ecommerce  | Carregadas 11959 linhas em pedido_detalhe (2.6s).
cassandra-init-ecommerce  | Keyspace ecommerce pronta em 25.8s. Cliente-âncora: CLI-000001.
```

> Para sair do `logs -f`, digite `Control+C` uma única vez.

### O que foi criado

```sh
docker ps -a

```

```
NAMES                        IMAGE                                        STATUS
cassandra-init-ecommerce     ...cassandra-gerador-esquema-ecommerce:3.0   Exited (0) 4 minutes ago
cassandra-init-infobarbank   ...cassandra-gerador-esquema-infobarbank:1.0 Exited (0) 4 minutes ago
cassandra-database           cassandra:5.0.8                              Up 6 minutes (healthy)
```

Os dois containers de carga aparecem como `Exited (0)`, e **é isso que se espera deles**: cada um cria a sua keyspace, insere os dados e termina. `Exited (0)` significa que terminaram sem erro. Só o `cassandra-database` fica no ar.

### Verificando o ambiente

```sh
curl -sS https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/main/scripts/check.sh | bash

```

```
Keyspaces
  ✓ infobarbank: 12 tabelas (modelagem de dados)
  ✓ ecommerce: 9 tabelas (trabalho final)
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

O outro extremo — uma partição que cresce sem limite — é um problema de verdade, e existe uma técnica para controlá-lo. Ela tem seção própria: 8.4.

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
/var/lib/cassandra/data/lab/cliente-547a6700885d11f192528d1521edebb1
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
-rw-r--r-- 1 cassandra cassandra 33554432 Jul 25 19:16 CommitLog-7-1785006544169.log
-rw-r--r-- 1 cassandra cassandra 33554432 Jul 25 19:16 CommitLog-7-1785006544170.log
```

Os 32 MB de cada arquivo são **pré-alocados**: o tamanho não diz nada sobre quanto dado existe. O Cassandra reserva o espaço adiantado justamente para que a escrita seja uma gravação sequencial no fim de um arquivo que já está lá.

Procure algo que só existe por causa do que você fez na seção 4 — a linha fantasma do upsert:

```sh
cass sh -c "grep --text -o 'FANTASMA' /var/lib/cassandra/commitlog/*.log"

```

```
/var/lib/cassandra/commitlog/CommitLog-7-1785006544169.log:FANTASMA
```

O `grep` informa em qual dos arquivos encontrou — os nomes serão outros no seu ambiente, porque incluem o instante de criação do segmento. E o e-mail que você atualizou:

```sh
cass sh -c "grep --text -o 'aldenora.moreira@bmail.com' /var/lib/cassandra/commitlog/*.log"

```

```
/var/lib/cassandra/commitlog/CommitLog-7-1785006544169.log:aldenora.moreira@bmail.com
```

Está tudo ali, em texto claro. Agora experimente com um nome:

```sh
cass sh -c "grep -c --text 'MARIVALDA' /var/lib/cassandra/commitlog/*.log"

```

```
/var/lib/cassandra/commitlog/CommitLog-7-1785006544169.log:9
/var/lib/cassandra/commitlog/CommitLog-7-1785006544171.log:0
```

Nove ocorrências, e você inseriu a Marivalda uma vez. O motivo: **o commit log é do nó, não da tabela**. Ele recebe as escritas de todas as tabelas de todas as keyspaces, em um único fluxo sequencial — e a Marivalda também é cliente do `infobarbank` e da loja `ecommerce`, cada um com suas tabelas.

Isso responde por que a escrita não fica mais lenta conforme você cria tabelas: há um só arquivo recebendo tudo, e nunca uma busca por posição.

> O número que você vai ver depende de **quanto tempo faz que o ambiente subiu**. O commit log não é histórico permanente: quando todas as tabelas de um segmento já descarregaram seus dados em SSTables, o Cassandra recicla aquele segmento. Se você criou o ambiente agora, as escritas das duas keyspaces do curso ainda estão lá e a contagem é 9. Algumas horas depois, elas terão sido recicladas e sobra só a sua — o que é a mesma lição vista de outro ângulo: o commit log existe para sobreviver a uma queda, não para guardar histórico.

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
-rw-r--r-- 1 cassandra cassandra   47 Jul 25 19:16 nb-1-big-CompressionInfo.db
-rw-r--r-- 1 cassandra cassandra  338 Jul 25 19:16 nb-1-big-Data.db
-rw-r--r-- 1 cassandra cassandra   10 Jul 25 19:16 nb-1-big-Digest.crc32
-rw-r--r-- 1 cassandra cassandra   24 Jul 25 19:16 nb-1-big-Filter.db
-rw-r--r-- 1 cassandra cassandra   78 Jul 25 19:16 nb-1-big-Index.db
-rw-r--r-- 1 cassandra cassandra 4973 Jul 25 19:16 nb-1-big-Statistics.db
-rw-r--r-- 1 cassandra cassandra   68 Jul 25 19:16 nb-1-big-Summary.db
-rw-r--r-- 1 cassandra cassandra   92 Jul 25 19:16 nb-1-big-TOC.txt
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
0000016 7f ff ff ff 80 00 01 00 f2 33 24 3f 16 8a 8f 08  >.........3$?....<
0000032 0e 37 39 37 2e 33 39 39 2e 35 32 30 2d 30 33 08  >.797.399.520-03.<
0000048 0e 76 65 72 61 40 62 6d 61 69 6c 2e 63 6f 6d 08  >.vera@bmail.com.<
0000064 04 56 45 52 41 08 14 4c 55 43 49 41 20 52 4f 44  >.VERA..LUCIA ROD<
0000080 52 49 47 55 45 53 20 53 45 4e 41 01 58 00 4b 32  >RIGUES SENA.X.K2<
0000096 34 32 61 58 00 f7 0d 83 94 08 0e 31 32 34 2e 35  >42aX.......124.5<
0000112 35 34 2e 32 36 30 2d 35 30 08 12 6a 75 63 69 6c  >54.260-50..jucil<
0000128 65 6e 65 5c 00 f4 21 08 4a 55 43 49 4c 45 4e 45  >ene\..!.JUCILENE<
0000144 08 0c 4d 4f 52 45 49 52 41 20 43 52 55 5a 01 00  >..MOREIRA CRUZ..<
0000160 0a 4e 41 4f 2d 45 58 49 53 54 45 6a 65 0b 8b 00  >.NAO-EXISTEje...<
0000176 06 57 74 53 69 9b c3 71 00 35 35 36 61 17 00 33  >.WtSi..q.556a..3<
[... 10 linhas ...]
0000320 4c 44 41 08 08 4b 41 4e 41 4d 41 52 59 01 5c 28  >LDA..KANAMARY.\(<
0000336 8e a6                                            >..<
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
      "deletion_info" : { "marked_deleted" : "2026-07-25T19:16:27.516867Z", "local_delete_time" : "2026-07-25T19:16:27Z" }
    },
    "rows" : [ ]
  },
  {
    "partition" : {
      "key" : [ "2b16256a" ],
      "position" : 223,
      "deletion_info" : { "marked_deleted" : "2026-07-25T19:16:27.951731Z", "local_delete_time" : "2026-07-25T19:16:27Z" }
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
-rw-r--r-- 1 cassandra cassandra 338 Jul 25 19:16 .../nb-1-big-Data.db
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
630 .../nb-4-big-Data.db
```

Três arquivos viraram um. Isso é **compactação**, e o conceito por trás dela é a [Log-structured merge-tree](https://en.wikipedia.org/wiki/Log-structured_merge-tree), a **LSM tree**: escreve-se sempre em arquivo novo, e a consolidação acontece depois, em segundo plano.

> Se a numeração do seu ambiente for diferente de `nb-1` a `nb-4`, é porque houve algum flush a mais. Use os nomes que o `ls` mostrar.

Veja o que sobrou da Marivalda:

```sh
cass sh -c "/opt/cassandra/tools/bin/sstabledump $DIR/nb-4-big-Data.db"

```

```json
      "key" : [ "2b162060" ],
      "position" : 439
    },
    "rows" : [
      {
        "type" : "row",
        "liveness_info" : { "tstamp" : "2026-07-25T19:16:26.203224Z" },
        "cells" : [
          { "name" : "cpf", "value" : "987.539.360-60" },
          { "name" : "email", "value" : "marivalda@bmail.com" },
          { "name" : "nome", "value" : "MARIVALDA" },
          { "name" : "sobrenome", "value" : "DE ALCÂNTARA [...] BOURBON KANAMARY", "tstamp" : "2026-07-25T19:16:32.571401Z" }
        ]
      }
    ]
```

Uma única célula `sobrenome`, com o valor novo. E repare no detalhe: ela tem **timestamp próprio**, `19:16:32`, diferente do `liveness_info` da linha, `19:16:26`. O timestamp no Cassandra é por célula, não por linha — o que explica como a compactação resolveu o conflito sem precisar de nada além dos próprios arquivos: para cada célula, vence a escrita mais recente.

### O tombstone que sobreviveu

```sh
cass sh -c "/opt/cassandra/tools/bin/sstabledump $DIR/nb-4-big-Data.db" | grep -B3 deletion_info

```

```json
      "key" : [ "NAO-EXISTE" ],
      "deletion_info" : { "marked_deleted" : "2026-07-25T19:16:27.516867Z", ... }
      "key" : [ "2b16256a" ],
      "deletion_info" : { "marked_deleted" : "2026-07-25T19:16:27.951731Z", ... }
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

Isso tem nome.

### Desnormalização

**Desnormalização** é gravar o mesmo dado em mais de um lugar para que cada consulta encontre tudo o que precisa num só lugar. É o oposto da normalização que você aprendeu em modelagem relacional, onde cada fato existe uma vez e as consultas o remontam com `JOIN`.

A palavra é a mesma nos dois mundos, mas o papel se inverte:

| | Relacional | Cassandra |
|---|---|---|
| A regra | normalizar; cada fato uma vez | uma tabela por consulta |
| Desnormalizar é | **exceção**, um desvio justificado por desempenho | **o padrão** |
| Quem reclama de uma cópia fora de sincronia | o banco, com chave estrangeira e transação | **ninguém** |

A terceira linha é a que custa caro, e vamos medir as duas primeiras antes de chegar nela.

#### O que as quatro cópias custam, medido

Quantas linhas em cada uma das quatro tabelas?

```sh
cql "
SELECT count(*) FROM infobarbank.cliente;
SELECT count(*) FROM infobarbank.cliente_por_cpf;
SELECT count(*) FROM infobarbank.cliente_por_email;
SELECT count(*) FROM infobarbank.cliente_por_telefone;"

```

Cinquenta em cada, com um aviso em cada — `Aggregation query used without partition key`, que é o Cassandra dizendo que para contar ele varreu a tabela inteira. Guarde o aviso: até `count(*)` é uma varredura.

Agora o espaço em disco:

```sh
nt tablestats infobarbank.cliente infobarbank.cliente_por_cpf infobarbank.cliente_por_email infobarbank.cliente_por_telefone

```

O comando imprime umas trinta linhas por tabela. Três delas interessam:

```
  Table: cliente
  Space used (total): 10063
  Number of partitions (estimate): 50

  Table: cliente_por_cpf
  Space used (total): 9760
  Number of partitions (estimate): 30

  Table: cliente_por_email
  Space used (total): 10425
  Number of partitions (estimate): 50

  Table: cliente_por_telefone
  Space used (total): 10257
  Number of partitions (estimate): 49
```

Cerca de **40 KB para armazenar 10 KB de clientes** — o fator quatro, medido. Num banco com cinquenta milhões de clientes seria a diferença entre 10 GB e 40 GB, e é o custo mais fácil de aceitar dos três: disco é barato e previsível.

Antes de seguir, olhe a linha de partições, porque ela denuncia algo que as contagens escondem. As quatro tabelas têm 50 linhas, mas `cliente_por_cpf` estima **30 partições** e `cliente_por_telefone`, **49**. Menos partições que linhas significa linhas diferentes com a mesma chave. Esse número é uma estimativa — confirme contando as chaves distintas:

```sh
cql "SELECT DISTINCT cpf FROM infobarbank.cliente_por_cpf;"

```

```
 cpf
----------------
 324.873.000-51
 219.384.290-89
 129.384.250-60
[...]

(30 rows)
```

Trinta chaves para cinquenta linhas. E é aqui que aparece a lição, que vale para qualquer tabela de acesso alternativo:

> `cliente_por_cpf` foi modelada supondo que **o CPF identifica uma pessoa**. Quando essa suposição falha, o Cassandra não avisa: não existe `UNIQUE`, não existe chave estrangeira, e um `INSERT` com chave que já existe é um upsert (seção 4) — sobrescreve, sem erro e sem log. **A partition key carrega uma afirmação sobre unicidade, e ninguém a verifica para você.**

Vale separar as duas repetições desta base, porque só uma delas é realista:

| | O que é |
|---|---|
| **telefone**, 49 chaves para 50 linhas | plausível em produção — duas pessoas da mesma casa, um celular corporativo. Uma tela que espera uma pessoa vai receber duas |
| **CPF**, 30 chaves para 50 linhas | **artefato desta base.** CPF é único por lei; foi a lista de personas do gerador que repetiu valores |

Ou seja: não tome o CPF repetido como retrato de produção. Tome-o como o que ele é — a chance de ver, em dado real, o que acontece quando a premissa de unicidade de uma partition key é falsa. O que se leva daqui é o hábito: **antes de eleger uma coluna como partition key, prove que ela é única na sua base**, porque o banco não vai reclamar depois.

E guarde a pergunta, porque a resposta está em 8.2: se o CPF se repete, por que as trinta pessoas com CPF repetido **não** se sobrescreveram? Quem modelou a `cliente_por_cpf` já contava com isso.

Consequência operacional, para não te confundir mais adiante: consultar `cliente_por_cpf` por um desses CPFs devolve **várias pessoas**. O CPF da Marivalda é único, e é o usado em todos os exemplos deste laboratório — assim como as outras seis clientes com movimento. Se você trocar de cliente por conta própria, confira antes.

#### O custo que dói: não existe transação

O segundo custo é escrever quatro vezes em vez de uma. O terceiro é o que quebra sistema em produção, e é melhor ver do que ler. Faça na sua bancada.

Crie uma tabela de acesso por e-mail para a `lab.cliente`, do mesmo jeito que o banco fez:

```sh
cql "
CREATE TABLE lab.cliente_por_email (
  email text PRIMARY KEY,
  id_cliente text,
  nome text
);
INSERT INTO lab.cliente_por_email (email, id_cliente, nome) VALUES ('marivalda@bmail.com','2b162060','MARIVALDA');"

```

Duas tabelas, o mesmo dado, tudo em ordem. Agora a Marivalda troca de e-mail, e a aplicação atualiza o cadastro:

```sh
cql "UPDATE lab.cliente SET email = 'marivalda.kanamary@bmail.com' WHERE id_cliente = '2b162060';"

```

Nenhum erro. Amanhã ela tenta entrar com o e-mail novo:

```sh
cql "SELECT * FROM lab.cliente_por_email WHERE email = 'marivalda.kanamary@bmail.com';"

```

```
 email | id_cliente | nome
-------+------------+------

(0 rows)
```

**O login falhou.** E o e-mail antigo, que ela não usa mais, continua funcionando:

```sh
cql "SELECT * FROM lab.cliente_por_email WHERE email = 'marivalda@bmail.com';"

```

```
 email               | id_cliente | nome
---------------------+------------+-----------
 marivalda@bmail.com |   2b162060 | MARIVALDA
```

Duas tabelas discordam sobre um fato, e **o banco não reclamou em nenhum momento.** Não existe chave estrangeira ligando as duas, não existe transação abrangendo as duas, não existe `ROLLBACK`. O `UPDATE` que faltou é código da aplicação, e esquecê-lo produz um dado que existe em duas versões — sem erro, sem log, sem aviso.

Piora um pouco. O conserto óbvio não é permitido:

> **Provoque este erro.**

```sh
cql "UPDATE lab.cliente_por_email SET email = 'marivalda.kanamary@bmail.com' WHERE email = 'marivalda@bmail.com';"

```

```
InvalidRequest: ... "PRIMARY KEY part email found in SET part"
```

O e-mail é a partition key: ele **decide em que partição a linha mora**. Mudá-lo não é alterar um campo, é mudar a linha de lugar — e isso, para o Cassandra, são duas operações. Insira a nova e apague a velha:

```sh
cql "
INSERT INTO lab.cliente_por_email (email, id_cliente, nome) VALUES ('marivalda.kanamary@bmail.com','2b162060','MARIVALDA');
DELETE FROM lab.cliente_por_email WHERE email = 'marivalda@bmail.com';
SELECT * FROM lab.cliente_por_email;"

```

```
 email                        | id_cliente | nome
------------------------------+------------+-----------
 marivalda.kanamary@bmail.com |   2b162060 | MARIVALDA
```

Some a tabela auxiliar e devolva o e-mail original — as próximas seções usam a `lab.cliente` como ela estava:

```sh
cql "
DROP TABLE lab.cliente_por_email;
UPDATE lab.cliente SET email = 'marivalda@bmail.com' WHERE id_cliente = '2b162060';"

```

Some a conta: **uma troca de e-mail custou um `UPDATE`, um `INSERT` e um `DELETE`, em duas tabelas, e nenhum deles é opcional.** Em relacional teria sido um `UPDATE`. É esse trabalho que a desnormalização transfere da consulta para a escrita, e da consulta para a aplicação.

#### O que se compra com isso

Qualquer uma das três telas de login responde com uma **leitura pontual, em uma partição, em um nó**, com custo que não muda quando a base cresce de mil para um bilhão de clientes.

> Essa é a frase que resume a modelagem em Cassandra: **escreve-se o dado N vezes para lê-lo barato N vezes.** No modelo relacional o dado é guardado uma vez e a consulta faz o trabalho; aqui a escrita faz o trabalho e a consulta é trivial.

E a Marivalda que você cadastrou na seção 4, com o mesmo `id_cliente` `2b162060`? É a mesma pessoa. A diferença é que aqui ela existe em um modelo que foi projetado a partir das perguntas que o sistema faz.

#### Quando desnormalizar, e quando não

A regra, e ela erra para os dois lados:

> Crie uma tabela por **caminho de acesso que precisa ser rápido**. Cada tabela nova soma uma escrita a cada mudança e uma cópia a manter em sincronia.

| Erro | Sintoma |
|---|---|
| **Tabelas de menos** | a consulta cai em `ALLOW FILTERING`, varredura, latência que cresce com a base (seção 8.7) |
| **Tabelas demais** | amplificação de escrita e superfície de bug de sincronia — a falha que você acabou de provocar, multiplicada |

Duas perguntas resolvem a maioria dos casos:

1. **Com que frequência essa consulta acontece?** A tela principal do aplicativo merece tabela. Um relatório mensal e uma busca do atendimento, não — para esses existem o índice SAI (seção 9) e o processamento em lote.
2. **Esse dado muda mais do que é lido?** Se muda, a troca se inverte: cada alteração paga N escritas por uma leitura que talvez não venha. Dado de cadastro — nome, CPF, e-mail — muda uma vez por ano e é lido todo dia, e por isso desnormalizar compensa tanto aqui.

#### Onde mais a desnormalização aparece neste laboratório

Agora que a técnica tem nome, ela fica visível em quase toda tabela que você vai ver:

| O mesmo dado, repetido em | Para atender |
|---|---|
| `infobarbank.cliente` + `cliente_por_cpf` + `cliente_por_email` + `cliente_por_telefone` | login por id, por CPF, por e-mail, por telefone |
| `ecommerce.cliente` + `cliente_por_cpf` + `cliente_por_email` | o mesmo, na loja |
| `lancamentos_detalhe` × as quatro tabelas de lançamento | a tela de detalhe e as telas de lista (8.1 e 8.5) |
| `lancamentos_por_periodo` + `_por_produto` + `_por_status` + `_por_tipo` | os mesmos lançamentos, quatro filtros (8.5) |
| `pedido_detalhe` × as tabelas de pedido do `ecommerce` | idem, na loja |

Não existe uma única tabela do `infobarbank` cujo conteúdo não apareça em outra. **É a regra, não a exceção.**

### O que você deve conseguir explicar

- Por que o CQL não tem `JOIN`, em termos de onde os dados estão fisicamente.
- O que é desnormalização, e por que em Cassandra ela é o padrão e não a exceção.
- Os três custos dela: espaço, escrita repetida e ausência de transação — e qual dos três quebra sistema.
- Por que mudar uma partition key exige `INSERT` mais `DELETE`.
- Dada uma consulta que a aplicação precisa fazer, decidir se ela merece uma tabela própria.

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

### Modelagem orientada a consultas

Aquela tabela acima não é documentação do modelo: **é o método.** Ela tem nome — **modelagem orientada a consultas**, ou *query-first design* — e a inversão em relação ao que você aprendeu em relacional é literal:

| | Relacional | Cassandra |
|---|---|---|
| Começa em | entidades e relacionamentos | **as consultas** |
| Depois | normaliza até a 3ª forma normal | uma tabela por consulta (seção 7) |
| As consultas | se adaptam ao modelo, com `JOIN` | **definem** o modelo |
| Consulta nova | quase sempre é só SQL novo | pode ser tabela nova, carga de dados e deploy |

A consequência prática incomoda quem vem do relacional: **não se modela em Cassandra sem saber as consultas.** Um diagrama de entidades correto não produz um modelo Cassandra utilizável, porque a informação que decide a `PRIMARY KEY` não está no diagrama. O que decide é *o que a aplicação tem em mãos no momento da leitura* — e isso está no fluxo de telas, não no modelo conceitual. Foi exatamente o que você viu em 8.1 quando faltava um `id_lancamento`: a chave da Q7 só faz sentido porque a tela anterior entrega o id.

Daí a ordem de trabalho, que é a desta seção:

```
fluxo de telas  →  uma consulta por tela  →  o que a tela tem em mãos  →  PRIMARY KEY  →  tabela
```

E o preço do método, que é honesto declarar agora: **a consulta que ninguém previu não tem tabela.** Nenhuma das doze responde "quais os dez maiores lançamentos da cliente no mês" — não porque seja difícil, mas porque essa tela não existia quando o modelo foi feito. Você vai reencontrar essa pergunta no trabalho final, e as três saídas para ela são as da seção 9 e da seção 8.7: modelar mais uma tabela, aceitar um índice SAI, ou varrer com `ALLOW FILTERING`. Nenhuma é grátis.

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

Use uma competência **do meio da lista** nos exemplos — nem a primeira, nem a última. O motivo aparece ao olhar a data do último lançamento de cada uma:

```sh
cql "SELECT max(data_hora) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-06';"

```

```
 2026-06-29 19:10:14.797000+0000
```

```sh
cql "SELECT max(data_hora) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-07';"

```

```
 2026-07-25 19:10:15.437000+0000
```

A última competência para no dia **25** — que é hoje. Ela é o **mês corrente**, e por isso cobre um mês incompleto. A primeira da lista tem o problema simétrico:

```sh
cql "SELECT min(data_hora) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2025-07';"

```

```
 2025-07-26 19:10:12.988000+0000
```

Começa no dia 26, porque os lançamentos foram distribuídos nos últimos 365 dias — e 365 dias atrás era o dia 26 do mês. **As duas pontas da série são parciais.**

Não é defeito do laboratório: é o que acontece em qualquer base de produção, e é o tipo de detalhe que derruba relatório — um gráfico de movimento por mês mostra queda no mês corrente todos os meses, e quem não souber disso vai procurar explicação de negócio para um artefato do calendário.

> Note que a **contagem** de lançamentos pode não denunciar isso: os lançamentos são sorteados, e um mês incompleto pode acabar com mais registros que um mês fechado. O que denuncia é a data, não o volume.

Nos exemplos a seguir aparece `2026-06`; troque por uma competência intermediária do seu ambiente.

### O que é igual e o que é diferente no seu ambiente

Vale saber antes de comparar resultados:

| | |
|---|---|
| **Igual em qualquer ambiente** | as cinquenta clientes, com nome, CPF, e-mail e telefone; as contas correntes e os cartões, com números, limites e saldos |
| **Sorteado a cada ambiente** | todos os lançamentos — data, valor, estabelecimento, `id_lancamento` e a conta ou cartão que os originou |

Ou seja: os resultados de Q1 e Q2 abaixo devem coincidir com os seus. Os de Q3 a Q7, não — a forma da resposta é a mesma, os valores são outros.

### 8.1 Partition key de coluna única

O caso mais simples, o mesmo da sua `lab.cliente`: a `PRIMARY KEY` tem uma coluna, que é a partition key. Uma partição, uma linha.

A tabela `cliente` do banco tem exatamente essa forma:

```sh
cql "DESCRIBE TABLE infobarbank.cliente;"

```

```
    id_cliente text PRIMARY KEY,
```

Repare **onde** essa declaração aparece: na própria linha da coluna. É a forma que o CQL usa quando a chave tem uma coluna só. Da seção 8.2 em diante você vai ver a outra forma, uma cláusula `PRIMARY KEY (...)` separada, no fim da lista de colunas — ela é obrigatória assim que a chave tem mais de uma coluna, porque aí a **ordem** das colunas importa e não haveria como expressá-la linha por linha.

Recupere a Marivalda:

```sh
cql "SELECT id_cliente, nome_completo, cpf, estado FROM infobarbank.cliente WHERE id_cliente='2b162060';"

```

```
 id_cliente | nome_completo      | cpf            | estado
------------+--------------------+----------------+--------
   2b162060 | MARIVALDA KANAMARY | 987.539.360-60 |     SP
```

Esta é uma das saídas que devem coincidir **exatamente** com a sua — clientes não são sorteados. Use como calibração antes de entrar nas tabelas de lançamento, onde os valores mudam a cada ambiente.

#### A mesma forma na Q7 — e o id que você não tem

A **Q7** é o detalhe de um lançamento, e usa a mesma chave de uma coluna:

```sh
cql "DESCRIBE TABLE infobarbank.lancamentos_detalhe;"

```

```
    id_lancamento text PRIMARY KEY,
```

Mesma forma, outra tabela. Só que aqui aparece um problema que a `cliente` não tem: **você não sabe nenhum `id_lancamento`.** O `id_cliente` da Marivalda você tinha em mãos — vem do login. Um `id_lancamento` não vem de lugar nenhum, e não se adivinha.

Isso não é inconveniência do laboratório, é a própria mecânica do aplicativo. A tela de detalhe nunca é a primeira: a cliente chega nela **tocando numa linha do extrato**, e é a tela anterior que carrega o id. Então faça o que o aplicativo faz — leia o extrato primeiro:

```sh
cql "
SELECT id_lancamento, data_hora, estabelecimento, valor
FROM infobarbank.lancamentos_por_periodo
WHERE id_cliente='2b162060' AND competencia='2026-06'
LIMIT 5;"

```

```
 id_lancamento | data_hora                       | estabelecimento     | valor
---------------+---------------------------------+---------------------+-----------
      ccf7c105 | 2026-06-27 19:41:51.601000+0000 |   Posto de gasolina |    957.63
      7bf5dcc8 | 2026-06-20 19:41:49.440000+0000 |             Padaria |    471.91
      a9f23932 | 2026-06-18 19:41:50.544000+0000 | Loja de eletrônicos | 297.51999
      6685149f | 2026-06-17 19:41:52.338000+0000 |     Salão de beleza |    150.47
      7133781c | 2026-06-17 19:41:52.081000+0000 |      Loja de roupas |     159.3
```

Os seus cinco ids são outros. **Escolha qualquer um deles** e siga com ele nos comandos abaixo.

> Repare que não há `ORDER BY` e ainda assim vieram os cinco mais recentes. A ordenação já está gravada no disco — é assunto de 8.2, e é o que faz o `LIMIT` ser barato aqui.

Agora a Q7, com o id que você escolheu:

```sh
cql "
SELECT id_lancamento, data_hora, estabelecimento, valor, status, codigo_autenticacao
FROM infobarbank.lancamentos_detalhe
WHERE id_lancamento='ccf7c105';"

```

```
 id_lancamento | data_hora                       | estabelecimento   | valor  | status   | codigo_autenticacao
---------------+---------------------------------+-------------------+--------+----------+--------------------------------------
      ccf7c105 | 2026-06-27 19:41:51.601000+0000 | Posto de gasolina | 957.63 | APROVADA | 74769828-a8a8-4244-b9c6-506a4adc758a
```

Confira contra a listagem anterior: mesmo estabelecimento, mesma data, mesmo valor. **É o mesmo lançamento, gravado em duas tabelas** — a listagem numa, o detalhe na outra. É a desnormalização da seção 7, agora entre tabelas de lançamento: a tela de extrato e a tela de detalhe são duas consultas, então são duas tabelas.

E repare no que a `lancamentos_detalhe` tem de diferente das outras tabelas de lançamento: uma coluna a mais, `codigo_autenticacao`. A tela de detalhe é a única que mostra esse campo, então ele existe só aqui. **Tabela por consulta significa também colunas por consulta.**

Duas leituras, duas partições, dois nós possíveis num cluster — e é assim que a tela funciona. Guarde o par: **uma consulta entrega a lista, outra entrega o detalhe, e o id é o que passa de uma para a outra.**

### 8.2 Partition key mais clustering key

Agora a `PRIMARY KEY` tem duas partes. A **Q1**, dados da conta:

```sh
cql "DESCRIBE TABLE infobarbank.conta_corrente;"

```

```
    PRIMARY KEY (id_cliente, status, id_conta)
) WITH CLUSTERING ORDER BY (status ASC, id_conta ASC)
```

Leia a cláusula da esquerda para a direita: a **primeira** coluna é a partition key, as demais são clustering keys. Aqui é `id_cliente` que decide a partição, e o `CLUSTERING ORDER BY` que veio de brinde confirma quem são as outras duas.

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

E não é hipótese. É exatamente o que você mediu na seção 7: **30 partições para 50 clientes.** Se a chave fosse apenas `cpf`, aqueles trinta clientes que dividem dez CPFs teriam virado dez linhas, e vinte pessoas simplesmente não existiriam nesta tabela — sem erro, sem aviso. A clustering key é o que impede isso. Comprove:

```sh
cql "SELECT cpf, id_cliente, nome_completo FROM infobarbank.cliente_por_cpf WHERE cpf='892.394.120-12';"

```

```
 cpf            | id_cliente | nome_completo
----------------+------------+------------------------
 892.394.120-12 |   2b165b48 | CARLOS EDUARDO MARTINS
 892.394.120-12 |   2b16727c | ROBERTO CARLOS MARTINS
 892.394.120-12 |   2b1689b0 |  MARIA EDUARDA MARTINS
 892.394.120-12 |   2b168c02 | RODRIGO CARLOS MARTINS

(4 rows)
```

Quatro pessoas, uma partição, quatro linhas ordenadas por `id_cliente`. A tela de login que espera uma pessoa recebe quatro — e o problema passou a ser da aplicação, não do banco. Mas **o dado está lá**, e é isso que a clustering key comprou.

> Os quatro têm o mesmo sobrenome, o que faz o resultado parecer uma família e a duplicidade parecer plausível. Não é: são quatro personas geradas em sequência a partir do mesmo sobrenome, e CPF continua sendo único por lei. Vale como aviso sobre dado sintético — ele às vezes é errado de um jeito que parece certo.

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

Falta explicar a decisão mais importante dessa chave: **por que `competencia` está ali**. Ela não identifica o lançamento, não é pedida pela regra de negócio e obriga toda consulta a informar um mês. É uma coluna que existe por um motivo de engenharia — e esse motivo tem nome. É a próxima seção.

### 8.4 Bucketing: quebrando a partição que não para de crescer

Imagine a chave sem a competência: `PRIMARY KEY ((id_cliente), data_hora, id_lancamento)`. Fica mais simples, e a consulta por período fica melhor — um intervalo de datas qualquer, sem precisar saber de mês nenhum.

O problema é que a partição de cada cliente passa a **crescer para sempre**. Uma partição não se divide entre nós: o cluster escala em **número** de partições, não em tamanho delas. Dez anos de extrato de um cliente ativo viram uma única partição, num único nó.

Acrescentar a competência à partition key quebra esse histórico em uma partição por mês. A técnica tem nome: **bucketing**. Consiste em incluir na partition key uma coluna cuja única função é **limitar quantas linhas caem em cada partição** — quase sempre derivada do tempo.

#### O tamanho do problema, medido

Vamos construir a versão sem bucket e comparar. Primeiro a tabela:

```sh
cql "
CREATE TABLE lab.lancamento_sem_bucket (
    id_cliente      text,
    data_hora       timestamp,
    id_lancamento   text,
    estabelecimento text,
    valor           float,
    PRIMARY KEY ((id_cliente), data_hora, id_lancamento)
) WITH CLUSTERING ORDER BY (data_hora DESC, id_lancamento ASC);"

```

Agora 200 mil lançamentos de **uma só cliente**, distribuídos em dez anos — o que um correntista ativo acumula em uma década:

```sh
LC_ALL=C awk 'BEGIN{
  srand(42);
  split("Supermercado,Restaurante,Farmácia,Padaria,Posto de gasolina", est, ",");
  print "id_cliente,data_hora,id_lancamento,estabelecimento,valor";
  for (i = 0; i < 200000; i++)
    printf "2b162060,%d,%08x,%s,%.2f\n", 1451606400000 + i * 1576800, i, est[int(rand()*5)+1], 10 + rand()*990;
}' > lancamentos.csv

```

```sh
docker cp lancamentos.csv cassandra-database:/tmp/

```

```sh
cql "COPY lab.lancamento_sem_bucket (id_cliente, data_hora, id_lancamento, estabelecimento, valor) FROM '/tmp/lancamentos.csv' WITH HEADER=TRUE;"

```

```
200000 rows imported from 1 files in 0 day, 0 hour, 0 minute, and 2.103 seconds (0 skipped).
```

> Duas coisas sobre esse `awk`. A coluna `data_hora` é gerada como **epoch em milissegundos** (`1451606400000` é 1º de janeiro de 2016), formato que o `COPY` aceita para colunas `timestamp` — assim não dependemos de nenhuma extensão de `awk` para formatar datas. E o `LC_ALL=C` não é enfeite: em locale brasileiro, `%.2f` imprime `395,46` com vírgula, o que quebraria o CSV em uma coluna a mais.

Force a descida para o disco e compare as duas tabelas:

```sh
cass nodetool flush lab lancamento_sem_bucket

```

```sh
cass nodetool tablestats lab.lancamento_sem_bucket

```

```
  Number of partitions (estimate): 1
  Compacted partition maximum bytes: 10090808
  Compacted partition mean bytes: 10090808
```

```sh
cass nodetool tablestats infobarbank.lancamentos_por_periodo

```

```
  Number of partitions (estimate): 91
  Compacted partition maximum bytes: 2759
  Compacted partition mean bytes: 934
```

| | partições | maior partição |
|---|---|---|
| sem bucket | 1 | 10.090.808 bytes |
| com bucket | 91 | 2.759 bytes |

Uma partição de **10 MB**, contra 2,7 KB. E isso com 200 mil linhas de **uma** cliente.

#### Onde o problema realmente aparece

Aqui está a parte que costuma surpreender. Uma leitura pontual dentro da partição gigante continua rápida:

```sh
cql "SELECT count(*) FROM lab.lancamento_sem_bucket WHERE id_cliente='2b162060' AND data_hora >= '2020-06-01' AND data_hora < '2020-06-08';"

```

```
   384
```

Responde em meio segundo. O índice da partição mais as clustering keys levam direto ao trecho pedido, e o tamanho da partição quase não pesa. Já atravessar a partição inteira custa:

```sh
cql "SELECT count(*) FROM lab.lancamento_sem_bucket WHERE id_cliente='2b162060';"

```

```
 200000
```

Três vezes mais lento — e com 200 mil linhas isso ainda é tolerável. Agora que houve leituras, o `tablehistograms` mostra a distribuição das duas tabelas lado a lado:

```sh
cass nodetool tablehistograms lab lancamento_sem_bucket

```

```
Percentile      Read Latency     Write Latency          SSTables    Partition Size        Cell Count
                    (micros)          (micros)                             (bytes)
50%                   215.00             35.00              1.00          10090808            454826
99%                   372.00           1916.00              1.00          10090808            454826
```

```sh
cass nodetool tablehistograms infobarbank lancamentos_por_periodo

```

```
50%                     0.00              0.00              0.00               770                50
99%                     0.00              0.00              0.00              2759               179
```

454 mil células numa partição contra 179, e uma partição que precisa de uma SSTable inteira para ser lida contra uma que o Cassandra resolve tão rápido que a latência fica abaixo da resolução do instrumento. O problema da partição gigante não está na leitura pontual; está em tudo que precisa **atravessá-la ou movê-la**:

- **Hotspot.** A partição inteira mora nas mesmas réplicas. Um cliente muito ativo concentra carga em poucos nós, e nenhum rebalanceamento resolve, porque partição não se divide.
- **Compactação e repair.** As duas operam sobre partições inteiras. Uma partição de gigabytes pressiona heap e GC em cada ciclo.
- **Leitura completa.** Em escala, ela deixa de ser lenta e passa a estourar o `read_request_timeout` — o servidor desiste antes de terminar.

A regra prática é manter partições **abaixo de ~100 MB**. Nossa partição de 10 MB está confortável; o que interessa é a trajetória: dez anos deram 10 MB para 200 mil linhas, então um cliente com dez vezes mais movimento encosta no teto, e um cliente corporativo o estoura.

#### O preço do bucketing

O bucket não é grátis, e o custo é na consulta. Com a competência na partition key, **não existe intervalo** na coluna de bucket:

> **Provoque este erro.**

```sh
cql "SELECT competencia, data_hora FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia >= '2026-04';"

```

```
InvalidRequest: ... "Cannot execute this query as it might involve data filtering..."
```

Faz sentido, pelo que você viu na seção 5: a partição vem de um hash, e hash não tem ordem. Não existe "as partições entre abril e junho". A saída é listar os buckets desejados:

```sh
cql "
SELECT competencia, count(*)
FROM infobarbank.lancamentos_por_periodo
WHERE id_cliente='2b162060' AND competencia IN ('2026-04','2026-05','2026-06')
GROUP BY competencia;"

```

```
 competencia | count
-------------+-------
     2026-04 |    25
     2026-05 |    22
     2026-06 |    18
```

E para um período que atravessa buckets, combina-se `IN` no bucket com o intervalo na clustering key:

```sh
cql "
SELECT competencia, count(*)
FROM infobarbank.lancamentos_por_periodo
WHERE id_cliente='2b162060' AND competencia IN ('2026-05','2026-06')
  AND data_hora >= '2026-05-20' AND data_hora < '2026-06-10'
GROUP BY competencia;"

```

```
 competencia | count
-------------+-------
     2026-05 |     4
     2026-06 |     4
```

Compare com a tabela sem bucket, onde o mesmo período é um intervalo só, sem que a aplicação precise saber de meses:

```sh
cql "SELECT count(*) FROM lab.lancamento_sem_bucket WHERE id_cliente='2b162060' AND data_hora >= '2020-05-20' AND data_hora < '2020-06-10';"

```

```
   1150
```

**É essa a troca.** O bucket protege o tamanho da partição e cobra dois preços: a aplicação passa a ter de **calcular quais buckets** cobrem o período pedido, e `IN` numa partition key são **N leituras**, possivelmente em N nós, com o coordenador esperando pela mais lenta. Serve para N pequeno. Não serve para "os últimos dois anos" — isso são 24 partições, e a consulta certa aí é outra tabela, com outro bucket.

É também por isso que a tela de extrato do seu banco tem um **seletor de mês** em vez de um campo livre de datas. A interface do aplicativo é consequência do modelo de dados.

#### Escolhendo o tamanho do bucket

A conta é direta:

```
linhas por partição  ≈  taxa de escrita  ×  período do bucket
```

Com o teto de ~100 MB, e mirando algo entre dez mil e cem mil linhas por partição:

| Caso | Taxa de escrita | Bucket | Linhas por partição | |
|---|---|---|---|---|
| extrato bancário | ~20 por mês | mês | ~20 | ✓ |
| pedidos de e-commerce | ~20 por mês | mês | ~20 | ✓ |
| sensor IoT | 1 por segundo | mês | 2,6 milhões | ✗ |
| sensor IoT | 1 por segundo | dia | 86.400 | ✓ |
| ticks de mercado | 1.000 por segundo | hora | 3,6 milhões | ✗ |
| ticks de mercado | 1.000 por segundo | minuto | 60.000 | ✓ |

Erra-se para os **dois** lados. Bucket grande demais devolve o problema da partição gigante. Bucket pequeno demais gera partições demais, e toda consulta de período precisa de um `IN` com muitos valores — trocando um problema de tamanho por um de quantidade de leituras.

E note o que a primeira linha da tabela revela sobre o nosso próprio modelo: com ~20 lançamentos por mês, um bucket **anual** daria 240 linhas por partição, ainda minúsculo. Pelo critério de tamanho, o bucket mensal do `infobarbank` é mais fino do que precisaria ser. Ele foi escolhido para casar com a **consulta** — a tela mostra um mês. Granularidade de bucket se decide pelas duas coisas: o limite de tamanho e o padrão de acesso.

#### Bucket sem tempo

Quando não há dimensão temporal natural, usa-se um bucket **sintético**: `bucket = hash(alguma_coisa) % N`, gravado como coluna e incluído na partition key. Um catálogo com uma categoria de milhões de itens pode virar `((categoria, bucket), item)` com `N = 100`.

O custo muda de forma: como o bucket não tem significado, a leitura precisa consultar **todos os N** e juntar os resultados na aplicação. Isso faz de `N` uma decisão de modelagem — grande o bastante para dividir a partição, pequeno o bastante para a leitura não virar N consultas caras.

#### Onde mais o bucketing aparece neste laboratório

Agora que a técnica tem nome, ela fica visível em todo o material:

| Tabela | Partition key | Bucket |
|---|---|---|
| `infobarbank.lancamentos_por_periodo` e as três irmãs | `(id_cliente, competencia)` | mês |
| `ecommerce.pedidos_por_periodo`, `_status` e `_forma_pagamento` | `(id_cliente, competencia)` | mês |
| `ecommerce.pedidos_por_produto` | `(id_cliente, produto)` | **nenhum** |

A última é a interessante, porque é a exceção. Ela não tem bucket, e isso é escolha, não esquecimento.

O bucket resolve o tamanho da partição, mas cobra um preço na consulta: **quem lê precisa saber o período**. Isso é barato quando a tela mostra um mês — e é exatamente o que as outras fazem. Mas a pergunta que essa tabela responde é *"quantas vezes eu já comprei isto?"*, e o histórico de um produto é justamente a pergunta que **não** tem período em mãos. Com `competencia` na partição, seria uma leitura por mês.

Sem bucket, quem limita o tamanho é a cardinalidade natural do par: um cliente não compra a mesma geladeira dez mil vezes. Confira:

```sh
cql "SELECT count(*) FROM ecommerce.pedidos_por_produto WHERE id_cliente='CLI-000001' AND produto='TABLET';"

```

Vinte e poucas linhas em doze competências — mesma ordem de grandeza das particionadas por mês. **Bucketing é uma troca, não uma regra:** só se paga o preço na consulta quando a partição cresceria sem limite.

Terminada a comparação, libere os 10 MB:

```sh
cql "DROP TABLE lab.lancamento_sem_bucket;"

```

### 8.5 A mesma partição, quatro ordenações

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

### 8.6 Os erros que ensinam

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

O Cassandra não ordena em tempo de consulta: ele **entrega** na ordem em que gravou. Querer os lançamentos por valor não é uma consulta diferente — é uma **tabela** diferente, com `valor` como clustering key. Foi exatamente esse raciocínio que produziu as quatro tabelas de 8.5.

### 8.7 O que o `ALLOW FILTERING` faz

O erro sugere `ALLOW FILTERING` desde a seção 4. Vamos ver o que ele custa, com o `TRACING` ligado.

Primeiro a consulta correta, com a partition key completa:

```sh
cql "TRACING ON; SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE id_cliente='2b162060' AND competencia='2026-06';"

```

Nas linhas do rastro, duas importam:

```
Executing single-partition query on lancamentos_por_periodo
Read 26 live rows and 0 tombstone cells
```

**Uma partição, 26 linhas lidas.** Agora a mesma pergunta, sem informar a cliente, forçando o filtro:

```sh
cql "TRACING ON; SELECT count(*) FROM infobarbank.lancamentos_por_periodo WHERE competencia='2026-06' ALLOW FILTERING;"

```

```
Computing ranges to query
Submitting range requests on 17 ranges with a concurrency of 1 (172.8 rows per range expected)
Executing seq scan across 1 sstables for (min(-9223372036854775808), min(-9223372036854775808)]
Read 171 live rows and 0 tombstone cells
```

Não é mais uma consulta a uma partição: é uma **varredura sequencial** de todo o anel de tokens, de -2⁶³ a 2⁶³-1, para depois descartar o que não bate. Leu 171 linhas para devolver as que interessavam.

O relógio não vai te avisar: esta tabela tem mil linhas, e as duas consultas respondem instantaneamente. É por isso que o Cassandra recusa por padrão em vez de deixar você descobrir — a consulta que varre mil linhas em desenvolvimento varre mil vezes mais em produção, e nesse dia ela não é lenta, ela é uma varredura em todos os nós do cluster ao mesmo tempo.

> `ALLOW FILTERING` tem lugar legítimo: consulta administrativa pontual, exploração de dados, tabela pequena e limitada por natureza. O que ele não é: solução para uma consulta que a aplicação faz a cada requisição.

### O que você deve conseguir explicar

- Por que a modelagem começa no fluxo de telas e não no diagrama de entidades — e o que o diagrama não sabe informar.
- Por que um mesmo dado aparece em quatro tabelas, e quem paga essa conta.
- A diferença entre partition key composta e múltiplas clustering keys — inclusive quais colunas cada uma exige na consulta.
- Por que `ORDER BY` só funciona em clustering key.
- Por que a tela de extrato do seu banco tem um seletor de mês.
- O que é bucketing, o que ele protege, o que ele cobra, e como escolher o período do bucket.
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
post-filtered 1 row in 1 partition, and took 1074 microseconds.
```

A boa notícia está no fim: **1 linha lida, 1 partição** — nada de varredura sequencial como no `ALLOW FILTERING` da seção 8.7.

A notícia importante está no meio: **`Submitting range requests on 17 ranges`**. O índice SAI é **local a cada nó**: ele sabe onde está o dado *dentro* do nó, mas não sabe em qual nó procurar. Então o coordenador pergunta a todos.

Aqui há um nó e 17 faixas de token. Num cluster de cinquenta nós, essa consulta fala com os cinquenta, e a resposta depende do mais lento deles. Compare com `cliente_por_cpf`: a partition key diz exatamente qual nó tem o dado, e a consulta fala com um.

| | Vai a quantos nós | Custo por nó |
|---|---|---|
| `WHERE` na partition key (`cliente_por_cpf`) | um | leitura pontual |
| `WHERE` em coluna com SAI | **todos** | leitura pontual |
| `WHERE` com `ALLOW FILTERING` | **todos** | varredura |

O SAI resolve o segundo problema, não o primeiro. Por isso ele é excelente para consulta de baixa frequência sobre coluna de alta cardinalidade — um relatório, uma busca administrativa, um filtro secundário dentro de uma partição já delimitada. E por isso ele **não** é a resposta para a consulta que a tela principal do aplicativo faz a cada acesso. Para essa, a resposta continua sendo a da seção 7: uma tabela cuja partition key é aquilo que você tem em mãos.

Ou seja: o SAI não substitui a modelagem orientada a consultas, ele **cobre o que ela não previu**. É a segunda das três saídas que a seção 8 anunciou para a consulta sem tabela — e a que você escolhe quando a consulta é rara o bastante para não merecer uma tabela própria, e frequente o bastante para não merecer uma varredura.

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

O fluxo Q1 a Q7 é a sequência de telas de um aplicativo. Até aqui você o executou digitando `cqlsh`. Vamos executá-lo como o aplicativo faz.

### Preparando o ambiente

O driver roda **no host**, não dentro do container: a imagem do Cassandra tem `python3` mas não tem `pip`. E é assim que se parece com a realidade — a aplicação nunca mora no mesmo host do banco.

```sh
python3 -m venv venv

```

```sh
. venv/bin/activate

```

```sh
pip install cassandra-driver

```

> O `venv` vale **só neste terminal**, como os `alias` da seção 1. Se você abrir outro terminal para rodar o `driver_demo.py`, precisa ativá-lo de novo — o `pip install` não se repete, a ativação sim. Quando ele está ativo, o prompt começa com `(venv)`.

A conexão vai para `127.0.0.1:9042`, a porta que o `compose.yaml` publica no host:

```sh
python3 -c "
from cassandra.cluster import Cluster
cluster = Cluster(['127.0.0.1'])
session = cluster.connect('infobarbank')
print('conectado, versão:', session.execute('SELECT release_version FROM system.local').one().release_version)
cluster.shutdown()"

```

```
conectado, versão: 5.0.8
```

### O fluxo aplicacional

Baixe a aplicação:

```sh
wget https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/main/driver_demo.py

```

```sh
python3 driver_demo.py

```

```
Cliente 2b162060 — MARIVALDA KANAMARY — competência 2026-06

Q1 · Dados da conta
  conta 2b162060  ATIVA    apelido MARIVALDA    saldo R$     100,00

Q2 · Cartões de crédito
  007c2c1c  ATIVO    5450 3799 9172 8454  limite R$   1.000,00  disponível R$     900,00
  897199aa  ATIVO    5576 8924 9861 7490  limite R$     200,00  disponível R$      50,00
  9a748c3c  INATIVO  5188 2716 2053 8850  limite R$     500,00  disponível R$     100,00

Q3 · Últimos lançamentos aprovados
  27/06 17:46  2b162060  Posto de gasolina    R$     708,41
  27/06 17:46  897199aa  Salão de beleza      R$     835,99
  25/06 17:46  2b162060  Salão de beleza      R$     936,00
  21/06 17:46  2b162060  Loja de brinquedos   R$     727,70
  19/06 17:46  2b162060  Salão de beleza      R$     654,87

Q4 · Extrato por período (dias 19 a 27)
  27/06 17:46  DEBITO   Posto de gasolina    R$     708,41
  [...]

Q7 · Detalhe do lançamento cc44552e
  27/06/2026 17:46  Posto de gasolina
  R$     708,41  APROVADA
  autenticação b2c5db0d-ec3c-4a13-b116-a44e1ffd8e41
```

Como na seção 8, os valores de Q1 e Q2 devem coincidir com os seus; os lançamentos de Q3 a Q7 são sorteados por ambiente.

Você pode passar outra cliente e outra competência:

```sh
python3 driver_demo.py 2b16242a

```

```sh
python3 driver_demo.py 2b162060 2026-05

```

> Sete das cinquenta clientes têm conta, cartões e lançamentos: `2b162060`, `2b16242a`, `2b16256a`, `2b16353c`, `2b1636ae`, `2b16396a` e `2b163bcc` — as mesmas personas da seção 4. Para as outras, o script avisa que não há lançamentos e encerra.

### Leia o código

Abra o `driver_demo.py`. Três decisões nele merecem atenção.

**1. Prepared statements.** Cada consulta é preparada uma vez e executada com parâmetros:

```python
CONSULTAS = {
    "Q3": """
        SELECT data_hora, id_produto, estabelecimento, valor
        FROM lancamentos_por_status
        WHERE id_cliente = ? AND competencia = ? AND status = 'APROVADA'
        LIMIT 5
    """,
    ...
}

stmt = {nome: session.prepare(cql) for nome, cql in CONSULTAS.items()}
...
session.execute(stmt["Q3"], [id_cliente, competencia])
```

O ganho evidente é que o servidor analisa a consulta uma vez só. O ganho maior é que o driver passa a **conhecer a estrutura da consulta** — inclusive quais parâmetros formam a partition key.

Nunca monte CQL concatenando string. Além da injeção, você perde as duas vantagens acima.

**2. Política de balanceamento declarada.**

```python
perfil = ExecutionProfile(
    load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(local_dc=DATACENTER)),
    consistency_level=ConsistencyLevel.LOCAL_ONE,
    request_timeout=15,
)
cluster = Cluster(CONTACT_POINTS, execution_profiles={EXEC_PROFILE_DEFAULT: perfil})
```

`TokenAwarePolicy` é onde as seções 5 e 10 se encontram. Com um prepared statement, o driver calcula o **token** da partition key ali mesmo, no cliente, e envia a consulta **direto para um nó que tem a réplica** — em vez de escolher um nó qualquer e obrigá-lo a intermediar. É o cálculo de `token(id_cliente)` que você fez na seção 5, agora sendo usado para rotear.

Com um nó isso não muda nada. É a configuração que se leva para produção, e o motivo pelo qual prepared statement é questão de desempenho, não só de segurança.

`DCAwareRoundRobinPolicy(local_dc=...)` mantém o tráfego no datacenter local. `ConsistencyLevel` e o comportamento de cada nível sob falha de réplica pertencem ao laboratório de cluster; aqui ficam declarados no perfil, onde a aplicação de verdade os define.

Se você omitir a política, o driver avisa:

```
Cluster.__init__ called with contact_points specified, but no load_balancing_policy.
In the next major version, this will raise an error; please specify a load-balancing policy.
```

**3. Parâmetro é tipado.**

```python
ano, mes = (int(parte) for parte in competencia.split("-"))
inicio = datetime(ano, mes, 19)
fim = datetime(ano, mes, 28)
```

No `cqlsh`, `data_hora >= '2026-06-19'` funciona: ele converte o literal. No driver, um parâmetro de prepared statement é tipado e verificado **no cliente**, antes de a consulta sair da máquina. Passar a string devolve:

```
TypeError: DateType arguments must be a datetime, date, or timestamp
```

### O erro da seção 8, agora em Python

Repare em como o script descobre a competência:

```python
session.execute("SELECT DISTINCT id_cliente, competencia FROM lancamentos_por_periodo")
```

A tentativa natural seria filtrar pela cliente:

> **Provoque este erro.**

```sh
python3 -c "
from cassandra.cluster import Cluster
session = Cluster(['127.0.0.1']).connect('infobarbank')
session.execute(\"SELECT competencia FROM lancamentos_por_periodo WHERE id_cliente='2b162060'\")"

```

```
cassandra.InvalidRequest: Error from server: code=2200 [Invalid query]
message="Cannot execute this query as it might involve data filtering..."
```

É o primeiro erro de 8.6 — partition key composta pela metade — agora como exceção Python. **O driver não protege de modelagem errada**, e não existe camada de abstração que resolva isso: as regras da seção 8 valem em qualquer linguagem.

O `SELECT DISTINCT` sobre as colunas da partition key é válido porque percorre o índice de partições, não os dados. Mas continua sendo conveniência de laboratório: percorrer todas as partições não escala. Um aplicativo de banco não descobre a competência — ele a recebe do seletor de mês da tela.

### Paginação

Uma consulta que devolve muitas linhas não vem de uma vez. O driver busca por páginas, e a iteração vai pedindo as seguintes conforme você consome:

```sh
python3 -c "
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
session = Cluster(['127.0.0.1']).connect('infobarbank')
stmt = SimpleStatement('SELECT id_lancamento, valor FROM lancamentos_detalhe', fetch_size=100)
resultado = session.execute(stmt)
paginas = 0
linhas = 0
while True:
    paginas += 1
    linhas += len(resultado.current_rows)
    if resultado.has_more_pages:
        resultado.fetch_next_page()
    else:
        break
print(f'{linhas} linhas em {paginas} páginas de 100')"

```

```
1000 linhas em 11 páginas de 100
```

Onze páginas para mil linhas em páginas de cem — a última vem vazia. O Cassandra devolve um *paging state* junto de cada página e não sabe que acabou até tentar buscar a seguinte: ele leu até completar cem linhas, guardou onde parou, e só na décima primeira tentativa descobriu que não havia mais nada. Não é desperdício relevante, mas explica a contagem.

O `fetch_size` padrão do driver é 5000. O que ele protege é a memória do **cliente** e o tempo de resposta do **coordenador**: sem paginação, uma consulta ampla obrigaria o nó a montar o resultado inteiro antes de enviar qualquer coisa.

Isso não torna consulta ampla aceitável. Paginar uma varredura continua sendo uma varredura — a seção 8.7 vale igual. Paginação existe para o caso em que **uma partição legítima** tem muitas linhas.

### Assíncrono

A tela de abertura do aplicativo precisa de Q1 e Q2 ao mesmo tempo. Executá-las em sequência soma as duas latências; disparadas juntas, custa a maior das duas:

```sh
python3 -c "
from cassandra.cluster import Cluster
session = Cluster(['127.0.0.1']).connect('infobarbank')
q1 = session.prepare('SELECT id_conta, saldo_disponivel FROM conta_corrente WHERE id_cliente = ?')
q2 = session.prepare('SELECT id_cartao, limite_disponivel FROM cartao_credito WHERE id_cliente = ?')
futuros = [session.execute_async(q1, ['2b162060']), session.execute_async(q2, ['2b162060'])]
conta, cartoes = [f.result() for f in futuros]
print('conta  :', conta.one().id_conta, conta.one().saldo_disponivel)
print('cartões:', [c.id_cartao for c in cartoes])"

```

```
conta  : 2b162060 100.0
cartões: ['007c2c1c', '897199aa', '9a748c3c']
```

`execute_async` devolve um future imediatamente; `result()` espera. Como cada consulta vai para uma partição diferente — e, em cluster, possivelmente para nós diferentes — o paralelismo é real.

Esse padrão é o que torna viável o modelo da Parte II. Uma tela que precisa de dados de cinco tabelas faz cinco leituras pontuais em paralelo, e isso é mais rápido e mais previsível do que um `JOIN` de cinco tabelas em qualquer banco relacional. **A desnormalização da seção 7 não é um preço que se paga; é o que permite a leitura ser trivial.**

### O que você deve conseguir explicar

- Por que prepared statement é questão de desempenho, e não só de segurança.
- O que `TokenAwarePolicy` faz com o resultado de `token(id_cliente)`.
- Por que uma modelagem errada erra igual em Python e no `cqlsh`.
- A diferença entre paginar uma partição grande e paginar uma varredura.
- Por que cinco leituras pontuais em paralelo podem ganhar de um `JOIN`.

Quando terminar, saia do ambiente virtual:

```sh
deactivate

```

**→ Parte IV.** Você percorreu um modelo completo, das perguntas às tabelas, e o executou de dentro de uma aplicação. Agora é a sua vez — em outra empresa.

## 11. Enunciado

Você acabou de percorrer o modelo de um banco digital, das sete perguntas do fluxo aplicacional até as doze tabelas que as respondem. Agora o exercício inverso: um modelo pronto, feito pelo mesmo método, e a sua tarefa é **reconstruir qual consulta motivou cada tabela** — em outra empresa, sem receber o mapa.

A keyspace `ecommerce` é uma **loja virtual**, já carregada. Ela foi modelada com as mesmas convenções do `infobarbank`: nomes no padrão `entidade_por_critério`, ordenação física por data decrescente, uma tabela dedicada à leitura pontual pelo id — e, acima de tudo, a regra que governa toda partition key deste laboratório: **ela é sempre algo que a tela tem em mãos**.

Repare que a regra não diz "o cliente". Diz *o que a tela tem*. Às vezes é o cliente logado, às vezes é o CPF que o atendente anotou, às vezes é o id que veio da lista anterior. Quando você for justificar cada escolha, é essa a pergunta a fazer primeiro.

A cliente é a mesma pessoa. No banco ela é `2b162060`; na loja, **`CLI-000001`** — mesmo nome, mesmo CPF, id próprio de cada sistema. É por isso que as duas empresas precisam de uma tabela de acesso por CPF.

### Explorando

```sh
cql "DESCRIBE KEYSPACE ecommerce;"

```

```sh
cql "SELECT table_name FROM system_schema.tables WHERE keyspace_name='ecommerce';"

```

```
 table_name
-----------------------------
                     cliente
             cliente_por_cpf
           cliente_por_email
 forma_pagamento_por_cliente
              pedido_detalhe
 pedidos_por_forma_pagamento
         pedidos_por_periodo
         pedidos_por_produto
          pedidos_por_status

(9 rows)
```

Descubra as competências disponíveis — aqui também os dados são relativos à data de execução:

```sh
cql "SELECT DISTINCT id_cliente, competencia FROM ecommerce.pedidos_por_periodo;"

```

Use uma competência **fechada** com bom volume. Nos exemplos deste enunciado aparece `2026-05`; troque pela que existir no seu ambiente.

### As consultas

Escreva, para cada item, a consulta CQL que o responde. Todas as respostas existem: **não é necessário criar nenhuma tabela**.

| | Consulta |
|---|---|
| **Q1'** | Exibir os dados cadastrais da cliente `CLI-000001`. |
| **Q2'** | Dado apenas o CPF `987.539.360-60`, descobrir de quem é a conta. |
| **Q3'** | Exibir as formas de pagamento cadastradas pela cliente, com a situação de cada uma. |
| **Q4'** | Exibir os cinco pedidos **aprovados** mais recentes da cliente na competência escolhida. |
| **Q5'** | Exibir os pedidos da cliente entre os dias 10 e 20 da competência. |
| **Q6'** | Exibir os pedidos de `TABLET` feitos pela cliente na competência. |
| **Q7'** | Exibir os pedidos que a cliente pagou com `PIX` na competência. |
| **Q8'** | Exibir o detalhe completo de um pedido, tendo apenas o `id_pedido`. |
| **Q9'** | *(analítica)* Exibir todas as vendas do estado de `SP` em um dia específico. |
| **Q10'** | *(analítica)* Exibir todas as vendas de `NOTEBOOK` em um dia específico. |

### O que entregar

Para cada consulta:

1. **O comando CQL**, executado e funcionando.
2. **O resultado** que ele devolveu.
3. **Uma linha** dizendo qual tabela você usou e por que ela, e não outra.

O item 3 é o que está sendo avaliado. Duas tabelas diferentes podem devolver o mesmo resultado nesta base pequena; só uma delas responde àquela pergunta com uma leitura pontual em uma partição. A justificativa deve mencionar a partition key e, quando for o caso, a clustering key.

### Critérios

| | |
|---|---|
| A consulta funciona | necessário, não suficiente |
| Informa a partition key completa | nenhuma resposta deve precisar de `ALLOW FILTERING` |
| Escolheu a tabela cuja ordenação física já entrega o resultado pedido | nenhuma resposta deve precisar de `ORDER BY` |
| A justificativa identifica corretamente o padrão de acesso | é o item que separa quem entendeu de quem traduziu |

Dito de outro modo: cada justificativa sua deve percorrer, ao contrário, o caminho da seção 8 — *desta consulta, o que eu tenho em mãos? logo, qual partition key? logo, qual tabela?*

> Se alguma resposta sua precisar de `ALLOW FILTERING` ou de `ORDER BY`, ela está usando a tabela errada. Releia a seção 8.

### Duas perguntas para discutir em sala

Não precisam de código.

1. A loja quer uma tela com **os dez pedidos de maior valor** de uma cliente numa competência. Nenhuma das nove tabelas responde a isso com eficiência. Por quê, e o que precisaria existir?
2. `pedidos_por_produto` particiona por `(id_cliente, produto)` — é a única tabela de pedidos sem bucket. O que aconteceria com ela se a partition key fosse `(id_cliente, produto, competencia)`? Ganha-se o quê, e perde-se qual consulta?

## A. Busca vetorial

A versão 5 trouxe um tipo de dado novo, `vector<float, N>`, e uma forma de consulta que não existia: **buscar por proximidade** em vez de por igualdade.

A ideia: representar cada item por uma lista de números — um **embedding** — em que a posição no espaço carrega significado. Itens parecidos ficam próximos. A consulta então pede "os N mais próximos deste ponto".

Vamos montar um exemplo minúsculo e explícito, com três dimensões inventadas: **portabilidade**, **uso pessoal** e **cozinha**.

```sh
cql "
CREATE TABLE lab.produto_similar (
    produto         text PRIMARY KEY,
    categoria       text,
    caracteristicas vector<float, 3>
);"

```

O índice é SAI, o mesmo da seção 9:

```sh
cql "CREATE INDEX ON lab.produto_similar(caracteristicas) USING 'sai';"

```

```
Warnings :
SAI ANN indexes on vector columns are experimental and are not recommended for production use.
They don't yet support SELECT queries with:
 * Consistency level higher than ONE/LOCAL_ONE.
 * Paging.
 * No LIMIT clauses.
 * PER PARTITION LIMIT clauses.
 * GROUP BY clauses.
 * Aggregation functions.
 * Filters on columns without a SAI index.
```

Leia esse aviso: na 5.0 a busca vetorial é **experimental**, e a lista de restrições é concreta. Duas delas valem destacar — consulta vetorial exige `LIMIT` (a terceira linha diz que consultas *sem* `LIMIT` não são suportadas) e não funciona com consistency level acima de `LOCAL_ONE`, o que a torna inadequada a caso de uso que exija leitura forte. Não é erro: é o Cassandra dizendo em que estágio o recurso está.

```sh
cql "
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('NOTEBOOK',       'informatica',  [0.9, 0.9, 0.0]);
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('TABLET',         'informatica',  [1.0, 0.8, 0.0]);
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('COMPUTADOR',     'informatica',  [0.1, 0.9, 0.0]);
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('CELULAR',        'telefonia',    [1.0, 0.6, 0.1]);
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('GELADEIRA',      'linha branca', [0.0, 0.1, 1.0]);
INSERT INTO lab.produto_similar(produto, categoria, caracteristicas) VALUES ('LIQUIDIFICADOR', 'linha branca', [0.1, 0.1, 0.9]);"

```

Agora a consulta nova. `ANN` é *Approximate Nearest Neighbor* — "os vizinhos mais próximos", aproximadamente:

```sh
cql "
SELECT produto, categoria, similarity_cosine(caracteristicas, [0.9, 0.9, 0.0]) AS similaridade
FROM lab.produto_similar
ORDER BY caracteristicas ANN OF [0.9, 0.9, 0.0]
LIMIT 4;"

```

```
 produto    | categoria   | similaridade
------------+-------------+--------------
   NOTEBOOK | informatica |            1
     TABLET | informatica |     0.996942
    CELULAR |   telefonia |     0.983298
 COMPUTADOR | informatica |     0.890434

(4 rows)
```

Perguntamos "o que é parecido com um notebook?" sem nenhum `WHERE`, e sem que o banco soubesse o que é um notebook. Os dois eletrodomésticos de cozinha nem apareceram entre os quatro primeiros. Faça a pergunta do outro lado do espaço:

```sh
cql "
SELECT produto, categoria, similarity_cosine(caracteristicas, [0.0, 0.1, 1.0]) AS similaridade
FROM lab.produto_similar
ORDER BY caracteristicas ANN OF [0.0, 0.1, 1.0]
LIMIT 3;"

```

```
 produto        | categoria    | similaridade
----------------+--------------+--------------
      GELADEIRA | linha branca |            1
 LIQUIDIFICADOR | linha branca |     0.996949
        CELULAR |    telefonia |     0.568009
```

### Três coisas a observar

**A dimensão faz parte do tipo.** `vector<float, 3>` só aceita vetores de exatamente três posições:

> **Provoque este erro.**

```sh
cql "SELECT produto FROM lab.produto_similar ORDER BY caracteristicas ANN OF [0.9, 0.9] LIMIT 1;"

```

```
InvalidRequest: ... "Invalid vector literal for caracteristicas of type vector<float, 3>..."
```

**A função de similaridade importa, e é uma decisão.** O padrão é cosseno, que compara **direção** e ignora **magnitude**. Foi por isso que escolhemos vetores em que cada dimensão significa algo: com valores arbitrários, um item de valores pequenos pode sair mais "parecido" que um item semanticamente próximo, simplesmente porque aponta na mesma direção. As alternativas são `dot_product` e `euclidean`, declaráveis na criação do índice.

**O "aproximado" do ANN é real.** A busca não garante os vizinhos exatos: ela troca precisão por velocidade, o que é o que torna viável pesquisar entre milhões de vetores. Para seis linhas, o resultado é exato.

### Onde isso se usa

Embeddings de verdade não são inventados à mão: vêm de um modelo que transforma texto, imagem ou áudio em algumas centenas ou milhares de dimensões. O que este apêndice mostra é o lado do banco — como armazenar, indexar e consultar por proximidade.

Vale notar o que **não** mudou: `produto` continua sendo a partition key, e a busca vetorial continua sendo um índice SAI, com a limitação da seção 9 — ela pergunta a todos os nós. Tudo o que você aprendeu na Parte II continua valendo.

E vale repetir o aviso do próprio Cassandra: na 5.0 isso é experimental. Serve para conhecer o mecanismo e para prototipar; não para sustentar um produto.

Limpando:

```sh
cql "DROP TABLE lab.produto_similar;"

```

## B. Encerrando o ambiente

```sh
docker compose down -v

```

O `-v` remove também o volume de dados. Como as duas keyspaces são recriadas em cerca de 30 segundos no próximo `up`, não há motivo para preservá-las.

### Para onde ir depois

Este laboratório trabalha com base pequena, de propósito: doze mil lançamentos cabem numa partição de dois quilobytes, e o que se aprende aqui é a **forma** da modelagem. O que ela custa em escala é outro assunto — partições de 224 MB, `ReadTimeout` porque a partição não caberia na resposta, 18,5 milhões de registros. Isso está no [cassandra-datamodeling-lab](https://github.com/infobarbosa/cassandra-datamodeling-lab).

Cluster de verdade — vários nós, `nodetool repair`, consistency level sob falha — tem laboratório próprio, pelos motivos que a seção 3 explica.

## C. Troubleshooting

Antes de qualquer coisa, rode a verificação — ela costuma responder sozinha:

```sh
curl -sS https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/main/scripts/check.sh | bash

```

### `cql: command not found`

Os `alias` valem só no terminal em que foram definidos. Abriu outro, ou fechou e reabriu? Defina de novo:

```sh
alias cql='docker exec -it cassandra-database cqlsh -e'
alias nt='docker exec -it cassandra-database nodetool'
alias cass='docker exec -it cassandra-database'

```

O mesmo vale para a variável `$DIR` da seção 6 e para o `venv` da seção 10 — tudo o que você define num terminal morre com ele.

### `Error response from daemon: No such container: cassandra-database`

O ambiente não está no ar. No diretório onde você baixou o `compose.yaml`:

```sh
docker compose up -d

```

### `Server is not initialized yet, cannot run nodetool`

O Cassandra ainda está subindo. Espere e repita. Para acompanhar:

```sh
docker logs -f cassandra-database

```

### `ModuleNotFoundError: No module named 'cassandra'`

Duas causas, e vale testar nesta ordem porque a segunda é a que costuma enganar.

**1. O `venv` não está ativo neste terminal.** É o caso mais comum: você instalou o driver, abriu outro terminal para rodar o script, e ali o `venv` não existe. Descubra qual Python está sendo usado:

```sh
which python3

```

Se a resposta **não** terminar em `venv/bin/python3`, é isso. Ative, no diretório onde você criou o `venv`:

```sh
. venv/bin/activate

```

**2. O driver não foi instalado.** Aí é o `pip install` da seção 10:

```sh
pip install cassandra-driver

```

> Se esse comando responder `Requirement already satisfied` e mesmo assim o erro continuar, **volte para a causa 1**: você instalou em um ambiente e está executando em outro. É a única combinação que produz esses dois sintomas juntos, e é onde as pessoas ficam presas reinstalando.

### `NoHostAvailable` ao conectar pelo driver

O driver roda no host e precisa da porta 9042 publicada. Confira:

```sh
docker port cassandra-database

```

```
9042/tcp -> 0.0.0.0:9042
```

Se não aparecer nada, seu `compose.yaml` é a versão antiga, sem a seção `ports`. Baixe de novo.

### `keyspace ecommerce does not exist` (ou `infobarbank`)

Os containers de carga falharam ou ainda estão rodando. Veja o que dizem:

```sh
docker compose logs cassandra-init-infobarbank cassandra-init-ecommerce

```

Se um deles terminou com erro, rode de novo apenas ele:

```sh
docker compose up cassandra-init-ecommerce

```

### `Address already in use` ao subir o ambiente

Outro processo já ocupa a 9042 — provavelmente um Cassandra de outro laboratório. Encontre:

```sh
docker ps --filter publish=9042

```

E pare o container que aparecer, ou remova a seção `ports` do `compose.yaml` (você perde a Parte III).

### Os resultados não batem com o texto

Confira nesta ordem:

1. **Competência.** Os lançamentos e pedidos são gerados em relação à data em que você criou o ambiente. Use `SELECT DISTINCT` para descobrir as suas, e prefira uma competência fechada — a mais recente é o mês corrente.
2. **Cliente.** No `infobarbank`, sete das cinquenta clientes têm conta, cartões e lançamentos: `2b162060`, `2b16242a`, `2b16256a`, `2b16353c`, `2b1636ae`, `2b16396a`, `2b163bcc`.
3. **Valores que sempre variam.** `Host ID`, endereço IP, `Load`, UUID do diretório da tabela, timestamps, e o tamanho do `Data.db` em um ou dois bytes.
4. **Numeração das SSTables.** Se você fez um flush a mais, seus arquivos não serão `nb-1` a `nb-4`. Use os nomes que o `ls` mostrar.

### Recomeçar do zero

```sh
docker compose down -v

```

```sh
docker compose up -d

```

Leva pouco mais de um minuto e não deixa resíduo. Não hesite: nada neste laboratório merece ser preservado.

### O tamanho da tabela em disco não diminui depois do `DELETE`

Não é problema — é a seção 6. Veja `gc_grace_seconds`.
