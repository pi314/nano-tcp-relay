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

* Relay many TCP ports

  - ``$ nano-tcp-relay {host} {relay-port-1} [{relay-port-2} ... {relay-port-n}]``
  - Works as following ::

      Internet ---> localhost:{relay-port-1} ---> {host}:{relay-port-1}
      Internet ---> localhost:{relay-port-2} ---> {host}:{relay-port-2}
      ...
      Internet ---> localhost:{relay-port-n} ---> {host}:{relay-port-n}
