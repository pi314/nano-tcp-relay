#!/usr/bin/env python3
import re
import select
import signal
import socket
import sys
from textwrap import dedent
import threading
import time

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
    print(dedent(f'''\
        [cmd] Internal command usage
        h       : stop output and print this usage (alias: empty line)
        p       : start output
        l       : list current relaying ports
        a <port>: add relaying port
        d <port>: remove relaying port
        q       : quit

        Current destination host: {config["host"]}
    '''))


def process_command(cmd):
    global print_quiet
    global thread_pool
    global config

    print_quiet = True
    cmd = cmd.strip()
    if cmd in ('', 'h'):
        print_internal_command_usage()
        return

    elif cmd in ('q',):
        # closing threads takes time
        # if we just return they will still be alive and we'll end up back here
        # instead, we should do a join before we return
        close_threads()
        for th in thread_pool:
            th.join()
        return

    elif cmd in ('p',):
        print_quiet = False
        print('[cmd] start print')

    elif cmd in ('l',):
        for i in config['ports']:
            print('{}-{}'.format(*i))

        return

    else:
        cmd = cmd.split()
        if len(cmd) < 2:
            print('Lack of argument: port')
            return

        m = re.match(r'^(\d+)(?:-(\d+))?$', cmd[1])
        if m is None:
            print('Invalid port number: {}'.format(cmd[1]))
            return

        p = m.groups()

        if cmd[0] in ('a',):
            p = (int(p[0]), int(p[0] if p[1] is None else p[1]))
            if invalid_port(p[0]) or invalid_port(p[1]):
                print('Invalid port number: {}'.format(cmd[1]))
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
                return

            p = int(p[0])
            for th in thread_pool:
                if th.ports[0] == p:
                    th.stop()

            config['ports'] = list(filter(lambda x: x[0] != p, config['ports']))

            for i in config['ports']:
                print('{}-{}'.format(*i))


def print_usage():
    command = sys.argv[0]
    print(dedent(f'''\
        Usage:
            {command} host [ports] ...

        host:             IP address or host name to forward to
        ports:
            number        Forward a single TCP port to the same destination port
            local-remote: Forward traffic from a local port to a different remote port
    '''), file=sys.stderr)


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
                try:
                    client, addr = self.socket.accept()
                except OSError:
                    # the socket was killed before we got a connection
                    self.stop()
                    break

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
            self.stop()

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


def close_threads():
    global thread_pool
    for th in thread_pool:
        th.stop()

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


def signal_handler(*args, **kwargs):
    close_threads()


def threads_alive():
    return any(map(lambda th: th.is_alive(), thread_pool))

if sys.platform == 'win32':
    import msvcrt
    def get_user_input():
        while threads_alive():
            if msvcrt.kbhit():
                return input()
            time.sleep(0.1)
else:
    def get_user_input():
        # avoid issues with select blocking forever and ignoring ctrl+c in python 3.6
        # by setting a timeout and looping
        while threads_alive():
            # only call input if we have input waiting for us
            # otherwise we break ctrl+c due to threading
            i, o, e = select.select([sys.stdin], [], [], 0.1)
            if i:
                return input()

def user_input():
    # due to use not using an endline, this doesn't always print
    # so force a flush
    print('COMMAND> ', end='')
    sys.stdout.flush()
    return get_user_input()

def main():
    # on windows we need to explicitly add signal handlers
    # due to an side-effect of the threading causing signals (ctrl+c)
    # to be eaten and not be passed to the application
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

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

    # let the threads startup and print before we print out our prompt
    time.sleep(0.1)

    try:
        while threads_alive():
            i = user_input()
            if i:
                process_command(i)

    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == '__main__':
    main()
