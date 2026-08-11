import socket
import threading
import argparse


def main():
    host, ports = get_arguments()

    host = validate_host(host)

    if not host:
        return

    ports = parse_ports(ports)

    result = scan(host, ports)

    print_result(host, result)


def get_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-H',
        '--host',
        required=True,
        help='Хост для сканирования'
    )

    parser.add_argument(
        '-p',
        '--ports',
        required=True,
        help='Порты для сканирования'
    )

    arg = parser.parse_args()

    return arg.host, arg.ports


def validate_host(host):
    try:
        ip = socket.gethostbyname(host)
        return ip

    except Exception:
        print(f'Неверный хост, проверь еблан: {host}')
        return False


def parse_ports(port_string):
    ports = []

    parts = port_string.split(',')

    for part in parts:
        if '-' in part:
            try:
                start, end = part.split('-')

                start = int(start)
                end = int(end)

                if start < 1 or end > 65535 or start > end:
                    raise ValueError

                for port in range(start, end + 1):
                    ports.append(port)

            except ValueError:
                raise ValueError(f'Неверный диапазон портов: {part}')

        else:
            try:
                port = int(part)

                if port < 1 or port > 65535:
                    raise ValueError

                ports.append(port)

            except ValueError:
                raise ValueError(f'Неверный порт: {part}')

    return sorted(set(ports))


def scan_port(host, port):
    sock = socket.socket()
    sock.settimeout(0.5)

    try:
        sock.connect((host, port))
        return 'OPEN'

    except socket.timeout:
        return 'CLOSED'

    except ConnectionRefusedError:
        return 'CLOSED'

    except Exception as e:
        return f'ERROR: {e}'

    finally:
        sock.close()


def scan(host, ports):
    results = {}
    threads = []
    lock = threading.Lock()

    def check_port(port):
        status = scan_port(host, port)

        with lock:
            results[port] = status

    for port in ports:
        thread = threading.Thread(
            target=check_port,
            args=(port,)
        )

        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return results


def print_result(host, results):
    print(f'\nСканирование: {host}\n')

    for port in sorted(results):
        status = results[port]

        print(f'{port}: {status}')


if __name__ == '__main__':
    main()