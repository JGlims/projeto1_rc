# RESUMO_PROJETO.md - Drone Telemetry Monitor

> Documento tecnico completo do sistema de telemetria IoT para monitoramento de drones em tempo real.
> Disciplina: CIC0124 - Redes de Computadores, UnB, Profa. Priscila Solis.

---

## 1. Visao Geral

### O que e o projeto

O **Drone Telemetry Monitor** e uma plataforma de monitoramento em tempo real de frotas de drones, desenvolvida como projeto pratico da disciplina de Redes de Computadores. O sistema simula um cenario real de telemetria IoT onde multiplos drones enviam dados de voo (posicao GPS, altitude, velocidade, bateria) para uma estacao terrestre central, que persiste, processa e exibe essas informacoes em um dashboard web interativo.

### Qual problema ele resolve no contexto de Redes de Computadores

O projeto demonstra na pratica os conceitos fundamentais da disciplina:

- **Escolha de protocolo de transporte**: o sistema usa **UDP** para dados de telemetria (onde a perda ocasional de um pacote e toleravel e a baixa latencia e prioritaria) e **TCP** para comandos criticos (onde a entrega garantida e essencial). Essa decisao arquitetural ilustra diretamente o trade-off entre confiabilidade e performance nos protocolos da camada de transporte.
- **Protocolo de aplicacao customizado**: sobre TCP e UDP, o sistema define um protocolo de aplicacao proprio baseado em JSON, com tipos de mensagem distintos (telemetria, comando, ACK), campos obrigatorios validados e semantica de request-response para comandos.
- **Modelo cliente-servidor**: a arquitetura segue o modelo classico com drones como clientes e a estacao terrestre como servidor, demonstrando conexoes concorrentes, multiplexacao de sockets e comunicacao bidirecional.
- **Metricas de rede**: o sistema mede e exibe RTT (Round-Trip Time) dos comandos TCP e throughput do canal UDP, permitindo avaliar a performance da comunicacao em tempo real.
- **Camada HTTP**: o dashboard web opera sobre HTTP (porta 8080), adicionando uma terceira camada de protocolo ao sistema e demonstrando a integracao entre protocolos de rede em diferentes camadas.

---

## 2. Arquitetura de Rede e Protocolos

### Visao geral dos canais de comunicacao

O sistema opera sobre tres canais de rede simultaneos:

| Canal | Protocolo | Porta | Direcao | Justificativa |
|---|---|---|---|---|
| Telemetria | UDP | 9001 | Drone -> Servidor | Streaming continuo de dados de voo. Tolerante a perda de pacotes. Prioriza baixa latencia. |
| Comandos | TCP | 9002 | Servidor <-> Drone | Comandos criticos (LAND, HOVER, RTH) exigem entrega garantida e confirmacao (ACK). |
| Dashboard | HTTP | 8080 | Browser <-> Servidor | Interface web para operadores. REST API + paginas HTML servidas pelo Flask. |

### 2.1 Canal UDP - Telemetria (porta 9001)

**Arquivo**: `src/server/udp_telemetry.py` (classe `UDPTelemetryServer`)

**Como funciona**:

1. O servidor cria um socket UDP (`socket.SOCK_DGRAM`) e faz `bind` no endereco `127.0.0.1:9001`.
2. Uma thread daemon executa o loop `_listen()`, chamando `recvfrom(4096)` para receber datagramas.
3. Cada datagrama recebido e decodificado de bytes UTF-8 para string e parseado como JSON pelo modulo `protocol.py`.
4. O pacote validado e armazenado em um dicionario thread-safe (`self._telemetry`), indexado por `drone_id`, mantendo o historico completo de cada drone.
5. Cada pacote recebido tambem e contabilizado pelo `ThroughputTracker` (bytes e contagem de pacotes) para calculo de metricas de rede.

**Por que UDP?** A telemetria e enviada a cada 1 segundo por drone. Se um pacote se perde, o proximo chegara em 1s com dados mais recentes. Nao faz sentido retransmitir dados antigos — a informacao mais recente e sempre mais valiosa. O UDP elimina o overhead do three-way handshake do TCP e da retransmissao, resultando em menor latencia e menor uso de banda.

**Detalhes de implementacao**:
- Socket com timeout de 0.5s para permitir verificacao do flag `self.running` e shutdown gracioso.
- `SO_REUSEADDR` habilitado para reuso imediato da porta apos reinicio.
- Buffer de 4096 bytes por pacote (`BUFFER_SIZE` em `config.py`).
- Logs com timestamp ISO 8601 UTC em cada recepcao.

