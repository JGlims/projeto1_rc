# Drone Telemetry Monitor

Sistema de Telemetria IoT para Monitoramento de Drones em Tempo Real.

Projeto 1 — CIC0124 Redes de Computadores, UnB, 2026/1.

## Arquitetura

```
  Drone Simulator (Client)              Ground Station (Server)
       |                                    |         |
       |--- UDP:9001 (telemetria) --------->|         |
       |    JSON a cada 1s                  |         |
       |                                    |         |
       |<-- TCP:9002 (comandos) ------------|         |
       |--- TCP:9002 (ACK) --------------->|         |
       |                                    |         |
                                   Browser -|---------|
                                   HTTP:8080 (dashboard + API REST)
```

| Canal | Protocolo | Porta | Direção | Uso |
|-------|-----------|-------|---------|-----|
| Telemetria | UDP | 9001 | Drone -> Servidor | GPS, bateria, velocidade, altitude, status |
| Comandos | TCP | 9002 | Servidor -> Drone | LAND, HOVER, RTH + ACK |
| Dashboard | HTTP | 8080 | Browser <-> Servidor | Visualização + envio de comandos |

## Protocolo de Aplicacao

### Telemetria (UDP, Drone -> Servidor)

Pacotes JSON enviados via UDP a cada 1 segundo. Tolerante a perda.

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

Campos obrigatorios: `drone_id`, `ts`, `lat`, `lon`, `alt`, `speed`, `battery`, `status`.

Valores de `status`: `flying`, `hovering`, `landed`, `returning`, `idle`.

### Registro TCP (Drone -> Servidor)

Ao conectar via TCP, o drone envia uma mensagem de registro terminada por `\n`:

```json
{"drone_id": "DRONE-01"}
```

### Comando (TCP, Servidor -> Drone)

Enviado pelo servidor quando o operador clica no dashboard. Terminado por `\n`.

```json
{
  "cmd_id": "a1b2c3d4",
  "type": "LAND",
  "params": {},
  "ts": 1716000001.456
}
```

Tipos de comando: `LAND` (pouso), `HOVER` (parar no ar), `RTH` (retornar a base), `MOVE` (ir para coordenada).

### ACK (TCP, Drone -> Servidor)

Confirmacao de recebimento do comando. Terminado por `\n`.

```json
{
  "cmd_id": "a1b2c3d4",
  "status": "ACK",
  "ts": 1716000001.789
}
```

### API REST (HTTP)

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | `/api/auth/register` | Cadastro de usuario |
| POST | `/api/auth/login` | Login, retorna token |
| GET | `/api/drones` | Lista drones conhecidos |
| GET | `/api/drones/<id>` | Ultima telemetria do drone |
| GET | `/api/drones/<id>/telemetry` | Historico de telemetria |
| POST | `/api/drones/<id>/command` | Envia comando (requer token) |
| GET | `/api/alerts` | Lista alertas |
| GET | `/api/metrics` | RTT medio e throughput UDP |

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

## Testes

```bash
pytest
```

105 testes cobrindo: protocolo, UDP, TCP, HTTP, auth, storage, integracao, erros, escalabilidade.

## Execucao

```bash
# Terminal 1 - Servidor (inicia UDP + TCP + HTTP)
python -m src.server.main

# Terminal 2 - Drone simulado
python -m src.client.drone_simulator

# Terminal 3 (opcional) - Segundo drone
python -m src.client.drone_simulator --drone-id DRONE-02
```

Abrir http://localhost:8080 no navegador para o dashboard.

Primeiro acesso: clicar em "Criar conta", depois fazer login.

## Demonstracao com Wireshark

### Filtros uteis

| Filtro | O que captura |
|--------|---------------|
| `udp.port == 9001` | Telemetria do drone |
| `tcp.port == 9002` | Comandos e ACKs |
| `tcp.port == 8080` | Requisicoes HTTP do dashboard |
| `tcp.flags.syn == 1` | Handshakes TCP (SYN) |
| `tcp.analysis.retransmission` | Retransmissoes TCP |

### Roteiro de captura

1. Iniciar captura no Wireshark (interface loopback/localhost)
2. Executar o servidor: `python -m src.server.main`
3. Executar o drone: `python -m src.client.drone_simulator`
4. Aguardar ~10 segundos (10 pacotes UDP de telemetria)
5. No dashboard, enviar um comando LAND (gera trafego TCP)
6. Parar a captura

### O que observar

- **UDP 9001**: pacotes de ~180 bytes a cada 1s, sem handshake, sem retransmissao
- **TCP 9002**: handshake SYN/SYN-ACK/ACK na conexao do drone, depois comando + ACK
- **HTTP 8080**: GET /api/drones a cada 2s (auto-refresh do dashboard)
- **RTT**: tempo entre o pacote TCP do comando e o pacote TCP do ACK
- **Tamanho**: comparar tamanho dos pacotes UDP (telemetria) vs TCP (comando)
- **Encapsulamento**: Ethernet > IP > TCP/UDP > dados JSON da aplicacao
