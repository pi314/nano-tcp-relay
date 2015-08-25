import sys
import re

def print_usage():
    print('Usage:', file=sys.stderr)
    print('    {} host port1 port2 ...'.format(sys.argv[0]), file=sys.stderr)
    print('', file=sys.stderr)
    print('    host: IP address or host name', file=sys.stderr)
    print('    port: TCP port number', file=sys.stderr)

def print_error_message(msg):
    print(msg, file=sys.stderr)

def parse_args(args):
    if not re.match(r'^([0-9a-zA-Z]+)(\.[0-9a-zA-Z]+){3}$', args[1]):
        print_error_message('Invalid host: {}'.format(args[1]))
        print_usage()
        exit(64)    # EX_USAGE, ``man sysexit``

def main():
    config = parse_args(sys.argv)

if __name__ == '__main__':
    main()
