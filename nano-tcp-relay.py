import sys
import re
import threading
import socket

thread_pool = []

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

class ListeningThread(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.daemon = True
        self.host = host
        self.port = port
        self.socket = None
        self.run_permission = True

    def run(self):
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('', self.port))
        print('Start listening at {}'.format(self.port))
        self.socket.listen(5)
        try:
            while self.run_permission:
                client, addr = self.socket.accept()
                info = {
                    'host': self.host,
                    'port': self.port,
                    'client-addr': addr[0],
                    'client-port': addr[1],
                }
                print('{a[0]}:{a[1]} <-> {h}:{p} opened'.format(a=addr, h=self.host, p=self.port))
                try:
                    relay = socket.socket()
                    relay.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    relay.connect((self.host, self.port))
                    th = threading.Thread(target=connection_thread, args=(client, relay))
                    th.daemon = True
                    th.start()
                    th = threading.Thread(target=connection_thread, args=(relay, client))
                    th.daemon = True
                    th.start()
                except ConnectionRefusedError:
                    client.close()
                    relay.close()
                    print('{a[0]}:{a[1]} <-> {h}:{p} closed'.format(a=addr, h=self.host, p=self.port))

        except (InterruptedError, ConnectionAbortedError):
            for th in thread_pool:
                th.stop()

    def stop(self):
        self.run_permission = False
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        except OSError:
            pass

def connection_thread(fr, to):
    from_info = fr.getpeername()
    to_info = to.getpeername()
    info = {
        'from-addr': from_info[0],
        'from-port': from_info[1],
        'to-addr': to_info[0],
        'to-port': to_info[1],
    }
    try:
        while True:
            data = fr.recv(1024)
            if len(data) <= 0:
                break
            to.sendall(data)
    except (ConnectionResetError, OSError):
        pass
    finally:
        to.shutdown(socket.SHUT_RDWR)
        to.close()
        print('{from-addr}:{from-port} -> {to-addr}:{to-port} closed'.format(**info))

def main():
    global thread_pool
    config = parse_args(sys.argv)
    for p in config['ports']:
        th = ListeningThread(config['host'], p)
        th.daemon = True
        th.start()
        thread_pool.append(th)

    try:
        for th in thread_pool:
            th.join()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
