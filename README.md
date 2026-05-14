# Drone Telemetry Monitor

Sistema de Telemetria IoT para Monitoramento de Drones em Tempo Real.

Projeto 1 — CIC0124 Redes de Computadores, UnB, 2026/1.

## Arquitetura

O sistema usa três canais de comunicação distintos:

- **UDP (porta 9001)**: Streaming de telemetria do drone (GPS, bateria, velocidade). Alta frequência, tolerante a perda.
- **TCP (porta 9002)**: Comandos críticos da base para o drone (LAND, RTH, HOVER). Exige entrega garantida.
- **HTTP (porta 8080)**: Dashboard web para visualização do status em tempo real.

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

## Execução

```bash
# Terminal 1 - Servidor
python -m src.server.main

# Terminal 2 - Drone simulado
python -m src.client.drone_simulator

# Terminal 3 - Dashboard
# Abrir http://localhost:8080 no navegador
```
