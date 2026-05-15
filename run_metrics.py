import logging
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.common.config import SERVER_HOST, UDP_TELEMETRY_PORT, TCP_COMMAND_PORT
from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.client.drone_simulator import DroneSimulator


def main():
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger("metrics")
    logger.setLevel(logging.INFO)

    num_drones = 5
    duration = 10

    logger.info(f"Iniciando benchmark: {num_drones} drones por {duration}s")

    udp = UDPTelemetryServer("127.0.0.1", 0)
    tcp = TCPCommandServer("127.0.0.1", 0)
    udp.start()
    tcp.start()

    drones = []
    for i in range(num_drones):
        d = DroneSimulator(
            drone_id=f"BENCH-{i:02d}",
            udp_host="127.0.0.1", udp_port=udp.port,
            tcp_host="127.0.0.1", tcp_port=tcp.port,
            telemetry_interval=0.5,
        )
        d.start()
        drones.append(d)

    time.sleep(1)

    logger.info(f"Drones conectados: {len(tcp.list_connected_drones())}")
    logger.info(f"Enviando comandos para medir RTT...")

    for i in range(num_drones):
        tcp.send_command(f"BENCH-{i:02d}", "HOVER")

    time.sleep(duration)

    tp = udp.throughput.summary()
    rtt_avg = tcp.rtt.average()
    rtt_all = tcp.rtt.all()

    logger.info("")
    logger.info("=" * 50)
    logger.info("  RESULTADOS DO BENCHMARK")
    logger.info("=" * 50)
    logger.info(f"  Drones ativos:     {len(udp.list_drones())}")
    logger.info(f"  Pacotes UDP:       {tp['packet_count']}")
    logger.info(f"  Bytes totais:      {tp['total_bytes']}")
    logger.info(f"  Throughput:        {tp['bytes_per_second']:.2f} B/s ({tp['bytes_per_second']/1024:.2f} KB/s)")
    logger.info(f"  Duracao:           {tp['elapsed_sec']:.1f}s")
    logger.info(f"  RTT medio:         {rtt_avg*1000:.2f} ms" if rtt_avg else "  RTT medio:         N/A")

    if rtt_all:
        logger.info(f"  RTT min:           {min(rtt_all.values())*1000:.2f} ms")
        logger.info(f"  RTT max:           {max(rtt_all.values())*1000:.2f} ms")

    logger.info("=" * 50)

    for d in drones:
        d.stop()
    udp.stop()
    tcp.stop()


if __name__ == "__main__":
    main()
