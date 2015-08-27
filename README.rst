==============
Nano TCP Relay
==============

Some times I need to relay TCP connections through some machines, and this can be achieved by ``nc`` command with a ``fifo`` file : ::

  #!/usr/bin/sh
  if [ -z $1 ] || [ -z $2 ] || [ -z $3 ]; then
      echo "Usage: $0 port host port"
      exit
  fi

  backpipe="backpipe-$1-$2-$3"

  if [ -p $backpipe ]; then
      echo "$backpipe exists."
  else
      mkfifo $backpipe
  fi

  while [ 1 ]; do
      echo "listening on port $1 and redirect to $2:$3"
      nc -l $1 0<$backpipe | nc $2 $3 1>$backpipe
      echo "one connection ends, start another."
  done

Usage
-----

* Transparently relay TCP ports ::

    $ nano-tcp-relay {host} {port-1} [{port-2} ... {port-n}]

  - Works as following ::

      Internet ---> localhost:{port-1} ---> {host}:{port-1}
      Internet ---> localhost:{port-2} ---> {host}:{port-2}
      ...
      Internet ---> localhost:{port-n} ---> {host}:{port-n}

* Relay and port forwarding ::

    $ nano-tcp-relay {host} {src-port-1}-{dst-port-1} [{src-port-2}-{dst-port-2} ...]

  - Works as following ::

      Internet --> localhost:{src-port-1} ---> {host}:{dst-port-1}
      Internet --> localhost:{src-port-2} ---> {host}:{dst-port-2}
      ...
      Internet --> localhost:{src-port-n} ---> {host}:{dst-port-n}
