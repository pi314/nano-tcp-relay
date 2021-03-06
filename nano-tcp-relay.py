#!/usr/bin/env python3
import sys
import re
import threading
import socket

EX_USAGE = 64   # man sysexits
EX_SOFTWARE = 70

if sys.version_info[0] < 3:
    print('Python2 is not supported.')
    exit(EX_SOFTWARE)

thread_pool = []

print_quiet = False

def log_info(*args, **kargs):
    if not print_quiet:
        print(*args, **kargs)


def print_internal_command_usage():
    print('[cmd] Internal command usage')
    print('h       : stop output and print this usage (alias: empty line)')
    print('p       : start output')
    print('l       : list current relaying ports')
    print('a <port>: add relaying port')
    print('d <port>: remove relaying port')
    print('')
    print('Current destination host: {}'.format(config['host']))


def process_command(cmd):
    global print_quiet
    global thread_pool
    global config

    print_quiet = True
    cmd = cmd.strip()
    if cmd in ('', 'h'):
        print_internal_command_usage()
        print('> ', end='')

    elif cmd in ('p',):
        print_quiet = False
        print('[cmd] start print')

    elif cmd in ('l',):
        for i in config['ports']:
            print('{}-{}'.format(*i))

        print('> ', end='')

    else:
        cmd = cmd.split()
        if len(cmd) < 2:
            print('Lack of argument: port')
            print('> ', end='')
            return

        m = re.match(r'^(\d+)(?:-(\d+))?$', cmd[1])
        if m is None:
            print('Invalid port number: {}'.format(cmd[1]))
            print('> ', end='')
            return

        p = m.groups()

        if cmd[0] in ('a',):
            p = (int(p[0]), int(p[0] if p[1] is None else p[1]))
            if invalid_port(p[0]) or invalid_port(p[1]):
                print('Invalid port number: {}'.format(cmd[1]))
                print('> ', end='')
                return

            config['ports'].append(p)
            th = ListeningThread(config['host'], p)
            th.daemon = True
            th.start()
            thread_pool.append(th)
            for i in config['ports']:
                print('{}-{}'.format(*i))

        elif cmd[0] in ('d',):
            if p[1] is not None:
                print('Delete command only accepts one port number, not a port pair')
                print('> ', end='')
                return

            p = int(p[0])
            for th in thread_pool:
                if th.ports[0] == p:
                    th.stop()

            config['ports'] = list(filter(lambda x: x[0] != p, config['ports']))

            for i in config['ports']:
                print('{}-{}'.format(*i))

        print('> ', end='')


def print_usage():
    print('Usage:', file=sys.stderr)
    print('    {} host port1 port2 ...'.format(sys.argv[0]), file=sys.stderr)
    print('', file=sys.stderr)
    print('    host: IP address or host name', file=sys.stderr)
    print('    port: TCP port number', file=sys.stderr)


def print_error_message(msg):
    log_info(msg, file=sys.stderr)


def invalid_port(p):
    return p <= 0 or p > 65535


def parse_args(args):
    if len(args) < 3:
        print_usage()
        exit(EX_USAGE)

    ret = {}
    if not re.match(r'^([0-9a-zA-Z-]+)(\.[0-9a-zA-Z-]+)*$', args[1]):
        print_error_message('Invalid host: {}'.format(args[1]))
        print_usage()
        exit(EX_USAGE)

    ret['host'] = args[1]

    ret['ports'] = []
    for i in args[2:]:
        m = re.match(r'^(\d+)(?:-(\d+))?$', i)
        if m is None:
            print_error_message('Invalid port number: {}'.format(i))
            exit(EX_USAGE)

        p = m.groups()
        p = (int(p[0]), int(p[0] if p[1] is None else p[1]))
        if invalid_port(p[0]) or invalid_port(p[1]):
            print_error_message('Invalid port number: {}'.format(i))
            exit(EX_USAGE)

        ret['ports'].append(p)

    if ret['host'] in ('localhost', '127.0.0.1'):
        if any(map(lambda x: x[0] == x[1], ret['ports'])):
            print_error_message('Localhost infinite loop is dangerous')
            exit(EX_USAGE)

    return ret


class ListeningThread(threading.Thread):
    def __init__(self, host, ports):
        threading.Thread.__init__(self)
        self.daemon = True
        self.host = host
        self.ports = ports
        self.socket = None
        self.run_permission = True

    def run(self):
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('', self.ports[0]))
        log_info('[listen] {} (--> {})'.format(*self.ports))
        self.socket.listen(5)
        try:
            while self.run_permission:
                client, addr = self.socket.accept()
                try:
                    relay = socket.socket()
                    relay.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    relay.connect((self.host, self.ports[1]))
                    info = get_connection_info(client, relay)
                    log_info('[opened] {client-addr}:{client-port} <--{listen-port}--{out-going-port}--> {remote-addr}:{remote-port}'.format(**info))
                    th = threading.Thread(target=connection_thread, args=(client, relay))
                    th.daemon = True
                    th.start()
                    th = threading.Thread(target=connection_thread, args=(relay, client))
                    th.daemon = True
                    th.start()
                except ConnectionRefusedError:
                    client_info = client.getpeername()
                    client.close()
                    relay.close()
                    log_info('[failed] {ch}:{cp} --> {h}:{p}'.format(
                        ch=client_info[0], cp=client_info[1],
                        h=self.host, p=self.ports[1]
                    ))

        except (InterruptedError, ConnectionAbortedError):
            for th in thread_pool:
                th.stop()

    def stop(self):
        self.run_permission = False
        try:
            close_socket(self.socket)
        except OSError:
            pass


def get_connection_info(client, relay):
    client_info = {
        'remote': client.getpeername(),
        'local': client.getsockname(),
    }
    relay_info = {
        'remote': relay.getpeername(),
        'local': relay.getsockname(),
    }
    info = {
        'client-addr': client_info['remote'][0],
        'client-port': client_info['remote'][1],
        'listen-port': client_info['local'][1],
        'out-going-port': relay_info['local'][1],
        'remote-addr': relay_info['remote'][0],
        'remote-port': relay_info['remote'][1],
    }
    return info


def close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    try:
        sock.close()
    except OSError:
        pass


def connection_thread(fr, to):
    from_info = fr.getpeername()
    to_info = to.getpeername()
    info = {
        'fr-addr': from_info[0],
        'fr-port': from_info[1],
        'fr-local-port': fr.getsockname()[1],
        'to-local-port': to.getsockname()[1],
        'to-addr': to_info[0],
        'to-port': to_info[1],
    }
    try:
        while True:
            data = fr.recv(1024)
            if len(data) <= 0:
                break
            log_info('[data  ] {fr-addr}:{fr-port} --{fr-local-port}--{to-local-port}--> {to-addr}:{to-port} ({count})'.format(count=len(data), **info))
            to.sendall(data)

        close_socket(fr)
        close_socket(to)

    except (ConnectionResetError, OSError):
        pass

    finally:
        close_socket(fr)
        close_socket(to)
        log_info('[closed] {fr-addr}:{fr-port} --{fr-local-port}--{to-local-port}--> {to-addr}:{to-port}'.format(**info))


def main():
    global thread_pool
    # config format:
    # {
    #   'host': host,
    #   'ports': [(src, dst), ...]
    # }
    global config
    config = parse_args(sys.argv)
    for p in config['ports']:
        th = ListeningThread(config['host'], p)
        th.daemon = True
        th.start()
        thread_pool.append(th)

    try:
        while True:
            process_command(input())

    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == '__main__':
    main()