**No lado do drone** (`src/client/drone_simulator.py`):
- O simulador cria um socket UDP e envia datagramas com `sendto()` para `(host, 9001)`.
- O envio ocorre em um loop com `time.sleep(TELEMETRY_INTERVAL_SEC)` (padrao: 1s).
- Nao ha conexao estabelecida — e puramente fire-and-forget, caracteristica fundamental do UDP.

### 2.2 Canal TCP - Comandos (porta 9002)

**Arquivo**: `src/server/tcp_command.py` (classe `TCPCommandServer`)

**Como funciona — Handshake e Registro**:

1. O servidor cria um socket TCP (`socket.SOCK_STREAM`), faz `bind` e chama `listen(5)` para aceitar ate 5 conexoes pendentes.
2. Uma thread daemon executa `_accept_loop()`, aceitando novas conexoes com `accept()`.
3. Para cada conexao aceita, uma nova thread daemon e criada para lidar com aquele drone (`_handle_drone()`).
4. **Registro**: a primeira mensagem que o drone envia apos conectar e um JSON de registro: `{"drone_id": "DRONE-01"}`. O servidor associa o socket ao `drone_id` em um dicionario thread-safe.
5. Apos o registro, toda mensagem subsequente do drone e tratada como um ACK de comando.

**Fluxo de envio de comando (Servidor -> Drone -> ACK)**:

1. O operador envia um comando via dashboard HTTP (ex: POST `/api/drones/DRONE-01/command` com `{"type": "LAND"}`).
2. O `TCPCommandServer.send_command()` constroi o pacote JSON do comando, registra o timestamp de inicio no `RTTTracker`, e envia pelo socket TCP da conexao ativa do drone, seguido de `\n`.
3. O drone recebe o comando no `_command_loop()`, faz o parse, executa a acao (ex: alterar status para "landed"), constroi um pacote ACK (`{"cmd_id": "...", "status": "ACK", "ts": ...}`) e envia de volta pelo mesmo socket TCP.
4. O servidor recebe o ACK, chama `rtt.finish(cmd_id)` para calcular o RTT, e armazena o resultado.

**Por que TCP?** Comandos como LAND sao criticos para a seguranca do voo. A perda de um comando de pouso poderia resultar em colisao. O TCP garante entrega ordenada e sem perda atraves do three-way handshake, controle de fluxo e retransmissao automatica.

**Protocolo de framing**: mensagens TCP sao delimitadas por `\n` (newline). O servidor acumula bytes em um buffer e processa linha por linha (`while b"\n" in buf`), tratando o problema de message boundary que nao existe no UDP (onde cada `recvfrom` retorna exatamente um datagrama).

### 2.3 Canal HTTP - Dashboard (porta 8080)

**Arquivo**: `src/server/http_dashboard.py` (funcao `create_app()`)

O dashboard HTTP e construido com **Flask** e expoe tanto paginas HTML quanto uma API REST:

**Rotas de pagina**:
| Rota | Metodo | Descricao |
|---|---|---|
| `/` | GET | Pagina principal (login + dashboard) |
| `/register` | GET | Pagina de registro dedicada |

**Rotas de API REST**:
| Rota | Metodo | Auth | Descricao |
|---|---|---|---|
| `/api/auth/register` | POST | Nao | Criar novo usuario |
| `/api/auth/login` | POST | Nao | Autenticar e receber token |
| `/api/drones` | GET | Nao | Listar todos os drones conhecidos |
| `/api/drones/<id>` | GET | Nao | Ultimo dado de telemetria do drone |
| `/api/drones/<id>/telemetry` | GET | Nao | Historico de telemetria (com `?limit=N`) |
| `/api/drones/<id>/command` | POST | Sim (Bearer) | Enviar comando ao drone |
| `/api/alerts` | GET | Nao | Listar alertas do sistema |
| `/api/metrics` | GET | Nao | Metricas de rede (RTT e throughput) |

**Autenticacao**: usa Bearer Token. O endpoint de comando requer autenticacao via header `Authorization: Bearer <token>`. O decorator `require_auth` valida o token contra o banco de dados.

---

## 3. O Protocolo de Aplicacao

### Formato das mensagens

