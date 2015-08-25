import sys
import re
import threading
import socket

def print_usage():
    print('Usage:', file=sys.stderr)
    print('    {} host port1 port2 ...'.format(sys.argv[0]), file=sys.stderr)
    print('', file=sys.stderr)
    print('    host: IP address or host name', file=sys.stderr)
    print('    port: TCP port number', file=sys.stderr)

def print_error_message(msg):
    print(msg, file=sys.stderr)

def parse_args(args):
    ret = {}
    if not re.match(r'^([0-9a-zA-Z]+)(\.[0-9a-zA-Z]+)*$', args[1]):
        print_error_message('Invalid host: {}'.format(args[1]))
        print_usage()
        exit(64)    # EX_USAGE, ``man sysexit``

    ret['host'] = args[1]

    try:
        for i in args[2:]:
            p = int(i)
            if p <= 0 or p > 65535:
                raise ValueError

        ret['ports'] = [int(i) for i in args[2:]]
    except ValueError as e:
        print_error_message('Invalid port number: {}'.format(i))
        exit(64)

    return ret

def listening_thread(host, port):
    print(host, port)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', port))
    print('Start listening at {}'.format(port))
    s.listen(5)
    while True:
        client, addr = s.accept()
        info = {
            'host': host,
            'port': port,
            'client-addr': addr[0],
            'client-port': addr[1],
        }
        print('{a[0]}:{a[1]} <-> {h}:{p} opened'.format(a=addr, h=host, p=port))
        try:
            relay = socket.socket()
            relay.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            relay.connect((host, port))
            t = threading.Thread(target=connection_thread, args=(client, relay))
            t.daemon = True
            t.start()
            t = threading.Thread(target=connection_thread, args=(relay, client))
            t.daemon = True
            t.start()
        except ConnectionRefusedError:
            client.close()
            relay.close()

def connection_thread(f, t):
    from_info = f.getsockname()
    to_info = t.getsockname()
    info = {
        'from-addr': from_info[0],
        'from-port': from_info[1],
        'to-addr': to_info[0],
        'to-port': to_info[1],
    }
    try:
        while True:
            data = f.recv(1024)
            if len(data) <= 0:
                break
            t.sendall(data)
    except ConnectionResetError:
        pass
    except OSError:
        pass
    finally:
        f.close()
        t.close()
        print('{from-addr}:{from-port} -> {to-addr}:{to-port} closed'.format(**info))

def main():
    config = parse_args(sys.argv)
    for p in config['ports']:
        t = threading.Thread(target=listening_thread, args=(config['host'], p))
        t.daemon = True
        t.start()

    while True: input()

if __name__ == '__main__':
    main()
