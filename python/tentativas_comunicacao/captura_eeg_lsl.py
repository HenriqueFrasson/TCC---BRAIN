import serial
import time
import re
import threading
import queue

from pylsl import StreamInfo, StreamOutlet

# ---------------- Configuração LSL ----------------
LSL_NOME = "NeuroSkyEEG"          # nome do stream — é assim que o OpenViBE vai enxergar ele
LSL_TIPO = "EEG"
NUM_CANAIS = 1
TAXA_ALVO_HZ = 512                # mesma taxa que você já vinha usando
LSL_SOURCE_ID = "neurosky_eeg_bridge_001"  # id único, ajuda o LSL a lidar com reconexões

# ---------------- Configuração da serial (capacete EEG) ----------------
PORTA_SERIAL = "COM5"
BAUDRATE = 57600
COMANDO_LEITURA = bytes.fromhex("7200000000000000")

FILTRAR_SATURACAO = True          # True = descarta -2048/2047 | False = manda tudo, cru mesmo
SATURACAO_NEGATIVA = -2048
SATURACAO_POSITIVA = 2047
LIMITE_PLAUSIVEL = 3000

PADRAO_EEG = re.compile(rb'\xaa\xaa\x04\x80\x02(..)', re.DOTALL)
INTERVALO_ALVO = 1.0 / TAXA_ALVO_HZ

fila_amostras = queue.Queue()
parar = threading.Event()


def conectar_serial(porta, baud):
    tentativa = 1
    while True:
        try:
            s = serial.Serial(porta, baudrate=baud, timeout=2)
            s.reset_input_buffer()
            s.reset_output_buffer()
            print("Conectado ao capacete!")
            return s
        except serial.SerialException as e:
            print(f"Tentativa {tentativa} falhou: {e}")
            tentativa += 1
            time.sleep(1)


def criar_stream_lsl():
    info = StreamInfo(
        name=LSL_NOME,
        type=LSL_TIPO,
        channel_count=NUM_CANAIS,
        nominal_srate=TAXA_ALVO_HZ,
        channel_format='float32',
        source_id=LSL_SOURCE_ID,
    )

    canais = info.desc().append_child("channels")
    canal = canais.append_child("channel")
    canal.append_child_value("label", "EEG1")
    canal.append_child_value("unit", "raw")
    canal.append_child_value("type", "EEG")

    outlet = StreamOutlet(info)
    print(f"Stream LSL '{LSL_NOME}' criado e anunciado na rede.")
    print("Não precisa esperar o OpenViBE conectar — pode ir configurando ele com calma.")
    return outlet


def thread_leitura_serial(ser):
    """Só lê a serial e empilha valores na fila."""
    consecutivos_vazios = 0

    while not parar.is_set():
        try:
            ser.write(COMANDO_LEITURA)
            time.sleep(0.01)
            b = ser.read_all()
        except serial.SerialException as e:
            print(f"Erro na leitura serial (Bluetooth caiu?): {e}")
            time.sleep(1)
            continue

        matches = PADRAO_EEG.findall(b) if b else []

        if matches:
            consecutivos_vazios = 0
            for m in matches:
                bruto = int.from_bytes(m, byteorder='big', signed=False)
                v = bruto - 65536 if bruto >= 32768 else bruto

                if abs(v) > LIMITE_PLAUSIVEL:
                    continue  # lixo de verdade, descarta sempre

                if FILTRAR_SATURACAO and v in (SATURACAO_NEGATIVA, SATURACAO_POSITIVA):
                    continue  # saturação do ADC, descarta só se a opção estiver ligada

                fila_amostras.put(v)
        else:
            consecutivos_vazios += 1
            if consecutivos_vazios == 5:
                print(f"[AVISO] {consecutivos_vazios} leituras seguidas sem dado novo")


def thread_envio_lsl(outlet):
    """Tira valores da fila e manda pro LSL, num ritmo constante."""
    contador_amostras = 0
    inicio = time.time()
    proximo_envio = time.time()

    while not parar.is_set():
        try:
            v = fila_amostras.get(timeout=1)
        except queue.Empty:
            continue

        outlet.push_sample([float(v)])
        contador_amostras += 1

        proximo_envio += INTERVALO_ALVO
        atraso = proximo_envio - time.time()
        if atraso > 0:
            time.sleep(atraso)
        else:
            proximo_envio = time.time()  # já atrasado, não tenta compensar tudo de uma vez

        if time.time() - inicio >= 1:
            print(f"Amostras/segundo reais: {contador_amostras}")
            contador_amostras = 0
            inicio = time.time()


def main():
    ser = conectar_serial(PORTA_SERIAL, BAUDRATE)
    time.sleep(1)

    outlet = criar_stream_lsl()

    print("Fim da inicialização")
    print("Transmitindo via LSL... (Ctrl+C para encerrar)")

    t_serial = threading.Thread(target=thread_leitura_serial, args=(ser,), daemon=True)
    t_lsl = threading.Thread(target=thread_envio_lsl, args=(outlet,), daemon=True)
    t_serial.start()
    t_lsl.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando...")
        parar.set()
        time.sleep(0.3)

    finally:
        ser.close()
        print("Conexão serial fechada.")


if __name__ == "__main__":
    main()