Todas as mensagens do protocolo de aplicacao sao **JSON puro codificado em UTF-8**. Nao ha headers binarios, comprimento prefixado ou framing customizado alem do delimitador `\n` no TCP.

### 3.1 Mensagem de Telemetria (UDP: Drone -> Servidor)

```json
{
    "drone_id": "DRONE-01",
    "ts": 1716000000.123,
    "lat": -15.7631,
    "lon": -47.8729,
    "alt": 120.5,
    "speed": 12.3,
    "battery": 87.2,
    "status": "flying"
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `drone_id` | string | Identificador unico do drone (ex: "DRONE-01") |
| `ts` | float | Timestamp UNIX de quando o dado foi gerado (via `time.time()`) |
| `lat` | float | Latitude GPS (graus decimais) |
| `lon` | float | Longitude GPS (graus decimais) |
| `alt` | float | Altitude em metros |
| `speed` | float | Velocidade em metros por segundo |
| `battery` | float | Nivel de bateria em percentual (0.0 a 100.0) |
| `status` | string | Estado do drone: `"flying"`, `"hovering"`, `"landed"`, `"returning"` |

**Empacotamento**: `protocol.build_telemetry_packet()` monta o dicionario Python e serializa com `json.dumps()`. O resultado e uma string JSON que e codificada para bytes com `.encode("utf-8")` antes de enviar pelo socket UDP via `sendto()`.

**Validacao**: `protocol.parse_telemetry_packet()` faz `json.loads()` do raw bytes/string e verifica se todos os 8 campos obrigatorios (`TELEMETRY_FIELDS`) estao presentes. Se faltar algum campo ou o JSON for invalido, levanta `ValueError`.

### 3.2 Mensagem de Comando (TCP: Servidor -> Drone)

```json
{
    "cmd_id": "a1b2c3d4",
    "type": "LAND",
    "params": {},
    "ts": 1716000001.456
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `cmd_id` | string | ID unico gerado com `uuid.uuid4().hex[:8]` (8 caracteres hex) |
| `type` | string | Tipo do comando: `"LAND"`, `"HOVER"`, `"RTH"` |
| `params` | object | Parametros adicionais (atualmente vazio `{}`) |
| `ts` | float | Timestamp UNIX de criacao do comando |

**Comandos suportados**:
- **LAND**: o drone pousa imediatamente (altitude = 0, velocidade = 0, status = "landed")
- **HOVER**: o drone permanece estacionario (velocidade = 0, status = "hovering")
- **RTH** (Return to Home): o drone retorna as coordenadas base (lat=-15.7631, lon=-47.8729, status = "returning")

**Framing TCP**: o pacote JSON e seguido de `\n` para delimitar mensagens no stream TCP. Isso e necessario porque o TCP e orientado a stream (nao a mensagens) — sem o delimitador, nao haveria como saber onde uma mensagem termina e a proxima comeca.

### 3.3 Mensagem de ACK (TCP: Drone -> Servidor)

```json
{
    "cmd_id": "a1b2c3d4",
    "status": "ACK",
    "ts": 1716000001.789
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `cmd_id` | string | Mesmo `cmd_id` do comando recebido (correlacao) |
| `status` | string | Status da confirmacao (sempre `"ACK"`) |
| `ts` | float | Timestamp UNIX de quando o ACK foi gerado |

**Fluxo completo**: Servidor envia Comando -> Drone recebe, executa, envia ACK -> Servidor recebe ACK e calcula RTT (`finish_time - start_time`).

### 3.4 Mensagem de Registro (TCP: Drone -> Servidor)

```json
{"drone_id": "DRONE-01"}
```

A primeira mensagem de um drone apos estabelecer a conexao TCP. O servidor usa isso para mapear o socket ao identificador do drone.

### Como os dados trafegam na rede

```
DRONE (Cliente)                              SERVIDOR (Ground Station)
     |                                              |
     |--- [UDP 9001] Telemetria JSON ------------->|  recvfrom() -> parse -> armazena
     |    (fire-and-forget, sem resposta)           |
     |                                              |
     |<-- [TCP 9002] Registro {"drone_id":...}\n -->|  accept() -> _handle_drone()
     |                                              |
     |<-- [TCP 9002] Comando JSON\n ----------------|  send_command() -> sendall()
     |--- [TCP 9002] ACK JSON\n ------------------->|  recv() -> parse_ack -> RTT
     |                                              |
     |                    OPERADOR (Browser)        |
     |                         |                    |
     |                         |<-- [HTTP 8080] --->|  Flask REST API + HTML
```

---

## 4. Estrutura do Projeto

```
projeto1_rc/
|
|-- RESUMO_PROJETO.md           # Este documento
|-- README.md                   # Descricao basica do projeto
|-- requirements.txt            # Dependencias: flask>=3.0, pytest>=8.0
|-- pytest.ini                  # Configuracao do pytest (testpaths = tests)
|-- run_demo.py                 # Script all-in-one: servidores + 3 drones simulados
|-- run_metrics.py              # Benchmark automatizado: 5 drones, mede RTT e throughput
|
|-- src/
|   |-- __init__.py
|   |
|   |-- common/                 # Modulos compartilhados entre cliente e servidor
|   |   |-- __init__.py
|   |   |-- config.py           # Constantes: portas, host, buffer size, intervalo
|   |   |-- protocol.py         # Serializacao/desserializacao do protocolo JSON
|   |   |-- metrics.py          # RTTTracker e ThroughputTracker (thread-safe)
|   |
|   |-- server/                 # Estacao terrestre (Ground Station)
|   |   |-- __init__.py
|   |   |-- main.py             # Classe GroundStation: orquestra todos os servicos
|   |   |-- udp_telemetry.py    # Servidor UDP para receber telemetria
|   |   |-- tcp_command.py      # Servidor TCP para enviar comandos e receber ACKs
|   |   |-- http_dashboard.py   # App Flask com rotas REST e paginas HTML
|   |   |-- storage.py          # Camada de persistencia SQLite (telemetria, comandos, alertas)
|   |   |-- auth.py             # Autenticacao: registro, login, tokens Bearer
|   |
|   |-- client/                 # Simulador do drone
|   |   |-- __init__.py
|   |   |-- drone_simulator.py  # Classe DroneSimulator: envia telemetria UDP, recebe comandos TCP
|   |
|   |-- dashboard/              # Frontend web
|       |-- templates/
|           |-- index.html      # Pagina principal: login split-screen + dashboard com cards
|           |-- register.html   # Pagina de registro dedicada
|
|-- tests/                      # Suite de testes (104 testes)
    |-- __init__.py
    |-- test_protocol.py        # 14 testes: serializacao/validacao do protocolo
    |-- test_udp_telemetry.py   #  9 testes: servidor UDP
    |-- test_tcp_command.py     #  8 testes: servidor TCP + comandos
    |-- test_storage.py         # 10 testes: persistencia SQLite
    |-- test_http_dashboard.py  # 16 testes: dashboard Flask + API REST
    |-- test_auth.py            # 13 testes: autenticacao e autorizacao
    |-- test_drone_simulator.py #  6 testes: simulador do drone
    |-- test_error_handling.py  #  8 testes: resiliencia a pacotes invalidos
    |-- test_integration.py     #  5 testes: fluxo completo end-to-end
    |-- test_metrics.py         # 10 testes: RTTTracker e ThroughputTracker
    |-- test_scalability.py     #  5 testes: carga com 10 drones simultaneos
```

### Banco de dados SQLite

O arquivo `drone_telemetry.db` (ou `demo_telemetry.db` no modo demo) contem tres tabelas:

| Tabela | Campos principais | Proposito |
|---|---|---|
| `telemetry` | drone_id, ts, lat, lon, alt, speed, battery, status, received_at | Historico de todos os dados de telemetria recebidos |
| `commands` | cmd_id, drone_id, cmd_type, params, ack_status, created_at | Registro de todos os comandos enviados e seus ACKs |
| `alerts` | drone_id, alert_type, message, created_at | Alertas gerados (ex: bateria baixa < 20%) |
| `users` | username, password_hash, salt | Usuarios registrados (autenticacao) |
| `tokens` | token, username | Tokens de sessao ativos |

---

## 5. Funcionalidades Implementadas

### 5.1 Comunicacao de Rede

- **Servidor UDP** para recepcao de telemetria em tempo real (fire-and-forget)
- **Servidor TCP** para envio de comandos criticos com confirmacao ACK
- **API REST HTTP** via Flask para integracao com o dashboard web
- **Protocolo de aplicacao JSON** customizado com validacao de campos obrigatorios
- **Framing TCP com delimitador `\n`** para resolver o problema de message boundaries
- **Registro de drones via TCP** (primeira mensagem da conexao)
- **Comunicacao bidirecional TCP**: servidor envia comandos, drone responde ACKs

### 5.2 Metricas de Rede

- **RTT (Round-Trip Time)**: medido para cada comando TCP enviado. O `RTTTracker` registra o instante de envio e o instante de recepcao do ACK, calculando a diferenca. Disponivel por comando individual e como media.
- **Throughput UDP**: o `ThroughputTracker` contabiliza bytes totais recebidos e pacotes, calculando bytes/segundo em tempo real.
- **Tamanho de pacote (Pkt Size)**: calculado no frontend para cada drone, mostrando o tamanho em bytes do payload JSON de telemetria.
- **Painel de metricas globais**: exibe RTT medio, throughput total, contagem de pacotes e bytes totais no dashboard.
- **Metricas por drone**: cada card de drone exibe protocolo (UDP/TCP), RTT, throughput proporcional e tamanho de pacote.

### 5.3 Dashboard Web (Frontend)

- **Tela de login split-screen**: lado esquerdo com animacao de globo 3D rotativo (D3.js + TopoJSON) e drones orbitando em SVG animado; lado direito com formulario de login em fundo escuro.
- **Abas Login/Registro**: troca fluida entre formularios de login e criacao de conta na mesma tela.
- **Pagina de registro dedicada** (`/register`): alternativa acessivel para criacao de conta.
- **Dashboard com cards de drone**: grid responsivo (1/2/3 colunas) com cards glassmorphism exibindo dados de telemetria em tempo real.
- **Atualizacao em tempo real**: polling a cada 2s para telemetria e 3s para metricas, com **atualizacao incremental dos cards** (sem reconstruir o DOM inteiro — evita flickering).
- **Barra de bateria visual**: indicador colorido (verde > 30%, amarelo 15-30%, vermelho < 15%) com animacao suave.
- **Indicador de status com animacao pulsante**: dot colorido que pisca de acordo com o status do drone (verde=flying, amarelo=hovering, cinza=landed).
- **Botoes de comando**: LAND (vermelho), HOVER (amarelo), RTH (azul) — enviam comandos TCP via API REST.
- **Dark Mode / Light Mode**: toggle manual com persistencia em `localStorage`. O tema padrao e light mode. O dark mode usa classes Tailwind CSS (`dark:`).
- **Globo 3D animado**: projecao ortografica D3.js com rotacao continua, graticulas, continentes e animacao de drones orbitantes em SVG.
- **Design glassmorphism**: cards com `backdrop-filter: blur(24px)`, bordas semi-transparentes e sombras sutis.
- **Tipografia premium**: fonte Inter (sans-serif) para UI e Instrument Serif para titulos.
- **Dot grid background**: padrao de pontos sutil no fundo para textura visual.
- **Animacoes de entrada**: fade-up escalonado nos elementos da tela de login.
- **Painel de alertas**: alertas de bateria baixa exibidos como banners com icone de atencao.

### 5.4 Autenticacao e Seguranca

- **Registro de usuarios**: username + senha com hash SHA-256 + salt aleatorio de 32 caracteres hex.
- **Autenticacao via token**: login gera token de 64 caracteres hex aleatorio, armazenado no banco.
- **Protecao de endpoints**: o envio de comandos exige Bearer Token no header Authorization.
- **Validacao de formulario**: senha minima de 4 caracteres, confirmacao de senha, feedback visual de erros.

### 5.5 Simulacao de Drones

- **Simulador realista**: cada drone tem posicao GPS (proximo a Brasilia: -15.76, -47.87), altitude, velocidade e bateria com variacao aleatoria.
- **Suporte multi-drone**: `run_demo.py` inicia 3 drones simultaneos; `run_metrics.py` usa 5 drones.
- **Deplecao de bateria**: bateria diminui gradualmente (0.05% a 0.2% por ciclo).
- **Execucao de comandos**: o simulador responde a LAND (pousa), HOVER (estaciona) e RTH (retorna a base), alterando seu estado interno.
- **Argumentos de linha de comando**: `--drone-id` e `--server` para execucao individual.

### 5.6 Persistencia e Alertas

- **SQLite thread-safe**: todas as operacoes de banco usam `threading.Lock()` e `check_same_thread=False`.
- **Persistencia automatica**: loop em thread daemon salva a telemetria mais recente de cada drone a cada 0.5s.
- **Alerta de bateria baixa**: quando a bateria cai abaixo de 20%, um alerta e gerado no banco com cooldown de 30s para evitar spam.
- **Historico completo**: telemetria, comandos e alertas sao persistidos com timestamps.

### 5.7 Suite de Testes (TDD)

- **104 testes** distribuidos em 11 arquivos.
- **Testes unitarios**: protocol.py (14 testes), metrics.py (10 testes), storage.py (10 testes).
- **Testes de componente**: UDP server (9), TCP server (8), HTTP dashboard (16), auth (13), drone simulator (6).
- **Testes de resiliencia**: error handling (8) — pacotes malformados, desconexoes abruptas, JSON invalido.
- **Testes de integracao**: end-to-end (5) — fluxo completo de telemetria ate o dashboard HTTP.
- **Testes de escalabilidade**: carga com 10 drones (5) — registros simultaneos, throughput, RTT sob carga.
- **Zero mocking**: a suite usa sockets reais, bancos de dados temporarios e fake servers customizados ao inves de mocks.

### 5.8 Benchmarking

- **Script `run_metrics.py`**: executa 5 drones por 10 segundos, envia comandos HOVER para todos e mede:
  - Throughput UDP (bytes/segundo e KB/s)
  - RTT medio, minimo e maximo dos comandos TCP
  - Total de pacotes e bytes trafegados
  - Performance validada com RTT sub-milissegundo em localhost

---

## 6. Como Executar

### Pre-requisitos

- Python 3.10+ instalado
- pip (gerenciador de pacotes Python)

### 6.1 Instalar dependencias

```bash
cd projeto1_rc
pip install -r requirements.txt
```

O `requirements.txt` contem apenas duas dependencias:
- `flask>=3.0` — framework web para o dashboard HTTP
- `pytest>=8.0` — framework de testes

### 6.2 Rodar os testes

```bash
cd projeto1_rc
python -m pytest
```

Para mais detalhes nos resultados:

```bash
python -m pytest -v
```

Resultado esperado: **104 testes passando** (pode variar levemente com ajustes), cobrindo protocolo, UDP, TCP, HTTP, autenticacao, simulador, tratamento de erros, integracao e escalabilidade.

### 6.3 Rodar o sistema completo (Demo)

```bash
cd projeto1_rc
python run_demo.py
```

**O que acontece**:
1. Remove o banco `demo_telemetry.db` anterior (se existir).
2. Inicia o servidor UDP na porta 9001.
3. Inicia o servidor TCP na porta 9002.
4. Registra um usuario padrao: `admin` / `admin`.
5. Inicia 3 drones simulados (DRONE-01, DRONE-02, DRONE-03).
6. Inicia o servidor HTTP Flask na porta 8080.
7. Imprime no terminal as informacoes de conexao.

**Para acessar o dashboard**:
1. Abra o navegador em `http://127.0.0.1:8080`.
2. Faca login com usuario `admin` e senha `admin`.
3. Os 3 drones aparecerao automaticamente com dados atualizando em tempo real.
4. Use os botoes LAND, HOVER e RTH nos cards para enviar comandos.
5. O painel de metricas de rede aparecera na parte inferior.

**Para encerrar**: pressione `Ctrl+C` no terminal.

### 6.4 Rodar o benchmark de metricas

```bash
cd projeto1_rc
python run_metrics.py
```

**O que acontece**:
1. Inicia servidores UDP e TCP em portas efemeras (porta 0 = porta aleatoria do SO).
2. Cria 5 drones simulados com intervalo de telemetria de 0.5s.
3. Envia um comando HOVER para cada drone.
4. Executa por 10 segundos coletando dados.
5. Imprime relatorio:
   - Drones ativos
   - Total de pacotes UDP
   - Bytes totais trafegados
   - Throughput em B/s e KB/s
   - RTT medio, minimo e maximo em milissegundos

### 6.5 Rodar um drone individual

```bash
cd projeto1_rc
python -m src.client.drone_simulator --drone-id DRONE-99 --server 127.0.0.1
```

Requer que os servidores UDP e TCP estejam rodando (via `run_demo.py` ou `main.py`).

### 6.6 Rodar apenas os servidores (sem drones simulados)

```bash
cd projeto1_rc
python -m src.server.main
```

Inicia a Ground Station completa (UDP + TCP + HTTP) e aguarda conexoes de drones reais ou simulados.

---

*Documento gerado em 25/05/2026 para a disciplina CIC0124 - Redes de Computadores, UnB.*
