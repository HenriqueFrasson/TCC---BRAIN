import serial
import time
import socket
import struct
import re


# ---------------- Configuração TCP para o OpenViBE ----------------
TCP_HOST = "127.0.0.1"
TCP_PORT = 1337          # precisa ser > 1024 (exigência do OpenViBE)
NUM_CANAIS = 1            # ajuste conforme a quantidade de canais que você extrai


# ---------------- Configuração da serial (capacete EEG) ----------------
PORTA_SERIAL = "COM5"
BAUDRATE = 57600
COMANDO_LEITURA = bytes.fromhex("7200000000000000")


LIMITE_PLAUSIVEL = 3000


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




def aguardar_openvibe(host, port):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((host, port))
    servidor.listen(1)
    print(f"Aguardando conexão do OpenViBE em {host}:{port} ...")
    conn, addr = servidor.accept()
    print(f"OpenViBE conectado: {addr}")
    return servidor, conn




def main():
    servidor, conn = aguardar_openvibe(TCP_HOST, TCP_PORT)
    ser = conectar_serial(PORTA_SERIAL, BAUDRATE)
    time.sleep(1)


    print("Fim da inicialização")
    print("Enviando dados para o OpenViBE... (Ctrl+C para encerrar)")


    contador_amostras = 0
    inicio = time.time()


    try:
        while True:
            try:
                ser.write(COMANDO_LEITURA)
                time.sleep(0.01)
                b = ser.read_all()
            except serial.SerialException as e:
                print(f"Erro na leitura serial (Bluetooth caiu?): {e}")
                time.sleep(1)
                continue  # pula essa iteração e tenta de novo


            dados = b.hex()
            eeg = re.findall(r'aaaa048002([0-9a-fA-F]{4})', dados)


            valor = []  # sempre existe, mesmo se não chegar nada nessa iteração


            if len(b) > 0 and eeg:
                valor = [int(x, 16) for x in eeg]
                valor = [v - 65536 if v >= 32768 else v for v in valor]
                valor = [v for v in valor if abs(v) <= LIMITE_PLAUSIVEL]  # descarta lixo


                for v in valor:
                    try:
                        pacote = struct.pack('<f', float(v))  # float32 little-endian
                        conn.sendall(pacote)
                    except (BrokenPipeError, ConnectionResetError):
                        print("OpenViBE desconectou.")
                        raise KeyboardInterrupt


            # ---- Contador de taxa real de amostragem (diagnóstico da onda quadrada) ----
            contador_amostras += len(valor)
            if time.time() - inicio >= 1:
                print(f"Amostras/segundo reais: {contador_amostras}")
                contador_amostras = 0
                inicio = time.time()


    except KeyboardInterrupt:
        print("\nEncerrando...")


    finally:
        ser.close()
        conn.close()
        servidor.close()
        print("Conexões fechadas.")




if __name__ == "__main__":
    main()

